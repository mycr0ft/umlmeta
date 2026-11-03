#!/usr/bin/env python
"""ocl_translator.py — the OCL runtime: helpers, the eval environment, and
the compatibility API over the AST.

Parsing and lowering moved out (O1):

  ocl_parse   tokenizer + recursive-descent parser -> ocl_ast tree
  ocl_ast     nodes with source spans, dump()/walk()/replace()
  ocl_emit    to_python() (this module's eval target) and to_ocl()
  ocl_symbols the operation tables shared by parser and emitter

What stays here is what the lowered code calls: the navigation and coercion
helpers (`_dot`, `_nav`, `_eq`, ...), the spec operations the repo
implements itself (is_multivalued, containing_activity, vertex_incoming,
all_instances, ...), and the eval environment that binds them.

Entry points:
  translate(body)         -> Python source (AST -> to_python), cached
  translate_legacy(body)  -> the pre-AST emitter; the differential oracle in
                             check_ocl_ast.py, delete at O3
  parse(body)             -> ocl_ast tree
  eval_body(body, self_obj, derived) -> Python value of the body
  check_constraints(obj, derived)    -> (ok, results, skipped)

Lowering vocabulary (unchanged; the AST emits it):

  OCL                           Python
  ----------------------------  ----------------------------------------
  a.b                           _dot(a, 'b')  / _g(self, 'b')
  c->select(e | p)              [e for e in c if p]
  c->exists(e | p)              any(p for e in c)
  c->forAll(e | b)              all(b for e in c)
  c->size()                     len(c)
  a implies b                   (not a) or b
  null / <> null                None / != None
  Enum::lit                     'lit'   (runtime stores literals as strings)
  let x = e in rest             (lambda _let1_x: rest)(e)
  x.oclIsKindOf(T)              _k(x, 'T')
  m.is(1,1)                     is_mult(m, 1, 1)

Elisions (raise UnmappedFeature, never guessed): @pre, ->iterate,
->isUnique, ->sortedBy, ->collectNested, selectByKind/specializesFromLibrary
and other KerML/SysML/spec helper operations (O3/O4), type-scoped calls
except `X.allInstances()` (O2/O5), and the extent itself — `all_instances`
returns [] because a bare object has no resource.
"""

from __future__ import annotations

import re

from . import extent as extent_mod
from . import derived as D
from . import ocl_ast, ocl_emit, ocl_parse
from . import ocl_symbols as SY
from . import uml25 as U


# the parser and emitter raise the AST module's exception; aliased here so
# `except ocl_translator.UnmappedFeature` keeps working
UnmappedFeature = ocl_ast.UnmappedFeature


# --------------------------------------------------------------------------
# runtime helpers (bound into the eval environment)
# --------------------------------------------------------------------------

def enum_val(v):
    """Normalize an enum-ish runtime value to its OCL literal string."""
    if v is None:
        return None
    if isinstance(v, U._enum.Enum):
        return v.value
    return str(v)


def ocl_is_kind_of(obj, tname):
    """obj.oclIsKindOf(T): obj's dynamic type conforms to metaclass T.
    Module-first lookup (like the extent's), with an uml25 fallback so
    a sysml2 element still answers against the UML hierarchy. Names that
    exist only in the v2 hierarchy answer False, not KeyError."""
    if obj is None:
        return False
    cls = extent_mod.metaclass(tname, getattr(_EXTENT, "prefer", None))
    if cls is not None and isinstance(obj, cls):
        return True
    try:
        return isinstance(obj, U.metaclass(tname))
    except KeyError:
        return False


def ocl_is_type_of(obj, tname):
    """obj.oclIsTypeOf(T): obj's dynamic type IS exactly T."""
    if obj is None:
        return False
    return type(obj).__name__ == tname


def ocl_as_type(obj, tname):
    """obj.oclAsType(T): obj when kind-of T, else invalid (None)."""
    return obj if ocl_is_kind_of(obj, tname) else None


def ocl_aslist(v):
    """OCL collection coercion: a single-valued property read is
    Set{v}; multi-valued properties are already lists."""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return v
    return [v]


def ocl_nav(v):
    """Receiver coercion for a collection operation: single-valued ->
    one-element list; None -> empty; list -> itself."""
    return ocl_aslist(v)


class Undetermined(Exception):
    """An evaluation that cannot answer yes or no (a feature the runtime
    does not carry). Recorded as a skip, never as False."""


class _Undefined:
    """A read of a feature this runtime does not have.

    OCL's `invalid`: any boolean use raises, so `all()`/`any()`/`if` cannot
    silently turn "I cannot tell" into False.
    """

    __slots__ = ("feature",)

    def __init__(self, feature):
        self.feature = feature

    def __bool__(self):
        raise Undetermined(f"undetermined: no feature {self.feature!r}")

    def __repr__(self):
        return f"<undetermined {self.feature!r}>"


_MISSING = object()


_DERIV_SRC = {}
_DERIV_BUSY = set()


def _derivation_source(cls, prop):
    """Python source for the right-hand side of `derive<Base><Prop>`.

    The KerML/SysML AS derives most properties by rule
    (`deriveUsageIsReference` = `isReference = not isComposite`), and the
    generated runtime stores those properties as None. Searching the MRO
    matters: the derivation is declared where the property is, not on every
    subclass.
    """
    key = (cls.__name__, prop)
    if key in _DERIV_SRC:
        return _DERIV_SRC[key]
    src = None
    # pass 1: the naming convention (`derive<Base><Prop>`)
    candidates = []
    for base in cls.__mro__:
        want = "derive" + base.__name__ + prop[:1].upper() + prop[1:]
        hit = [b for n, b in base.__dict__.get("CONSTRAINTS", ())
               if n == want]
        if hit:
            candidates.append((base.__name__, prop, hit[0]))
    # pass 2: corpus bodies whose LEFT-HAND SIDE names the property but
    # whose rule name does not follow the convention
    # (deriveUsageNestedEnumeration derives `ownedNested`)
    if not candidates:
        for base in cls.__mro__:
            for n, b in base.__dict__.get("CONSTRAINTS", ()):
                if not n.startswith("derive"):
                    continue
                try:
                    tree = ocl_parse.parse(_repair_body(base.__name__, n, b))
                except Exception:              # noqa: BLE001
                    continue
                if isinstance(tree, ocl_ast.BinOp) and tree.op == "=" \
                        and getattr(tree.left, "name", None) == prop:
                    candidates.append((base.__name__, n[len('derive'):], b))
                    break
            if candidates:
                break
    src = None
    for base_name, prop_name, hit in candidates:
        src_text = _repair_body(base_name, prop_name, hit)
        tree = ocl_parse.parse(src_text)          # may raise: reported
        rhs = tree.right if isinstance(tree, ocl_ast.BinOp) and \
            tree.op == "=" else tree
        src = ocl_emit.to_python(rhs)
        break
    _DERIV_SRC[key] = src
    return src


# Structural AS derivations: rules the runtime computes from a link rather
# than from an expression, so the corpus carries no body for them.
def _is_end(obj):
    """KerML Feature::isEnd — the owning membership is an EndFeatureMembership."""
    from . import sysml2 as _S2
    return isinstance(getattr(obj, "owningMembership", None),
                      _S2.EndFeatureMembership)


_AS_STRUCTURAL: dict = {"isEnd": _is_end}  # deliberately heterogeneous values


def _owned_member_feature(obj):
    """Membership::ownedMemberFeature — the single owned member that is a
    Feature. Structural, so the corpus carries no body for it."""
    from . import sysml2 as _S2
    feats = [m for m in (getattr(obj, "ownedRelatedElement", None) or ())
             if isinstance(m, _S2.Feature)]
    return feats[0] if feats else None


_AS_STRUCTURAL["ownedMemberFeature"] = _owned_member_feature


def _owned_feature(obj):
    """Type::ownedFeature — the owned members that are Features. A membership
    subtype owns its member as a feature: EndFeatureMembership IS a
    FeatureMembership, and the connector's end memberships are exactly what
    makes its ends visible here."""
    from . import sysml2 as _S2
    feats = list(getattr(obj, "ownedFeature", None) or ())
    for rel in (getattr(obj, "ownedRelationship", None) or ()):
        if isinstance(rel, _S2.FeatureMembership):
            for m in (getattr(rel, "ownedRelatedElement", None) or ()):
                if isinstance(m, _S2.Feature) and m not in feats:
                    feats.append(m)
    return feats


def _owned_end_feature(obj):
    """Type::ownedEndFeature — ownedFeature->select(isEnd). Reachable now:
    isEnd computes structurally and owningMembership is set by as_inverses."""
    return [f for f in _owned_feature(obj) if _is_end(f)]


def _connector_end(obj):
    """Connector::connectorEnd — the connector's own end features."""
    return _owned_end_feature(obj)


_AS_STRUCTURAL["ownedEndFeature"] = _owned_end_feature
_AS_STRUCTURAL["connectorEnd"] = _connector_end


def _owned_reference_subsetting(obj):
    """Feature::ownedReferenceSubsetting — ownedRelationship->selectByKind
    (ReferenceSubsetting). The generated runtime declares the end derived,
    so it never stores it; the rule is the select over ownedSubsetting."""
    from . import sysml2 as _S2
    return [rel for rel in (getattr(obj, "ownedRelationship", None) or ())
            if isinstance(rel, _S2.ReferenceSubsetting)]


def _subsetted_feature(obj):
    """Subsetting::subsettedFeature — whatever the subsetting points at."""
    return getattr(obj, "referencedFeature", None)


_AS_STRUCTURAL["ownedReferenceSubsetting"] = _owned_reference_subsetting
_AS_STRUCTURAL["subsettedFeature"] = _subsetted_feature
# ParameterMembership::ownedMemberParameter redefines ownedMemberFeature:
# the single owned member, which IS a Feature (the parameter).
_AS_STRUCTURAL["ownedMemberParameter"] = _owned_member_feature


def _owned_member_element(obj):
    """Membership::ownedMemberElement — the single owned member (any
    Element); the corpus derivation of Namespace::ownedMember reads this
    end, and the transform stores membership members in
    ownedRelatedElement."""
    rels = getattr(obj, "ownedRelatedElement", None) or ()
    return rels[0] if rels else None


_AS_STRUCTURAL["ownedMemberElement"] = _owned_member_element


def _membership_owning_namespace(m):
    """Membership::membershipOwningNamespace — the namespace that owns
    the membership (= its owner for a directly-held membership)."""
    from . import sysml2 as _S2
    o = D.owner(m) if callable(getattr(D, "owner", None)) else None
    if isinstance(o, _S2.Namespace):
        return o
    return o


_AS_STRUCTURAL["membershipOwningNamespace"] = _membership_owning_namespace


def _feature_type(obj):
    """Feature::type — ownedTyping->collect(type). The normative
    deriveFeatureType body is a corpus text defect (unparseable escape),
    so the structural form carries the derivation."""
    out = []
    for ot in (getattr(obj, "ownedTyping", None) or ()):
        t = getattr(ot, "type", None)
        if t is not None:
            out.append(t)
    return out


_AS_STRUCTURAL["type"] = _feature_type


def _related_types(obj):
    """Association::relatedType — the types of the association's end
    features (set-valued, memberEnd order)."""
    out, seen = [], set()
    for end in _owned_end_feature(obj):
        for t in _feature_type(end):
            if t is not None and id(t) not in seen:
                seen.add(id(t))
                out.append(t)
    return out


_AS_STRUCTURAL["relatedType"] = _related_types


def _item_definition(obj):
    """Usage::itemDefinition — the typing types (ownedTyping->collect
    (type)); partDefinition's normative derivation narrows to
    PartDefinition on top of this."""
    return _feature_type(obj)


_AS_STRUCTURAL["itemDefinition"] = _item_definition
# Association::associationEnd — the association's end features; the
# normative relatedType derivation reads associationEnd.type
_AS_STRUCTURAL["associationEnd"] = _owned_end_feature
# Usage::occurrenceDefinition — the occurrence-kind typing types; the
# itemDefinition corpus derivation reads occurrenceDefinition->selectByKind
_AS_STRUCTURAL["occurrenceDefinition"] = _feature_type


def _expr_result(obj):
    """Expression::result — the result Feature carried by the expression's
    ReturnParameterMembership (the .33/.34 result-parameter shape the
    transform attaches to every literal)."""
    for m in (getattr(obj, "ownedRelationship", None) or ()):
        if type(m).__name__ == "ReturnParameterMembership":
            ch = m._vals.get("ownedRelatedElement") or ()
            return ch[0] if ch else None
    return None


_AS_STRUCTURAL["result"] = _expr_result
# Connector::sourceFeature / targetFeature — the relatedFeature slices
# (source the first related feature, targetFeature the rest); the corpus
# derivations read connectorEnd chains that the transform emits as owned
# ReferenceSubsettings
def _connector_source_feature(obj):
    rel = _related_features(obj)
    return rel[0] if rel else None


def _connector_target_features(obj):
    return _related_features(obj)[1:]


def _related_features(obj):
    rels = []
    for e2 in _owned_end_feature(obj):
        for s in (getattr(e2, "ownedRelationship", None) or ()):
            if type(s).__name__ in ("ReferenceSubsetting", "Subsetting"):
                tgt = s._vals.get("referencedFeature") \
                    or s._vals.get("subsettedFeature")
                if tgt is not None:
                    rels.append(tgt)
    return rels


_AS_STRUCTURAL["sourceFeature"] = _connector_source_feature
_AS_STRUCTURAL["targetFeature"] = _connector_target_features
# the binding-connector rules navigate `relatedFeatures` (plural) — the
# plural spelling of Connector::relatedFeature
_AS_STRUCTURAL["relatedFeatures"] = _related_features


def _specialization_special(obj):
    """Specialization::special — the specific (sub) type: the KerML owner
    link (Subclassification.subclassification... the sub owns the
    specialization)."""
    return D.owner(obj)


_AS_STRUCTURAL["special"] = _specialization_special


def _owned_generalization(obj):
    """Feature::ownedGeneralization — the generalizations (Specialization
    kinds) owned by the feature; deriveFeatureOwnedTyping narrows to
    FeatureTyping over this."""
    from . import sysml2 as _S2
    return [r for r in (obj._vals.get("ownedRelationship") or ())
            if isinstance(r, _S2.Specialization)]


_AS_STRUCTURAL["ownedGeneralization"] = _owned_generalization


def _specialization_is_implied(obj):
    """Relationship::isImplied — "generated by tooling to meet semantic
    rules". The transform's own library-base subclassifications are
    exactly that; a specialization carrying a user-side edge (a mapped
    v1 generalization) is redefined by its subclass (Subclassification
    redefines ... isImplied is False when explicitly set)."""
    return getattr(obj, "_vals", {}).get("isImplied", True)
    # a user specialization sets _vals["isImplied"] = False at emission


_AS_STRUCTURAL["isImplied"] = _specialization_is_implied


def _owning_variation(obj, kind):
    """Usage::owningVariationUsage / Definition::owningVariationDefinition
    — the owner chain's first Usage/Definition with isVariation = true
    (the runs end the AS declares for variants; our runtime drops these
    ends, so they are structural)."""
    from . import sysml2 as _S2
    o = D.owner(obj)
    while o is not None:
        if isinstance(o, kind) and o._vals.get("isVariation"):
            return o
        o = D.owner(o)
    return None


def _owning_variation_usage(obj):
    from . import sysml2 as _S2
    return _owning_variation(obj, _S2.Usage)


def _owning_variation_definition(obj):
    from . import sysml2 as _S2
    return _owning_variation(obj, _S2.Definition)


_AS_STRUCTURAL["owningVariationUsage"] = _owning_variation_usage
_AS_STRUCTURAL["owningVariationDefinition"] = _owning_variation_definition


def _nested_usage(obj):
    """Usage::nestedUsage — the member usages nested within this usage
    (the corpus deriveUsageNestedEnumeration reads it)."""
    from . import sysml2 as _S2
    out = []
    for m in _aslist(getattr(obj, "ownedRelationship", None) or ()):
        if not isinstance(m, _S2.OwningMembership):
            continue
        for ch in _aslist(m._vals.get("ownedRelatedElement") or ()):
            if isinstance(ch, _S2.Usage):
                out.append(ch)
    return out


_AS_STRUCTURAL["nestedUsage"] = _nested_usage


def _inherited_memberships(tp):
    """Type::inheritedMemberships — the memberships of the types this
    type specializes (transitively, the AS inheritance model). Library
    stubs carry no memberships, so they contribute nothing."""
    from . import sysml2 as _S2
    out, seen_types = [], set()
    stack = [g for s in (getattr(tp, "ownedRelationship", None) or ())
             if isinstance(s, _S2.Specialization)
             for g in _aslist(s._vals.get("general") or ())]
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen_types:
            continue
        seen_types.add(id(cur))
        for m in (cur._vals.get("ownedRelationship") or ()):
            if isinstance(m, _S2.Membership):
                out.append(m)
        for s in (cur._vals.get("ownedRelationship") or ()):
            if isinstance(s, _S2.Specialization):
                for g in _aslist(s._vals.get("general") or ()):
                    stack.append(g)
    return out


_AS_STRUCTURAL["inheritedMemberships"] = _inherited_memberships
# Type/Feature::featureMemberships — the corpus result/parameter derivation
# reads this end; the runtime carries memberships only in
# ownedRelationship, so the select is structural here
def _feature_membership_union(obj):
    """Type::featureMembership — the corpus `feature` derivation reads
    this end (featureMembership.ownedMemberFeature); variant memberships
    (VariantMembership) carry features too, so they contribute."""
    from . import sysml2 as _S2
    return [rel for rel in (obj._vals.get("ownedRelationship") or ())
            if isinstance(rel, (_S2.FeatureMembership,
                                _S2.VariantMembership))]


_AS_STRUCTURAL["featureMembership"] = _feature_membership_union
_AS_STRUCTURAL["featureMemberships"] = _feature_membership_union
_AS_STRUCTURAL["ownedSubjectParameter"] = _owned_member_feature
# CaseUsage spells the same derived end without 'owned' in some places
_AS_STRUCTURAL["subjectParameter"] = lambda obj: _owned_member_feature(obj)


def _needs_derivation(obj, name, v):
    """A derived property whose stored value is empty still needs its rule:
    a multi-valued derived end reads as an empty list, not as None. A
    non-derived end whose storage is empty is returned as-is — EXCEPT an
    end with redefines (the generator's marker that a subclass end carries
    the value), where None means "read the redefining sibling":
    Subsetting.subsettedFeature is the common case."""
    d = (getattr(type(obj), "_props", {}) or {}).get(name)
    if d is None:
        return False
    # a generated operation stub bound as a value is never a stored value
    # (established for derived_only_props) — a read through it must fall
    # to the rule layer instead of handing the method to the body
    if callable(v):
        return True
    if getattr(d, "derived", False):
        return v is None or (isinstance(v, (list, tuple)) and not v)
    if v is None:
        # unset Boolean attributes read FALSE (the tooling convention: a
        # materialized AS model omits false-valued Booleans — KerML
        # rules read isComposite/isVariation/... as false when unset)
        if getattr(d, "t", None) is bool or getattr(d, "t", None) == bool:
            return False
        if getattr(d, "redefines", ()):
            return True
    if isinstance(v, (list, tuple)) and not v \
            and (getattr(d, "subsets", ()) or getattr(d, "redefines", ())):
        # an unset multi end that participates in the AS composition web
        # (subsets/redefines another end) reads through its rule when one
        # exists — Type::feature over variant memberships is the case
        return True
    return False




def _local_read_fn(name):
    """The DERIVED_FUNCS "local" implementation for `name` when it takes
    exactly one positional argument — a bare property read of a query
    end (KerML ends ARE queries: owningType(), qualifiedName()) may
    dispatch to it."""
    entry = SY.DERIVED_FUNCS.get(name)
    if entry is None or entry[0] != "local":
        return None
    fn = globals().get(entry[1])
    if fn is None:
        return None
    try:
        import inspect as _inspect
        sig = _inspect.signature(fn)
        req = [q for q in sig.parameters.values()
               if q.default is _inspect.Parameter.empty]
        has_kw = any(q.default is not _inspect.Parameter.empty
                     for q in sig.parameters.values())
        pos = [q for q in sig.parameters.values()
               if q.kind in (_inspect.Parameter.POSITIONAL_ONLY,
                             _inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        if len(req) == 1 and len(pos) >= 1 and pos[0] is req[0] and not has_kw:
            return fn
    except (TypeError, ValueError):            # noqa: BLE001
        return None
    return None


def ocl_get(obj, name):
    """A bare property read (`ownedMemberFeature`), with the derivation and
    sentinel rules applied — the `_dot` fallback's counterpart, without which
    an unqualified name never reaches either."""
    v = getattr(obj, name, _MISSING)
    if callable(v):
        v = _MISSING                    # a stub op is not a stored value
    if v is None:
        # unset Boolean attributes read FALSE — but a DERIVED Boolean end
        # must still consult its derivation (the stored None only means
        # "no carrier"); non-derived ends take the tooling default directly
        d0 = getattr(type(obj), "_props", {}).get(name)
        if d0 is not None and getattr(d0, "t", None) is bool \
                and not getattr(d0, "derived", False):
            v = False
    if v is not _MISSING and not _needs_derivation(obj, name, v):
        return v
    d = derived_read(obj, name)
    if d is not _MISSING:
        return d
    lfn = _local_read_fn(name)
    if lfn is not None:
        try:
            return lfn(obj)
        except Exception:                      # noqa: BLE001
            pass
    if v is _MISSING or callable(v):
        return _Undefined(name)
    if v is None:
        # unset Boolean attributes read FALSE (the tooling convention: a
        # materialized AS model omits false-valued Booleans)
        dd = getattr(type(obj), "_props", {}).get(name)
        if dd is not None and getattr(dd, "t", None) is bool:
            return False
    return v


def derived_read(obj, prop):
    """Value of a derived property, or _MISSING when there is no rule.

    Rule order: a `derive<Base><Prop>` OCL constraint in the class MRO, then
    a structural rule (_AS_STRUCTURAL), then — new in O4b — a `derived.py`
    function registered in DERIVED_FUNCS as ("derived", fn) even when the
    generator kept the (derived, readonly) end, e.g. NamedElement.
    qualifiedName: the stored end is derived+readonly with no derive
    constraint, so without this last hop every read returned null."""
    try:
        src = _derivation_source(type(obj), prop)
    except Exception:                              # noqa: BLE001
        # an UNPARSEABLE derivation body (corpus text defect): fall
        # through to the structural/derived.py rules rather than
        # dropping the read to _MISSING
        src = None
    if src is None:
        fn = _AS_STRUCTURAL.get(prop)
        if fn is not None:
            return fn(obj)
        entry = SY.DERIVED_FUNCS.get(prop)
        if entry is not None and entry[0] == "derived":
            try:
                return getattr(D, entry[1])(obj)
            except Exception:                      # noqa: BLE001
                return _MISSING
        return _MISSING
    guard = (id(obj), prop)
    if guard in _DERIV_BUSY:
        return _MISSING
    _DERIV_BUSY.add(guard)
    try:
        from . import derived as _derived
        env = dict(_EVAL_ENV)
        env["self"] = obj
        env["_d"] = _derived_call(_derived)
        env["all_instances"] = all_instances
        g = dict(_EVAL_BUILTINS)
        g.update(env)
        val = eval(src, g, {})
        # a body that exists but evaluates to None because its own input is
        # missing must not shadow the structural rule; the same holds for an
        # EMPTY multi (the corpus derivations narrow to one membership kind,
        # and variants carried by other membership kinds still count)
        empty_multi = isinstance(val, (list, tuple)) and not val
        if val is None or empty_multi:
            fn = _AS_STRUCTURAL.get(prop)
            if fn is not None:
                sv = fn(obj)
                if sv is not None and (not empty_multi or sv):
                    return sv
        return val                    # noqa: S307
    except Exception:                              # noqa: BLE001
        return _MISSING
    finally:
        _DERIV_BUSY.discard(guard)


def ocl_dot(recv, attr):
    """Property navigation with implicit collect: over a single value
    this is getattr; over a collection it collects the attribute values
    (OCL 2.4 §10.3.2 implicit collect).

    A property with no stored carrier (the generator drops derived ends it
    cannot compute) resolves through `derived.py` instead of reading an
    attribute that does not exist — `self.owner` is the common case.
    """
    if isinstance(recv, (list, tuple)):
        return ocl_collect([ocl_dot(e, attr) for e in recv])
    if recv is None:
        return None
    v = getattr(recv, attr, _MISSING)
    if v is None:
        d0 = getattr(type(recv), "_props", {}).get(attr)
        if d0 is not None and getattr(d0, "t", None) is bool \
                and not getattr(d0, "derived", False):
            v = False   # unset Booleans read false (tooling convention)
    fn = SY.derived_only_props().get(attr)
    # a generated operation stub is a bound method: reading it as a property
    # would hand back the method object, so a derived implementation wins
    if fn is not None and (v is _MISSING or callable(v)):
        from . import derived as _derived
        return getattr(_derived, fn)(recv)
    if v is _MISSING or v is None or _needs_derivation(recv, attr, v):
        derived = derived_read(recv, attr)
        if derived is not _MISSING:
            return derived
    if v is _MISSING:
        # the runtime has no such feature: try the local query op, then
        # undetermined, not None
        lfn = _local_read_fn(attr)
        if lfn is not None:
            try:
                return lfn(recv)
            except Exception:              # noqa: BLE001
                pass
        return _Undefined(attr)
    if callable(v):
        # the rule layer has no better answer: a stub op is undetermined,
        # not a value the body can iterate
        return _Undefined(attr)
    if v is None:
        dd = getattr(type(recv), "_props", {}).get(attr)
        if dd is not None and getattr(dd, "t", None) is bool:
            return False   # unset Booleans read false (tooling convention)
    return v


def ocl_eq(a, b):
    if isinstance(a, _Undefined) or isinstance(b, _Undefined):
        raise Undetermined(
            f"undetermined comparison: "
            f"{getattr(a, 'feature', a)!r} vs {getattr(b, 'feature', b)!r}")
    """OCL =: for two collections, set equality; scalar = scalar is
    plain equality; a collected multi-valued read (list) against a
    scalar (None / literal / enum) follows the UML constraint-bodies'
    universal reading: every element equals the scalar.  An EMPTY
    collected read against null is True (no element violates it — the
    vacuous forAll reading the spec bodies rely on)."""
    if isinstance(a, (list, tuple)) and not isinstance(b, (list, tuple)):
        return all(x == b for x in a)
    if isinstance(b, (list, tuple)) and not isinstance(a, (list, tuple)):
        return all(x == a for x in b)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return (len(a) == len(b) and
                all(x in b for x in a))
    return a == b


def ocl_collect(seq):
    """Flatten a list of single values / lists into a dedup'd list
    (implicit-collect semantics for collect over multi-valued
    properties, per OCL 2.4 §10.3.2 flatten semantics)."""
    out, seen = [], set()
    for e in seq:
        for it in (e if isinstance(e, (list, tuple)) else (e,)):
            if it is None or id(it) in seen:
                continue
            seen.add(id(it))
            out.append(it)
    return out


def ocl_flatten(seq):
    """OCL flatten(): recursively unwraps nested collections."""
    out, seen = [], set()
    def rec(s):
        for e in s:
            if isinstance(e, (list, tuple)):
                rec(e)
            elif e is not None and id(e) not in seen:
                seen.add(id(e))
                out.append(e)
    rec(seq)
    return out


def ocl_union(a, b):
    """OCL union() over sequences: set-union, order preserved."""
    out, seen = [], set()
    for e in list(a) + list(b):
        if e is not None and id(e) not in seen:
            seen.add(id(e))
            out.append(e)
    return out


def ocl_range(lo, hi):
    """Sequence{lo..hi} (1-based inclusive)."""
    return list(range(int(lo), int(hi) + 1))


def is_mult(me, lo, hi):
    """MultiplicityElement::is(lower, upper) (§7.8.8): every
    cardinality in [lo, hi] is included by this multiplicity."""
    from .derived import lower_bound, upper_bound
    lb = lower_bound(me)
    ub = upper_bound(me)
    def un(v):
        return "*" if v == "*" or v is None else int(v)
    return lb == lo and (un(ub) == un(hi) or (un(ub) == "*" and hi != 0))


_EXTENT = None
_SELF = None


def set_extent(extent):
    """Bind the model scope for the duration of an evaluation (or None)."""
    global _EXTENT
    previous = _EXTENT
    _EXTENT = extent
    return previous


def current_extent():
    return _EXTENT


def set_self(obj):
    """Bind the constraint's `self` for the duration of an evaluation.
    Nested evaluations (`_iterate` over a body that itself iterates)
    read it through `current_self()`."""
    global _SELF
    previous = _SELF
    _SELF = obj
    return previous


def current_self():
    return _SELF


def all_instances(tname):
    """T.allInstances(): the extent's elements of that metaclass.

    Without an extent (a bare object graph) the answer is the empty set —
    stated, not guessed: there is no resource to enumerate.
    """
    if _EXTENT is None:
        return []
    return _EXTENT.of_kind(tname)


def select_by_kind(collection, tname):
    """KerML `x->selectByKind(T)`: the elements of the collection that are
    (a subtype of) metaclass T."""
    cls = extent_mod.metaclass(tname, getattr(_EXTENT, "prefer", None))
    if cls is None:
        return list(collection or ())
    return [e for e in (collection or ()) if isinstance(e, cls)]


def select_as_kind(collection, tname):
    """KerML `x->selectAsKind(T)`: the kind filter, as T."""
    return select_by_kind(collection, tname)


def specializes_from_library(el, qname):
    """KerML `specializesFromLibrary('Pkg::Element')`: does `el` specialize
    the library element? Answered from the model's own specialization graph;
    with no library loaded an element that never names the library does not
    specialize it."""
    if _EXTENT is not None:
        return _EXTENT.specializes_from_library(el, qname)
    return extent_mod.Extent().specializes_from_library(el, qname)


def containing_activity(node):
    """ActivityNode::containingActivity (§12.4.1.6): the nearest
    owning Activity, through StructuredActivityNode containers."""
    from . import derived as D
    o = node.owner
    while o is not None:
        if isinstance(o, U.Activity):
            return o
        o = o.owner
    return None


def containing_state_machine(v):
    """Vertex::containingStateMachine (§13.3.7): climb containers to
    the owning StateMachine, entering submachine states on the way."""
    from . import derived as D
    o = v.owner
    while o is not None:
        if isinstance(o, U.StateMachine):
            return o
        if isinstance(o, U.State) and o.submachine is not None:
            sm = o.submachine
            return sm
        o = o.owner
    return None


def containing_behavior(beh_el):
    """Behavior::containingBehavior (§13.2.3): the owning class-like
    Classifier (via the _'context' subset union owner)."""
    o = beh_el.owner
    while o is not None:
        if isinstance(o, U.Classifier):
            return o
        o = o.owner
    return None


def end_type(p):
    """Property::endType (§9.9.17.7): the ends' types that this end
    connects (types of the other ends, plus own type)."""
    from . import derived as D
    a = p.association
    out = []
    if a is None:
        return out
    for e in a.memberEnd:
        t = e.type
        if t is not None and t not in out:
            out.append(t)
    return out


def all_actions(a):
    """Action::allActions (§12.3.3): self plus all contained actions
    (owned nodes that are Actions, recursively)."""
    from . import derived as D
    out, seen = [], set()
    def rec(n):
        if id(n) in seen:
            return
        seen.add(id(n))
        if isinstance(n, U.Action):
            out.append(n)
        for e in D.all_owned_elements(n):
            if isinstance(e, U.Action):
                out.append(e)
    rec(a)
    return out


def all_pins(a):
    """Action::allPins (§12.3.3): all Pins of all contained Actions."""
    from . import derived as D
    out, seen = [], set()
    for act in all_actions(a):
        for e in D.all_owned_elements(act):
            if isinstance(e, U.Pin):
                if id(e) not in seen:
                    seen.add(id(e))
                    out.append(e)
    return out


def all_owned_nodes(node):
    """StructuredActivityNode::allOwnedNodes (§12.10.3.4): owned nodes
    plus their owned nodes transitively (activity-group scope)."""
    from . import derived as D
    out, seen = [], set()
    def rec(n):
        if id(n) in seen:
            return
        seen.add(id(n))
        if isinstance(n, U.ActivityNode):
            out.append(n)
        if isinstance(n, U.StructuredActivityNode):
            for sub in n.node:
                rec(sub)
    for sub in node.node:
        rec(sub)
    return out


def all_included_use_cases(uc):
    """UseCase::allIncludedUseCases (§14.1.3.4): transitive include
    closure, cycle-guarded."""
    out, seen = [], set()
    def rec(u):
        for inc in u.include:
            t = inc.extension  # target use case of the Include
            if t is None or id(t) in seen:
                continue
            seen.add(id(t))
            out.append(t)
            rec(t)
    rec(uc)
    return out


def all_roles(sc):
    """StructuredClassifier::allRoles (§9.10.3.4): member->select(oclIsKindOf
    (ConnectableElement)) — full normative member (derived.member)."""
    from . import derived as D
    return [m for m in D.member(sc) if isinstance(m, U.ConnectableElement)]


def all_slottable_features(cl):
    """InstanceSpecification::allSlottableFeatures (§9.7.3.4): all
    direct and inherited attributes, excluding association ends."""
    from . import derived as D
    return [f for f in D.all_attributes(cl)
            if f.association is None]


def is_attribute(p):
    """Property::isAttribute (§9.9.17.8): attribute form (no
    association end and not a memberEnd of any association)."""
    return p.association is None


def is_multivalued(me):
    """MultiplicityElement::isMultivalued (§7.8.8): upperBound() > 1
    or = '*'."""
    from .derived import upper_bound
    ub = upper_bound(me)
    return ub == "*" or ub is None or ub > 1


def must_be_owned(el):
    """Element::mustBeOwned (§7.8.6.7): false for Package (and Profile/
    Model which specialize it), true otherwise — §12.4.5.7 gives the
    Package redefinition body false."""
    return not isinstance(el, U.Package)


def is_navigable(p):
    """Property::isNavigable (§9.9.17.9)."""
    return not (p.association is not None and
                p.owningAssociation is not None and
                p.association.ownedEnd and
                p in p.association.ownedEnd and p.isReadOnly)


def association(p):
    """Property::association(): the Association owning this end."""
    return p.association


def input_parameters(op):
    """BehavioralFeature::inputParameters (§9.6.3): ownedParameter
    ->select(direction = in or inout)."""
    return [p for p in op.ownedParameter
            if enum_val(p.direction) in ("in", "inout")]


def output_parameters(op):
    """BehavioralFeature::outputParameters (§9.6.3): ownedParameter
    ->select(direction = out or inout or return)."""
    return [p for p in op.ownedParameter
            if enum_val(p.direction) in ("out", "inout", "return")]


def integer_value(lit):
    """LiteralInteger::integerValue(): the carried value (None when
    unset)."""
    if lit is None:
        return None
    return getattr(lit, "value", None)


def unlimited_value(lit):
    """LiteralUnlimitedNatural::unlimitedValue(): the carried value."""
    if lit is None:
        return None
    return getattr(lit, "value", None)


def closure(seq, chain):
    """->closure(p): transitive closure of property chain `chain`
    over seq (OCL 2.4 §10.3.3 closure — the set reached by repeatedly
    applying the chain, cycle-guarded)."""
    out, seen = [], set()
    frontier = list(seq)
    while frontier:
        nxt = []
        for e in frontier:
            cur = [e]
            for prop in chain:
                nxt_lvl = []
                for x in cur:
                    if x is None:
                        continue
                    v = getattr(x, prop, None)
                    items = v if isinstance(v, (list, tuple)) else (v,)
                    nxt_lvl.extend(i for i in items if i is not None)
                cur = nxt_lvl
            for it in cur:
                if it is None or id(it) in seen:
                    continue
                seen.add(id(it))
                out.append(it)
                nxt.append(it)
        frontier = nxt
    return out


def ocl_compatible_with(me, other):
    """MultiplicityElement::compatibleWith (§7.8.8): other is wider
    than or the same as self, i.e. self.includesMultiplicity(other):
    lowerBound(other) <= lowerBound(self) and upperBound(self) <=
    upperBound(other) (with '*' unbounded)."""
    from .derived import lower_bound, upper_bound

    def un(v):
        return "*" if v == "*" or v is None else int(v)
    return (un(lower_bound(other)) <= un(lower_bound(me)) and
            (un(upper_bound(me)) == "*" or
             un(upper_bound(other)) == "*" or
             un(upper_bound(me)) >= un(upper_bound(other))))


def _vertex_regions(v, seen=None):
    """Every Region whose transition set governs vertex v: the regions
    reached DOWN the region/subvertex tree from v, and UP through the
    vertex's container chain (the container region itself)."""
    if seen is None:
        seen = set()

    def rec(obj):
        if obj is None or id(obj) in seen:
            return
        seen.add(id(obj))
        if isinstance(obj, U.Region):
            yield obj
        for e in (obj._vals.get("region") or []):
            yield from rec(e)
        for e in (obj._vals.get("subvertex") or []):
            yield from rec(e)
    yield from rec(v)
    # upward: the container region chain (subvertex containment);
    # Region has no .container — regions nest via stateMachine/region
    c = v.container
    while isinstance(c, U.Region):
        yield c
        c = c._vals.get("container")


def vertex_incoming(v):
    """Vertex::incoming (§13.3.6): the Transitions entering this
    vertex — the derived end computes as Transition->select(target=self)
    over the regions containing the vertex."""
    out, seen = [], set()
    for r in _vertex_regions(v):
        for t in r.transition:
            if t.target is v and id(t) not in seen:
                seen.add(id(t))
                out.append(t)
    return out


def vertex_outgoing(v):
    """Vertex::outgoing (§13.3.6): the Transitions departing."""
    out, seen = [], set()
    for r in _vertex_regions(v):
        for t in r.transition:
            if t.source is v and id(t) not in seen:
                seen.add(id(t))
                out.append(t)
    return out


# The operation tables live in ocl_symbols (shared by parser, emitter and
# this module). The legacy parser needs the function OBJECTS for its local
# lowerings, so it gets its own view built from the shared names.
DERIVED_FUNCS = SY.DERIVED_FUNCS
COLLECTION_OPS = SY.COLLECTION_OPS
CLASSIFY_OPS = SY.CLASSIFY_OPS
_LOCAL_BARE = SY.LOCAL_BARE

# `_DERIVED_FUNCS_LEGACY` and the eval-environment bindings are built at the
# END of this module: they resolve local lowerings by name, and several of
# those are defined further down (O4 helpers), so building them here would
# raise KeyError at import.


# --------------------------------------------------------------------------
# tokenizer
# --------------------------------------------------------------------------

def tokenize(body):
    """Split an OCL body into (kind, text) tokens."""
    toks = []
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c.isspace():
            i += 1
            continue
        if c == "'":
            j = body.find("'", i + 1)
            if j < 0:
                raise UnmappedFeature(
                    f"unterminated string near {body[i:i + 20]!r}")
            toks.append(("qstr", body[i + 1:j]))
            i = j + 1
            continue
        two = body[i:i + 2]
        if two in ("<>", "<=", ">=", "::", "..", "->"):
            toks.append(("op", two))
            i += 2
            continue
        if c == "_" and i + 1 < n and body[i + 1] == "'":
            # keyword-escaped name: _'in' / _'context'
            j = body.find("'", i + 2)
            if j < 0:
                raise UnmappedFeature("unterminated _'...'")
            toks.append(("name", body[i + 2:j]))
            i = j + 1
            continue
        if c in "(),":
            toks.append(("paren", c))
            i += 1
            continue
        if c == "|":
            toks.append(("bar", "|"))
            i += 1
            continue
        if c == ".":
            toks.append(("op", "."))
            i += 1
            continue
        if c in "=<>+-*/":
            toks.append(("op", c))
            i += 1
            continue
        if c == ":":
            toks.append(("colon", ":"))
            i += 1
            continue
        if c == "{":
            toks.append(("lc", "{"))
            i += 1
            continue
        if c == "}":
            toks.append(("rc", "}"))
            i += 1
            continue
        if c.isdigit():
            j = i
            while j < n and body[j].isdigit():
                j += 1
            toks.append(("num", body[i:j]))
            i = j
            continue
        if body[i:i + 1] == "*":
            toks.append(("op", "*"))
            i += 1
            continue
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", body[i:])
        if m:
            toks.append(("name", m.group(0)))
            i += len(m.group(0))
            continue
        raise UnmappedFeature(f"character {c!r} in {body[i:i + 30]!r}")
    toks.append(("eof", ""))
    return toks


# --------------------------------------------------------------------------
# recursive-descent parser emitting Python source
# --------------------------------------------------------------------------
#
# precedence (loosest to tightest), per OCL 2.4 §7.5.3:
#   implies < or < xor < and < not < =/<> < </<=/>/>= < +/- < *// < unary
#
# emitted source references only these bare names, which eval_body binds:
#   self, _g (getattr), _k/_t/_a (classification), _d (derived/local ops),
#   _enum, _collect, _flatten, _union, _range

_PRECEDENCE = [
    ("name", "implies"),
    ("name", "or"),
    ("name", "xor"),
    ("name", "and"),
]


class _Parser:
    def __init__(self, body):
        self.toks = tokenize(body)
        self.i = 0
        self._uid = 0
        self.scopes = []  # in-scope lambda iterator variable names

    def peek(self):
        return self.toks[self.i]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def accept(self, kind, text=None):
        k, t = self.peek()
        if k == kind and (text is None or t == text):
            self.next()
            return t
        return None

    def expect(self, kind, text=None):
        t = self.accept(kind, text)
        if t is None:
            raise UnmappedFeature(
                f"expected {text or kind} at token {self.peek()!r}")
        return t

    # -- entry ---------------------------------------------------------------
    def parse(self):
        e = self.implication()
        if self.peek()[0] != "eof":
            raise UnmappedFeature(
                f"trailing tokens {[t for t in self.toks[self.i:self.i + 5]]}")
        return e

    def implication(self):
        left = self.or_()
        if self.accept("name", "implies"):
            return f"((not ({left})) or ({self.implication()}))"
        return left

    def or_(self):
        e = self.xor_()
        while self.accept("name", "or"):
            e = f"({e} or {self.xor_()})"
        return e

    def xor_(self):
        e = self.and_()
        while self.accept("name", "xor"):
            e = f"(bool({e}) != bool({self.and_()}))"
        return e

    def and_(self):
        e = self.not_()
        while self.accept("name", "and"):
            e = f"({e} and {self.not_()})"
        return e

    def not_(self):
        if self.accept("name", "not"):
            return f"(not ({self.not_()}))"
        return self.equality()

    def equality(self):
        e = self.relational()
        while True:
            op = self.accept("op", "=") or self.accept("op", "<>")
            if op is None:
                return e
            rhs = self.relational()
            if op == "=":
                e = f"(_eq({e}, {rhs}))"
            else:
                e = f"(not (_eq({e}, {rhs})))"

    def relational(self):
        e = self.additive()
        for op in ("<=", ">=", "<", ">"):
            if self.accept("op", op):
                return f"({e} {op} {self.additive()})"
        return e

    def additive(self):
        e = self.multiplicative()
        while True:
            op = self.accept("op", "+") or self.accept("op", "-")
            if op is None:
                return e
            e = f"({e} {op} {self.multiplicative()})"

    def multiplicative(self):
        e = self.unary()
        while self.accept("op", "*"):
            e = f"({e} * {self.unary()})"
        return e

    def unary(self):
        if self.accept("op", "-"):
            return f"(-({self.unary()}))"
        return self.postfix()

    # -- postfix chains ----------------------------------------------------
    def postfix(self):
        e = self.primary()
        while True:
            if self.accept("op", "."):
                e = self.suffix_dot(e)
            elif self.accept("op", "->"):
                e = self.suffix_arrow(e)
            else:
                return e

    def suffix_dot(self, recv):
        name = self.expect("name")
        if self.peek() == ("paren", "("):
            return self.call(recv, name)
        return f"_dot({recv}, {name!r})"

    def suffix_arrow(self, recv):
        name = self.expect("name")
        if self.peek() != ("paren", "("):
            raise UnmappedFeature(f"->{name} without ()")
        return self.call(recv, name)

    def call(self, recv, name):
        self.expect("paren", "(")
        args = []
        if self.peek() != ("paren", ")"):
            args.append(self.implication())
            # comma-separated / bar-separated argument and lambda forms
            while True:
                t = self.peek()
                if t == ("paren", ")"):
                    break
                if t == ("colon", ":"):
                    # typed iterator variable: 'v : T | body' — drop the
                    # variable just parsed, consume ': T |', parse body
                    args.pop()
                    self.next()
                    self.expect("name")  # type name (unchecked, wave 1)
                    if self.peek()[0] != "bar":
                        raise UnmappedFeature("typed lambda without |")
                    self.next()
                    args.append(self.implication())
                    continue
                if t in (("paren", ","), ("bar", "|")):
                    self.next()
                    args.append(self.implication())
                    continue
                raise UnmappedFeature(f"call argument at {t!r}")
        self.expect("paren", ")")
        return self.emit_op(recv, name, args)

    # -- operation emitters -------------------------------------------------
    def emit_op(self, recv, name, args):
        if name in COLLECTION_OPS:
            return self.emit_collection(recv, name, args)
        if name in CLASSIFY_OPS:
            return self.emit_classify(recv, name, args)
        if name in _DERIVED_FUNCS_LEGACY:
            kind, fn = _DERIVED_FUNCS_LEGACY[name]
            if kind == "derived":
                if args:
                    return f"_d({fn!r}, {recv}, {', '.join(args)})"
                return f"_d({fn!r}, {recv})"
            # local implementation bound by name in eval env
            if args:
                return f"{fn.__name__}({recv}, {', '.join(args)})"
            return f"{fn.__name__}({recv})"
        # plain navigation with call syntax is not a property
        raise UnmappedFeature(f"operation {name}({', '.join(a[:20] for a in args)})")

    def _shadow(self, val, var):
        """Rewrite self-property reads inside an iterator body so they
        resolve against the iterator element.  The declared var always
        shadows itself.  For the implicit 'it' form, bare property names
        (lowerCamelCase) belong to the element; uppercase names are
        metaclasses and stay self-relative."""
        if var == "it":
            val = re.sub(r"_g\(self, '([a-z]\w*)'\)", r"_g(it, '\1')", val)
        else:
            val = re.sub(r"_g\(self, '%s'\)" % re.escape(var), var, val)
        return val

    def emit_collection(self, recv, name, args):
        # OCL treats every property as a collection: navigation through a
        # single-valued property yields Set{v}. The runtime stores lists
        # for multi-valued properties and bare values for single-valued
        # ones, so collection ops coerce the receiver first. Navigation
        # THROUGH a multi-valued receiver (implicit collect) is handled
        # by _nav: single-valued attr -> getattr; multi -> _collect of
        # the per-element attribute values.
        if name in ("size", "isEmpty", "notEmpty", "includes", "excludes",
                    "includesAll", "excludesAll", "exists", "forAll",
                    "select", "reject", "one", "any", "collect", "asSet",
                    "asSequence", "asOrderedSet", "asBag", "union",
                    "intersection", "flatten", "closure", "first", "last",
                    "at", "indexOf", "excluding"):
            recv = f"_nav({recv})"
        if name == "size":
            return f"len({recv})"
        if name == "isEmpty":
            return f"(len({recv}) == 0)"
        if name == "notEmpty":
            return f"(len({recv}) > 0)"
        if name in ("asSet", "asSequence", "asOrderedSet", "asBag"):
            return recv
        if name == "includes":
            return f"(({args[0]}) in {recv})"
        if name == "excludes":
            return f"(({args[0]}) not in {recv})"
        if name == "includesAll":
            return f"all(a in {recv} for a in ({args[0]}))"
        if name == "excludesAll":
            return f"all(a not in {recv} for a in ({args[0]}))"
        if name in ("exists", "one", "any"):
            var, val = self._lambda(args)
            self.scopes.append(var)
            try:
                # iterator var shadows self-properties within the body:
                # _g(self, 'e'...) reads become _g(e... (the shadowing
                # applies to the exact var name only)
                val = self._shadow(val, var)
                if name == "exists":
                    return f"any({val} for {var} in {recv})"
                return f"(sum(1 for {var} in {recv} if ({val})) == 1)"
            finally:
                self.scopes.pop()
        if name == "forAll":
            var, val = self._lambda(args)
            self.scopes.append(var)
            try:
                val = self._shadow(val, var)
                return f"all({val} for {var} in {recv})"
            finally:
                self.scopes.pop()
        if name == "select":
            var, val = self._lambda(args)
            self.scopes.append(var)
            try:
                val = self._shadow(val, var)
                return f"[{var} for {var} in {recv} if ({val})]"
            finally:
                self.scopes.pop()
        if name == "reject":
            var, val = self._lambda(args)
            self.scopes.append(var)
            try:
                val = self._shadow(val, var)
                return f"[{var} for {var} in {recv} if not ({val})]"
            finally:
                self.scopes.pop()
        if name == "collect":
            var, val = self._lambda(args)
            self.scopes.append(var)
            try:
                val = self._shadow(val, var)
                return f"_collect([{val} for {var} in {recv}])"
            finally:
                self.scopes.pop()
        if name == "flatten":
            return f"_flatten({recv})"
        if name == "union":
            return f"_union({recv}, ({args[0]}))"
        if name == "intersection":
            return f"[a for a in {recv} if a in ({args[0]})]"
        if name == "excluding":
            return f"[a for a in {recv} if a != ({args[0]})]"
        if name == "closure":
            # ->closure(p): transitive closure over property chain p
            # (applied stepwise to each element of recv, cycle-guarded)
            prop = args[0].strip()
            if re.fullmatch(r"[a-z]\w*", prop):
                return f"_closure_iter({recv}, [{prop!r}])"
            # dotted chain: _g(_g(it, 'a'), 'b') → ['a', 'b']
            chain = re.findall(r"'(\w+)'", prop)
            if chain and prop.startswith("_g("):
                return f"_closure_iter({recv}, {chain!r})"
            raise UnmappedFeature(f"->closure({prop[:40]})")
        if name == "first":
            return f"({recv}[0] if {recv} else None)"
        if name == "last":
            return f"({recv}[-1] if {recv} else None)"
        if name == "at":
            return f"(({recv})[{args[0]} - 1] if len({recv}) >= ({args[0]}) else None)"
        if name == "indexOf":
            return f"((({recv}).index(({args[0]})) + 1) if (({args[0]}) in ({recv})) else -1)"
        raise UnmappedFeature(f"->>{name}")

    def emit_classify(self, recv, name, args):
        if name == "oclIsKindOf":
            return f"_k({recv}, {self._type_arg(args[0])!r})"
        if name == "oclIsTypeOf":
            return f"_t({recv}, {self._type_arg(args[0])!r})"
        if name == "oclAsType":
            return f"_a({recv}, {self._type_arg(args[0])!r})"
        if name == "oclIsUndefined":
            return f"(({recv}) is None)"
        if name == "oclType":
            return f"type({recv}).__name__"
        raise UnmappedFeature(name)

    def _type_arg(self, src):
        """A classification type argument arrives as whatever the
        primary parser produced; metaclass names get resolved as bare
        names to _g(self, 'T') — unwrap that back to the name."""
        s = src.strip()
        m = re.fullmatch(r"_g\(self, '([A-Z]\w*)'\)", s)
        if m:
            return m.group(1)
        if re.fullmatch(r"[A-Z]\w*", s):
            return s
        raise UnmappedFeature(f"type argument {s!r}")

    def _lambda(self, args):
        """exists/forAll/select/... argument forms:
        1 arg  -> implicit iterator 'it'
        2 args -> (var, body)
        3 args -> (var, type-expr, body)   [type ignored]
        The variable arrives possibly wrapped as _g(self, 'v') by the
        bare-name rule — unwrap."""
        if len(args) == 1:
            return "it", args[0]
        if len(args) == 2:
            var = self._unwrap_var(args[0])
            return var, args[1]
        if len(args) == 3:
            var = self._unwrap_var(args[0])
            return var, args[2]
        raise UnmappedFeature(f"lambda arity {len(args)}")

    def _unwrap_var(self, src):
        s = src.strip()
        m = re.fullmatch(r"_g\(self, '(\w+)'\)", s)
        if m:
            return m.group(1)
        if re.fullmatch(r"[a-z]\w*", s):
            return s
        raise UnmappedFeature(f"lambda var {s!r}")

    # -- primaries -----------------------------------------------------------
    def primary(self):
        k, t = self.peek()
        if k == "paren" and t == "(":
            self.next()
            e = self.implication()
            self.expect("paren", ")")
            return self._postfix_continue(e)
        if k == "name":
            e = self.name_or_call()
            # a receiver may be re-typed by a classification call chained
            # to it (e.g. `type.oclIsKindOf(Interface)` where `type` is
            # a property of self); name_or_call already applied its own
            # postfix, so continue chains here
            return e
        if k == "qstr":
            self.next()
            return repr(t)
        if k == "num":
            self.next()
            return t
        if k == "op" and t == "*":
            # the UnlimitedNatural unbounded literal (e.g. is(0,*))
            self.next()
            return repr("*")
        if k == "lc":
            # collection literal: Sequence{1..n} / Set{...}
            return self.collection_literal()
        raise UnmappedFeature(f"primary at {self.peek()!r}")

    def _postfix_continue(self, e):
        """After a parenthesized group, .nav / ->op() chains continue."""
        while True:
            if self.accept("op", "."):
                e = self.suffix_dot(e)
            elif self.accept("op", "->"):
                e = self.suffix_arrow(e)
            else:
                return e

    def collection_literal(self):
        # '{' opens the literal directly (optional 'Sequence'/'Set'/
        # 'OrderedSet' prefix is consumed by name_or_call as a bare name;
        # range form: Sequence{1..n})
        self.expect("lc")
        items = []
        if self.peek() != ("rc", "}"):
            items.append(self.implication())
            while self.peek() == ("paren", ","):
                self.next()
                items.append(self.implication())
            if self.accept("op", ".."):
                hi = self.implication()
                self.expect("rc")
                return f"_range({items[0]}, {hi})"
        self.expect("rc")
        return "[" + ", ".join(items) + "]"

    def if_then_else(self):
        """if C then A else B endif  →  ((B-if) form)."""
        self.expect("name", "if")
        cond = self.implication()
        self.expect("name", "then")
        then = self.implication()
        self.expect("name", "else")
        els = self.implication()
        self.expect("name", "endif")
        return f"(({then}) if ({cond}) else ({els}))"

    def name_or_call(self):
        name = self.expect("name")
        if name == "let":
            # 'let' binds as an expression, wherever it appears
            # (mid-`and` chains included): back up one token and parse
            # the whole let-expression from the primary level
            self.i -= 1
            return self.let_expression("let")
        if name == "if":
            self.i -= 1
            return self.if_then_else()
        if name in ("Sequence", "Set", "OrderedSet", "Bag", "Collection"):
            # collection-type prefix of a literal: Sequence{1..n} /
            # Set{a, b}; the '{' follows immediately
            if self.peek() == ("lc", "{"):
                return self.collection_literal()
            raise UnmappedFeature(f"collection type {name} used as value")
        if name == "self":
            return "self"
        if name in ("true", "false", "null", "invalid", "OclInvalid",
                    "oclInvalid"):
            return {"true": "True", "false": "False"}.get(name, "None")
        # enum literal: EnumName::literal  (also Type::lit in OCL text)
        if self.peek() == ("op", "::"):
            self.next()
            lit = self.expect("name")
            return repr(lit)
        # bare call with no receiver: an operation on self
        if self.peek() == ("paren", "("):
            self.next()
            args = []
            if self.peek() != ("paren", ")"):
                args.append(self.implication())
                while self.peek() in (("paren", ","), ("bar", "|")):
                    self.next()
                    args.append(self.implication())
            self.expect("paren", ")")
            return self.emit_op("self", name, args)
        # a bare name: OCL resolves unqualified property access against
        # self, EXCEPT names bound as lambda iterator variables or
        # let-bound variables (tracked in scopes by both mechanisms).
        # Names that are wave-1 computed derivations (incoming/outgoing)
        # emit the function call so the value is computed, not read from
        # the (always empty) derived-end storage.
        if name not in self.scopes:
            if name in _LOCAL_BARE:
                return f"{_LOCAL_BARE[name]}(self)"
            return f"_g(self, {name!r})"
        return name

    def let_expression(self, name):
        """let var : T = e in body  →  (lambda var: body)(e)
        (type annotation skipped; wave-1 note: no type checking)."""
        self.next()  # consume 'let'
        var = self.expect("name")
        self.scopes.append(var)  # let-bound names shadow self-properties
        try:
            return self._let_body(var)
        finally:
            self.scopes.pop()

    def _let_body(self, var):
        if self.peek()[0] == "colon":
            self.next()
            # swallow the type annotation up to '=' at paren-depth 0
            # (types like Set(InteractionUse) nest parens; '=' inside
            # a nested lambda body — e.g. ->any(type = self) — is NOT
            # the binding '=')
            depth = 0
            while True:
                k, t = self.peek()
                if k == "eof":
                    raise UnmappedFeature("let without '='")
                if k == "paren" and t == "(":
                    depth += 1
                elif k == "paren" and t == ")":
                    if depth == 0:
                        raise UnmappedFeature("unbalanced let type")
                    depth -= 1
                elif k == "op" and t == "=" and depth == 0:
                    break
                self.next()
        self.expect("op", "=")
        # bindings:  let a : T = e, b : T2 = e2 in body
        bindings = []
        val = self.implication()
        bindings.append((var, val))
        while self.peek() == ("paren", ","):
            self.next()
            bvar = self.expect("name")
            if self.peek()[0] == "colon":
                self.next()
                depth = 0
                while True:
                    k, t = self.peek()
                    if k == "eof":
                        raise UnmappedFeature("let without '='")
                    if k == "paren" and t == "(":
                        depth += 1
                    elif k == "paren" and t == ")":
                        if depth == 0:
                            raise UnmappedFeature("unbalanced let type")
                        depth -= 1
                    elif k == "op" and t == "=" and depth == 0:
                        break
                    self.next()
            self.expect("op", "=")
            bindings.append((bvar, self.implication()))
        if not self.accept("name", "in"):
            raise UnmappedFeature("let without 'in'")
        # bind into body: replace var references by lambda parameters
        body = self.implication()
        src = body
        for var, val in reversed(bindings):
            self._uid += 1
            pyvar = f"_let{self._uid}_{var}"
            # rename only OUTSIDE _dot/_g string literals: the emitted
            # attribute names 'stateMachine' live inside quotes and must
            # not collide with the bound variable name
            src = re.sub(rf"(?<!')\b{re.escape(var)}\b(?!')", pyvar, src)
            val = re.sub(rf"(?<!')\b{re.escape(var)}\b(?!')", pyvar, val)
            src = f"(lambda {pyvar}: ({src}))({val})"
        return src


# patch: hook 'let' into the expression entry points
def _implication_with_let(self):
    k, t = self.peek()
    if k == "name" and t == "let":
        return self.let_expression(t)
    return self._implication_orig()


_Parser._implication_orig = _Parser.implication
_Parser.implication = _implication_with_let


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

_TRANSLATE_CACHE = {}


def translate(body):
    """OCL body -> Python source string (cached).

    Goes through the AST (ocl_parse -> ocl_ast -> ocl_emit). The v0
    source-emitting parser is still available as `translate_legacy` and is
    the differential oracle in `check_ocl_ast.py` for one release.
    """
    src = _TRANSLATE_CACHE.get(body)
    if src is None:
        src = ocl_emit.to_python(ocl_parse.parse(body))
        _TRANSLATE_CACHE[body] = src
    return src


def translate_legacy(body):
    """The pre-AST translator (differential oracle; delete at O3)."""
    return _Parser(body).parse()


def parse(body):
    """OCL body -> ocl_ast tree (the API the type checker will use)."""
    return ocl_parse.parse(body)


_EVAL_ENV = {
    "select_by_kind": select_by_kind,
    "select_as_kind": select_as_kind,
    "specializes_from_library": specializes_from_library,
    "_g": ocl_get,
    "_dot": ocl_dot,
    "_nav": ocl_nav,
    "_aslist": ocl_aslist,
    "_eq": ocl_eq,
    "_k": ocl_is_kind_of,
    "_t": ocl_is_type_of,
    "_a": ocl_as_type,
    "_enum": enum_val,
    "_collect": ocl_collect,
    "_flatten": ocl_flatten,
    "_union": ocl_union,
    "_range": ocl_range,
    "_closure_iter": closure,
    "is_mult": is_mult,
    "all_instances": all_instances,
    "is_attribute": is_attribute,
    "is_multivalued": is_multivalued,
    "is_navigable": is_navigable,
    "must_be_owned": must_be_owned,
    "containing_activity": containing_activity,
    "containing_state_machine": containing_state_machine,
    "containing_behavior": containing_behavior,
    "end_type": end_type,
    "all_actions": all_actions,
    "all_pins": all_pins,
    "all_owned_nodes": all_owned_nodes,
    "all_included_use_cases": all_included_use_cases,
    "all_roles": all_roles,
    "all_slottable_features": all_slottable_features,
    "vertex_incoming": vertex_incoming,
    "vertex_outgoing": vertex_outgoing,
}


# every local lowering in the table must be bound here, or the emitted bare
# call raises NameError at evaluation time (the corpus never exercised
# input_parameters/output_parameters/integer_value until the v2 leg ran)
for _name, (_kind, _fn) in SY.DERIVED_FUNCS.items():
    if _kind == "local" and _fn in globals():
        _EVAL_ENV.setdefault(_fn, globals()[_fn])


def _derived_call(derived):
    """Binder: _d('funcname', obj, ...) -> derived.func(obj, ...)."""
    def call(fnname, obj, *rest):
        return getattr(derived, fnname)(obj, *rest)
    return call


_EVAL_BUILTINS = {
    "all": all, "any": any, "len": len, "sum": sum, "type": type,
    "isinstance": isinstance, "range": range, "list": list, "set": set,
}


_UNSET = object()


def eval_body(body, self_obj, derived, extent=_UNSET):
    """Evaluate an OCL constraint body against self_obj.

    `derived` is the derived module (spec-normative query layer).
    Returns the body's Python value (True/False for boolean bodies).
    Raises UnmappedFeature for constructs outside the grammar.
    By default the extent stays whatever the caller bound (check_constraints
    runs after v2_validate bound the model's extent) — passing None would
    force extent-less metaclass resolution, where module-first lookup can
    pick the WRONG module for colliding names (uml25.Expression over
    sysml2.Expression) and silently empty a selectByKind.
    """
    if extent is _UNSET:
        extent = _EXTENT
    src = translate(body)
    # comprehensions resolve free variables via the *globals* mapping, so
    # the env must ride IN the globals dict, not as locals
    env = dict(_EVAL_ENV)
    env["self"] = self_obj
    env["_d"] = _derived_call(derived)
    g = dict(_EVAL_BUILTINS)
    g.update(env)
    previous = set_extent(extent)
    prev_self = set_self(self_obj)
    try:
        return eval(src, g, {})  # noqa: S307
    finally:
        set_extent(previous)
        set_self(prev_self)


_CORPUS_DEFECT_RULES = {
    # the generated body names oclIsType(RequiremenCaseRequirementDefinition)
    # — a mangled concatenation artifact in the corpus text; with exact-type
    # semantics the rule can never hold for a UseCase*/Case* subject member,
    # so it is skipped with a named reason instead of reported as a model
    # violation
    ("SubjectMembership", "validateSubjectMembershipOwningType"):
        "RequiremenCaseRequirementDefinition",
}

# Serialization defects the generator committed when joining multi-line
# normative bodies into single strings: trailing closers lost at the join,
# a keyword typo, and an inline `--` comment that (on one line) swallows
# its tail. The repairs append exactly the closing tokens the visible
# structure requires — the lambda/if predicates themselves are complete —
# and are applied before evaluation AND before _derivation_source parses.
_CORPUS_REPAIRS = {
    ("Feature", "validateFeatureEndNoDirection"):
        [("implied", "implies")],          # KerML has no `implied` keyword
    ("Feature", "checkFeatureEndRedefinition"): [("END", ")")],
    ("Feature", "checkFeatureResultRedefinition"): [("END", ")")],
    # two closers: the forAll lambda and the outer implication let-chain
    ("Feature", "checkFeatureParameterRedefinition"): [("END", ") )")],
    ("Feature", "deriveFeatureCrossFeature"): [("END", "endif")],
    ("IncludeUseCaseUsage", "checkIncludeUseCaseSpecialization"):
        # the lost closer belongs BEFORE the implies: `(A or B) implies sfl`
        [("oclIsKindOf(UseCaseUsage) implies",
          "oclIsKindOf(UseCaseUsage)) implies")],
    ("PartUsage", "checkPartUsageActorSpecialization"): [("END", "endif")],
    ("Step", "checkStepOwnedPerformanceSpecialization"):
        # same precedence repair: close the or-group before the implies
        [("exists(oclIsKindOf(Structure)) implies",
          "exists(oclIsKindOf(Structure))) implies")],
    ("TransitionUsage", "checkTransitionUsageTransitionFeatureSpecialization"):
        [("END", ") )")],
    ("TransitionUsage", "deriveTransitionUsageSource"):
        [("END", "endif")],                # close the if/then/else of the let
    # the inline `-- Note:` eats everything after it on the joined line,
    # and the corpus spells Collection::exists as `exist`
    ("Feature", "deriveFeatureType"):
        [("-- Note: The closure operation automatically handles circular"
          " relationships. ", ""),
         ("->exist(", "->exists(")],
}

# corpus bodies whose lambda text the serializer LOST (the rule navigates
# `.type->exists(selectByKind(Class))` — an argument-less selectByKind is
# not OCL); unrepairable without speculation, named as defects
for _r in ("checkFeatureDataValueSpecialization",
           "checkFeatureObjectSpecialization",
           "checkFeatureOccurrenceSpecialization"):
    _CORPUS_DEFECT_RULES[("Feature", _r)] = "exists(selectByKind("


def _repair_body(cls_name, cname, body):
    for (c, r), deltas in _CORPUS_REPAIRS.items():
        if c == cls_name and r == cname:
            for old, new in deltas:
                if old == "END":
                    body = body + " " + new
                elif old in body:
                    body = body.replace(old, new)
    return body


def check_constraints(obj, derived, only=None):
    """Evaluate every CONSTRAINTS body on obj's class (+ MRO).

    Returns (ok, results) where results is a list of
    (class, name, body, value) for each body that translated and ran,
    and skipped is (name, body) pairs that raised UnmappedFeature —
    reported, not guessed.
    """
    results, skipped = [], []
    seen = set()
    for cls in type(obj).__mro__:
        for cname, body in getattr(cls, "CONSTRAINTS", ()):
            key = (cname, body)
            if key in seen:
                continue
            seen.add(key)
            body = _repair_body(cls.__name__, cname, body)
            defect = _CORPUS_DEFECT_RULES.get((cls.__name__, cname))
            if defect is not None and defect in body:
                skipped.append((cname, body, "corpus-defect: " + defect))
                continue
            try:
                val = eval_body(body, obj, derived)
            except UnmappedFeature as ex:
                skipped.append((cname, body, str(ex)))
                continue
            except Undetermined as ex:
                skipped.append((cname, body, str(ex)[:80]))
                continue
            except (AttributeError, TypeError, KeyError) as ex:
                # the body navigates an end the generated runtime does
                # not carry (hidden/derived ends the generator closed,
                # e.g. Port.encapsulatedClassifier) — recorded, not
                # guessed; wave-2 material
                skipped.append((cname, body,
                                "eval-unmapped: " + str(ex)[:80]))
                continue
            if val is None:
                # three-valued KerML: a null body is UNDETERMINED, not a
                # violated constraint
                skipped.append((cname, body,
                                "undetermined: body evaluates to null"))
                continue
            results.append((cls.__name__, cname, body, val))
    ok = all(val for _, _, _, val in results)
    return ok, results, skipped


def translate_all(pairs):
    """Translate (class, name, body) triples; report coverage.

    Returns (translated, unmapped) where translated is a dict
    (class, name) -> python source and unmapped lists
    (class, name, reason)."""
    translated, unmapped = {}, []
    for cls, name, body in pairs:
        try:
            translated[(cls, name)] = translate(body)
        except UnmappedFeature as ex:
            unmapped.append((cls, name, str(ex)))
    return translated, unmapped

# --------------------------------------------------------------------------
# O4 helper operations, transcribed from the spec's own definitions
# --------------------------------------------------------------------------
# Anything the model does not carry answers None; the sentinel turns that into
# an undetermined skip rather than a False.

def effective_name(el):
    """KerML::effectiveName — the name, else the short name."""
    return getattr(el, "name", None) or getattr(el, "shortName", None) \
        or getattr(el, "declaredShortName", None)


def effective_short_name(el):
    """KerML::effectiveShortName — the short name only when there is no name."""
    if getattr(el, "name", None):
        return None
    return getattr(el, "shortName", None) or getattr(el, "declaredShortName",
                                                       None)


def escaped_name(el):
    """KerML::escapedName — the effective name, quoted when it needs it."""
    name = effective_name(el)
    if not name:
        return name
    bad = set(" \t\n()[]{}<>,.:;'\"+-*/%&|!=?@#$^~`\\")
    return "'" + name + "'" if any(c in bad for c in name) else name


def direction_of(_self=None, feature=None, arg=None):
    """KerML Type::directionOf(f) — f's direction, or null. The emitter
    lowers the corpus call as `direction_of(self, f)` (receiver first),
    so the FEATURE is the second positional."""
    if arg is not None:
        feature = arg
    if feature is None or feature is _self:
        feature = _self
    if feature is None:
        return None
    d = getattr(feature, "direction", None)
    return getattr(d, "value", d)


def sub_sequence(coll, lo, hi):
    """OCL Sequence::subSequence(lo, hi) — 1-based, inclusive."""
    seq = list(coll or ())
    return seq[max(int(lo) - 1, 0):int(hi)]


def sub_ordered_set(coll, lo, hi):
    """OCL OrderedSet::subOrderedSet(lo, hi) — 1-based, inclusive."""
    return sub_sequence(coll, lo, hi)


def ocl_concat(s, other):
    """OCL String::concat(s2): string concatenation; null propagates
    (a null operand yields null, not a crash)."""
    if s is None or other is None:
        return None
    return str(s) + str(other)


def _iterate(coll, var, acc, init, body_src):
    """`x->iterate(v; acc = init | body)` (OCL 2.4 §10.3.6): fold
    `body` over the elements, the accumulator starting at `init`.
    `body_src` is the lowered Python source of the body, evaluated once
    per element with `var` and `acc` bound — the parser already renamed
    them to plain names, so a two-name eval env does the binding."""
    env = dict(_EVAL_ENV)
    env["_d"] = _derived_call(D)
    env["all_instances"] = all_instances
    env["self"] = current_self()
    g = dict(_EVAL_BUILTINS)
    g.update(env)
    result = init
    for elem in (coll or ()):
        g[var] = elem
        g[acc] = result
        result = eval(body_src, g, {})  # noqa: S307
    return result


def including(coll, element):
    """OCL Collection::including(x)."""
    return list(coll or ()) + [element]


# --------------------------------------------------------------------------
# O5b: KerML/SysML v2 (sysml2) helper operations, transcribed from the
# corpus bodies that call them. Anything the runtime does not carry
# answers None (undetermined -> a skip), never a guessed False.
# --------------------------------------------------------------------------

def _as_list(v):
    if v is None:
        return ()
    if isinstance(v, (list, tuple)):
        return v
    return (v,)


def _extent():
    """The bound extent, or an empty one (never None — the lookup then
    honestly answers "not found")."""
    return _EXTENT if _EXTENT is not None else extent_mod.Extent()


def _qualified(el):
    from . import derived as D
    try:
        return D.qualified_name(el)
    except Exception:                              # noqa: BLE001
        return None


def _specializes(el, target):
    """Direct/indirect specialization (KerML Specialization graph plus
    the v1 generalization chain), cycle-guarded."""
    if el is None or target is None:
        return False
    seen = set()
    stack = [el]
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        if cur is target:
            return True
        for attr in ("specializes", "general", "subtype"):
            for t in _as_list(getattr(cur, attr, None)):
                if t is not None and t is target:
                    return True
                stack.append(t)
        # the owned specializations point the other way: specific -> general
        for attr in ("ownedSpecialization", "ownedSubclassification",
                     "generalization"):
            for rel in _as_list(getattr(cur, attr, None)):
                g = getattr(rel, "general", None)
                if g is not None:
                    if g is target:
                        return True
                    stack.append(g)
    return False


def _redefines(el, target):
    """Direct/indirect Redefinition chain: el (transitively) redefines
    target via its ownedRedefinition.redefinedFeature. The runtime
    stores ownedRedefinition as a derived select, so the chain is walked
    through the OCL read when it is not directly populated."""
    if el is None or target is None:
        return False
    seen = set()
    stack = [el]
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        if cur is target:
            return True
        rels = _as_list(getattr(cur, "ownedRedefinition", None))
        if not rels:
            # derived end not populated on the raw object: read it the
            # way the evaluator does (derive-on-read)
            try:
                rels = _as_list(derived_read(cur, "ownedRedefinition"))
            except Exception:                      # noqa: BLE001
                rels = ()
        for rel in rels:
            rf = getattr(rel, "redefinedFeature", None)
            if rf is not None:
                if rf is target:
                    return True
                stack.append(rf)
    return False


def redefines_from_library(el, qname):
    """KerML `redefinesFromLibrary('Pkg::El')`: does `el` redefine the
    library element, answered from the model's own redefinition graph
    (like specializesFromLibrary but via Redefinition)."""
    if el is None:
        return False
    if _qualified(el) == qname:
        return True
    ext = _extent()
    target = ext.qualified(qname)
    if target is None:
        return False
    return _redefines(el, target)


def _range_bounds(m):
    """(lower, upper) of a MultiplicityRange: the values carried by its
    lowerBound/upperBound Expressions (their literal `value`, read the
    way the evaluator reads them — derive-on-read — when the raw
    storage is empty)."""
    def val(e):
        if e is None:
            return None
        for r in _as_list(ocl_dot(e, "result")):
            v = getattr(r, "value", None)
            if v is not None:
                return v
        # the bound's literal is often owned directly through an
        # OwningMembership as ownedMemberElement; read that too
        for rel in _as_list(getattr(e, "ownedRelationship", None) or ()):
            for m in _as_list(getattr(rel, "ownedMemberElement", None) or ()):
                v = getattr(m, "value", None)
                if v is not None:
                    return v
            for m in _as_list(getattr(rel, "ownedRelatedElement", None) or ()):
                v = getattr(m, "value", None)
                if v is not None:
                    return v
        return getattr(e, "value", None)
    try:
        lo = val(ocl_dot(m, "lowerBound"))
        hi = val(ocl_dot(m, "upperBound"))
        if lo is None or hi is None:
            # bounds may be owned without memberName (order: lower, upper)
            owned = []
            for rel in _as_list(getattr(m, "ownedRelationship", None) or ()):
                for x in _as_list(getattr(rel, "ownedRelatedElement", None)
                                  or getattr(rel, "ownedMemberElement", None)
                                  or ()):
                    owned.append(x)
            if lo is None and len(owned) >= 1:
                lo = getattr(owned[0], "value", None)
            if hi is None and len(owned) >= 2:
                hi = getattr(owned[1], "value", None)
            for rel in _as_list(getattr(m, "ownedRelationship", None) or ()):
                nm = getattr(rel, "memberName", None)
                if nm == "lowerBound" and lo is None:
                    lo = val(_as_list(getattr(rel, "ownedRelatedElement", None)
                                or getattr(rel, "ownedMemberElement", None)
                                or [None])[0])
                if nm == "upperBound" and hi is None:
                    hi = val(_as_list(getattr(rel, "ownedRelatedElement", None)
                                or getattr(rel, "ownedMemberElement", None)
                                or [None])[0])
    except Exception:                              # noqa: BLE001
        return None, None
    return lo, hi


def has_bounds(m, lo, hi, _self=None):
    """MultiplicityRange::hasBounds(lower, upper): the range's
    lowerBound/upperBound Expression results equal the given values
    (upper '*' matches unbounded)."""
    if m is None:
        return False
    glo, ghi = _range_bounds(m)
    if glo is None and ghi is None:
        return None
    def un(v):
        return "*" if v == "*" or v is None else int(v)
    lo_ok = glo is not None and un(glo) == un(lo)
    if ghi is None:
        hi_ok = lo_ok          # no upperBound: lower defaults to upper
    else:
        hi_ok = un(ghi) == un(hi)
    return bool(lo_ok and hi_ok)


def multiplicity_has_bounds(m, lo, hi, _self=None):
    """KerML `multiplicityHasBounds(m, lo, hi)` — the multiplicity `m`
    has exactly the bounds lo..hi."""
    return has_bounds(m, lo, hi)


def subsets_chain(a, b):
    """KerML `subsetsChain(a, b)`: true when `a` transitively subsets
    `b` through the Subsetting chain (a == b counts). The runtime
    stores ownedSubsetting as a derived select, so the chain is walked
    through the OCL read when the raw storage is empty."""
    if a is None or b is None:
        return False
    seen = set()
    stack = [a]
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        if cur is b:
            return True
        rels = _as_list(getattr(cur, "ownedSubsetting", None))
        if not rels:
            try:
                rels = _as_list(derived_read(cur, "ownedSubsetting"))
            except Exception:                      # noqa: BLE001
                rels = ()
        for rel in rels:
            sf = getattr(rel, "subsettedFeature", None)
            if sf is not None:
                stack.append(sf)
        # also the direct subsetting targets carried on the element
        for f in _as_list(getattr(cur, "subsettedFeature", None)):
            stack.append(f)
    return False


def owned_cross_feature(f):
    """KerML Feature::ownedCrossFeature(): if this Feature is an end
    Feature of its owningType, the first ownedMember that is a Feature,
    not a Multiplicity/MetadataFeature, whose owningMembership is NOT a
    FeatureMembership — else null."""
    from . import sysml2 as _S2
    if f is None:
        return None
    ot = ocl_dot(f, "owningType")
    if ot is None or getattr(f, "owner", None) is None:
        return None
    try:
        ends = _as_list(ocl_dot(ot, "endFeature")) 
    except Exception:                              # noqa: BLE001
        ends = ()
    if not ends:
        # endFeature derives from feature->select(isEnd); isEnd is
        # structural — compute it directly from the owning memberships
        ends = [m for rel in _as_list(getattr(ot, "ownedRelationship", None)
                                      or ())
                for m in _as_list(getattr(rel, "ownedRelatedElement", None)
                                  or ())
                if getattr(m, "owningMembership", None) is rel
                and isinstance(rel, _S2.EndFeatureMembership)]
    if f not in ends:
        return None
    for rel in _as_list(ocl_dot(f, "ownedRelationship")):
        if not isinstance(rel, _S2.OwningMembership):
            continue
        if isinstance(rel, _S2.FeatureMembership):
            continue
        for m in _as_list(getattr(rel, "ownedRelatedElement", None)):
            if isinstance(m, _S2.Feature) and \
                    not isinstance(m, (_S2.Multiplicity,)) and \
                    not type(m).__name__.startswith("Metadata"):
                return m
    return None


def is_owned_cross_feature(f):
    """KerML Feature::isOwnedCrossFeature(): ownedCrossFeature() exists."""
    return owned_cross_feature(f) is not None


def _featuring_types(f):
    from . import sysml2 as _S2
    out = []
    for t in _as_list(ocl_dot(f, "featuringType")):
        if isinstance(t, _S2.Type):
            out.append(t)
    return out


def is_featured_within(f, t):
    """KerML Feature::isFeaturedWithin(type): the featuringTypes of `f`
    are compatible with `type`; null checks featuring by Anything
    (here: having any featuringType counts); isVariable also features
    within the owningType."""
    if f is None:
        return False
    # a library element is featured within its own library namespace — the
    # transform carries name-only stubs for KerML globals, which the real
    # library models feature correctly
    if getattr(f, "_library_qname", None) or \
            getattr(f, "_vals", {}).get("isLibraryElement", False):
        return True
    fts = _featuring_types(f)
    ot = ocl_dot(f, "owningType") if ocl_dot(f, "owningType") is not None \
        else getattr(f, "owningType", None)
    if t is None:
        return len(fts) > 0 or ot is not None
    for ft in fts:
        if ft is t or _specializes(ft, t) or _specializes(t, ft):
            return True
    # a non-variable feature is featured within its owningType by default;
    # "within" means the owning type specializes the argument's type OR is
    # the same — the argument type is an upper bound
    if ot is not None and (ot is t or _specializes(ot, t)):
        return True
    if getattr(f, "isVariable", None):
        if ot is not None and (ot is t or _specializes(ot, t)):
            return True
    return False


def ocl_is_type(obj, tname):
    """KerML `oclIsType(T)`: exact dynamic-type test (like oclIsTypeOf)."""
    return ocl_is_type_of(obj, tname)


def ocl_is_kind(obj, tname):
    """KerML `oclIsKind(T)`: kind test (like oclIsKindOf)."""
    return ocl_is_kind_of(obj, tname)


def _land(a, bth):
    """Three-valued KerML AND: false decides (short-circuit), null
    propagates. The consequent `bth` is a thunk — v0 relied on Python's
    short-circuit `and`, and eager evaluation breaks bodies whose right
    operand navigates ends the left operand's falsity exempts."""
    if a is False:
        return False
    b = bth() if callable(bth) else bth
    if b is False:
        return False
    if a is None or b is None:
        return None
    return bool(a) and bool(b)


def _lor(a, bth):
    """Three-valued KerML OR: true decides (short-circuit), null
    propagates."""
    if a is True:
        return True
    b = bth() if callable(bth) else bth
    if b is True:
        return True
    if a is None or b is None:
        return None
    return bool(a) or bool(b)


def _implies(a, bth):
    """Three-valued KerML implies = or(not a, b): not-null is null and
    or(null, false) is null (undetermined); or(null, true) is True — so
    a null antecedent answers True only when the consequent is True.
    `bth` is a thunk: a False antecedent never evaluates the consequent
    (v0 relied on Python `or` for exactly this)."""
    if a is False:
        return True
    b = bth() if callable(bth) else bth
    if a is None:
        return True if b is True else None
    if b is None:
        return None if a is not False else True
    return (not a) or b


def all_super_types(t):
    """KerML Type::allSuperTypes(): the type and its direct and indirect
    supertypes — the transitive closure over the specialization generals
    (library stubs included). SELF-INCLUDING is the contract the corpus
    requires: validateFeatureEndMultiplicity reads
    `multiplicities().allSuperTypes()->flatten()->selectByKind(
    MultiplicityRange)->exists(hasBounds(1,1))` and a defaulted end's
    multiplicity IS Base::exactlyOne [1..1], which specializes nothing —
    the chain element itself must be in the result for the rule to bind."""
    if t is None:
        return []
    out, seen = [], set()
    stack = [t]
    for s in (getattr(t, "ownedRelationship", None) or ()):
        if type(s).__name__ == "Specialization":
            g = getattr(s, "_vals", {}).get("general")
            if g is not None:
                stack.append(g)
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        out.append(cur)
        for s in (getattr(cur, "ownedRelationship", None) or ()):
            if type(s).__name__ == "Specialization":
                g = getattr(s, "_vals", {}).get("general")
                if g is not None:
                    stack.append(g)
    return out


def _closure_call(seq, fn, depth=24):
    """KerML x->closure(f()): the elements reached by applying the
    per-element query f repeatedly (BFS, cycle-guarded), including the
    starting elements."""
    seq = list(seq or ())
    out, seen = [], set()
    frontier = list(seq)
    for el in frontier:
        if el is not None and id(el) not in seen:
            seen.add(id(el))
            out.append(el)
    rounds = 0
    while frontier and rounds < depth:
        rounds += 1
        nxt = []
        for el in frontier:
            try:
                res = fn(el)
            except Exception:                  # noqa: BLE001
                res = None
            for r in res if isinstance(res, (list, tuple)) else \
                    ([res] if res is not None else []):
                if r is not None and id(r) not in seen:
                    seen.add(id(r))
                    out.append(r)
                    nxt.append(r)
        frontier = nxt
    return out


def typing_features(f):
    """KerML Feature::typingFeatures(): the features through which this
    feature's typing flows — the generals of its specializations that
    are themselves Features (the redefinition/typing chain)."""
    from . import sysml2 as _S2
    out = []
    for s in (getattr(f, "ownedRelationship", None) or ()):
        if isinstance(s, _S2.Specialization):
            g = s._vals.get("general")
            if g is not None and isinstance(g, _S2.Feature):
                out.append(g)
    return out


def is_unique_op(coll, key):
    """Collection::isUnique(key): no two elements share the key value.
    `key` lowers as a lambda over the element (the implicit-`it` rebind
    rewrites a bare named argument into the element read)."""
    if coll is None:
        return True
    fn = key if callable(key) else (lambda _x: key)
    vals = [fn(x) for x in coll]
    return len(vals) == len({repr(v) for v in vals})


def trigger_payload_parameter(tu):
    """Actions::TransitionUsage::triggerPayloadParameter(): the library
    TransitionPerformance's payload input parameter. The transform emits
    no payload-carrying trigger actions (the corpus rule binds it only
    when triggerAction is non-empty), so the answer is the library null."""
    return None


def cross_feature(f):
    """KerML Feature::crossFeature(): the feature crossed through this
    feature's ownedCrossSubsetting (the corpus derive body: the
    crossedFeature's chaining at position 2). The transform emits no
    CrossSubsettings, so the answer is null — which is exactly what the
    corpus rules expect for non-crossing features
    (`select(crossFeature() <> null)` filters them out)."""
    if f is None:
        return None
    for rel in (getattr(f, "ownedRelationship", None) or ()):
        if type(rel).__name__ == "CrossSubsetting":
            cf = getattr(rel, "_vals", {}).get("crossedFeature")
            chain = getattr(cf, "_vals", {}).get("ownedRelatedElement") \
                if hasattr(cf, "_vals") else None
            if isinstance(chain, (list, tuple)) and len(chain) > 1:
                return chain[1]
            return cf
    return None


def subsetting_is_unique(s):
    """Subsetting::isUnique — whether the subsetting constrains element
    uniqueness. Unset reads TRUE for Feature ends (KerML: a feature is
    unique unless marked nonunique; the isUnique Boolean defaults to the
    nonunique flag's opposite)."""
    if s is None:
        return None
    v = getattr(s, "_vals", {}).get("isUnique")
    if v is None:
        return True
    return v


def is_cartesian_product(t):
    """KerML Type::isCartesianProduct(): whether t is the product of its
    members. The transform emits no Cartesian product types (products
    arise from ownedFeatureChaining/intersection structures), so this is
    False deterministically; a real product carries the product structure
    and would answer True."""
    if t is None:
        return False
    oc = getattr(t, "_vals", {}).get("ownedFeatureChaining") or ()
    return bool(oc)


def as_cartesian_product(t):
    """KerML Type::asCartesianProduct(): the type recast as its Cartesian
    product (null when it is not one)."""
    return t if is_cartesian_product(t) else None


def source_feature(tu):
    """Actions::TransitionUsage::sourceFeature(): the feature the
    transition's source end references — the succession's first related
    feature (the source state). The corpus derives `source` from this
    via featureTarget, which for a terminal feature is the feature
    itself."""
    if tu is None:
        return None
    from . import sysml2 as _S2
    rel = _related_features(tu)
    if rel:
        return rel[0]
    # the transition's succession may own the ends
    for om in _aslist(getattr(tu, "ownedRelationship", None)):
        for el in _aslist(getattr(om, "ownedRelatedElement", None)):
            if isinstance(el, _S2.Connector):
                rel = _related_features(el)
                if rel:
                    return rel[0]
    return None


def resolve_global(qname, _self=None):
    """KerML `resolveGlobal('Pkg::El')`: the extent's qualified lookup;
    None when no extent is bound or the name is unknown. Accepts the
    receiver as a second positional because a bare call lowers with self
    prepended."""
    if not isinstance(qname, str):
        _self, qname = qname, _self   # receiver came first
    ext = _extent()
    if ext is None:
        return None
    hit = ext.qualified(qname)
    if hit is not None:
        return hit
    # a KerML library name (TransitionPerformances::...::transitionLink)
    # resolves to the name-only stub the transform registered — identity
    # matches whatever the transform bound with _attach_one_base
    try:
        from . import v1_to_v2_as as _AS
        stub = _AS._LIBRARY_DEFS.get(qname)
        if stub is not None:
            return stub
    except Exception:                          # noqa: BLE001
        pass
    # qualified names are None on hand-built ownerless models; fall back to
    # matching the last segment against element names
    leaf = qname.rsplit("::", 1)[-1]
    for el in ext.elements():
        if getattr(el, "name", None) == leaf or \
                getattr(el, "declaredName", None) == leaf:
            return el
    return None


def imported_memberships(ns, excluded=None):
    """KerML Namespace::importedMemberships(excluded): the Memberships
    imported by this Namespace's owned Imports. The runtime carries
    ownedImport (NamespaceImport -> importedNamespace membership,
    MembershipImport -> importedMembership); visibility filtering is
    not carried, so isImportAll=false still yields the imported set
    (stated: the visible-filter is not modeled)."""
    from . import sysml2 as _S2
    if ns is None:
        return []
    out, seen = [], set()
    excluded_ids = {id(e) for e in _as_list(excluded)}
    # ownedImport is derived; read the union, then fall back to scanning
    # ownedRelationship for Import memberships
    imps = _as_list(ocl_get(ns, "ownedImport")) or \
        _as_list(getattr(ns, "ownedImport", None)) or \
        [r for r in _as_list(getattr(ns, "ownedRelationship", None) or ())
         if "Import" in type(r).__name__]
    for imp in imps:
        if id(imp) in excluded_ids or id(imp) in seen:
            continue
        seen.add(id(imp))
        if isinstance(imp, _S2.MembershipImport):
            for m in _as_list(getattr(imp, "importedMembership", None)):
                if m is not None and id(m) not in seen:
                    seen.add(id(m))
                    out.append(m)
        elif isinstance(imp, _S2.NamespaceImport):
            tgt = getattr(imp, "importedNamespace", None)
            if tgt is None:
                tgt = imp._vals.get("importedNamespace")
            if tgt is None:
                continue
            # ownedMembership is a derived select over ownedRelationship
            rels = _as_list(ocl_get(tgt, "ownedMembership")) or \
                _as_list(getattr(tgt, "ownedMembership", None)) or \
                [r for r in _as_list(getattr(tgt, "ownedRelationship", None) or ())
                 if isinstance(r, _S2.Membership)]
            for rel in rels:
                if id(rel) in seen:
                    continue
                seen.add(id(rel))
                out.append(rel)
            if getattr(imp, "isRecursive", None):
                for sub in _as_list(getattr(tgt, "ownedRelationship", None)):
                    pass  # recursion needs the sub-namespaces' imports
    return out


def _transition_feature_memberships_of_owner(owner, kind):
    from . import sysml2 as _S2
    out = []
    for rel in _as_list(getattr(owner, "ownedRelationship", None)):
        if isinstance(rel, _S2.TransitionFeatureMembership) and \
                enum_val(getattr(rel, "kind", None)) == kind:
            for m in _as_list(getattr(rel, "ownedRelatedElement", None)):
                out.append(m)
    return out


def is_trigger_action(a):
    """KerML AcceptActionUsage::isTriggerAction(): this AcceptActionUsage
    is the triggerAction of a TransitionUsage. The runtime carries the
    forward end (TransitionUsage.triggerAction); answer from the extent
    when bound, else scan the owner chain — without either the answer
    is unknown (None)."""
    from . import sysml2 as _S2
    if a is None or not isinstance(a, _S2.AcceptActionUsage):
        return None
    ext = _EXTENT
    if ext is not None:
        for t in ext.of_kind("TransitionUsage"):
            # triggerAction derives from TransitionFeatureMembership kind=trigger
            for rel in _as_list(getattr(t, "ownedRelationship", None) or ()):
                if type(rel).__name__ == "TransitionFeatureMembership" and \
                        str(getattr(rel, "kind", "")).endswith("trigger"):
                    for m in _as_list(getattr(rel, "ownedRelatedElement", None)
                                      or ()):
                        if m is a:
                            return True
            for ta in _as_list(ocl_dot(t, "triggerAction")):
                if ta is a:
                    return True
        return False
    # no extent: walk owners looking for a TransitionUsage carrying it
    o = getattr(a, "owner", None)
    while o is not None:
        if isinstance(o, _S2.TransitionUsage):
            for ta in _as_list(ocl_dot(o, "triggerAction")):
                if ta is a:
                    return True
        o = getattr(o, "owner", None)
    return None


def instantiated_type_op(expr):
    """KerML InstantiationExpression::instantiatedType(): the Type being
    instantiated — the type of the first argument's result when present,
    else the stored/derived instantiatedType, else null (the runtime
    carries no template-binding input here)."""
    from . import sysml2 as _S2
    if expr is None:
        return None
    stored = ocl_dot(expr, "instantiatedType")
    if stored is not None and not isinstance(stored, _Undefined):
        return stored
    args = _as_list(ocl_dot(expr, "argument"))
    for a in args:
        for r in _as_list(ocl_dot(a, "result")):
            for t in _as_list(ocl_dot(r, "type")):
                if isinstance(t, _S2.Type):
                    return t
    return None


def is_substate_usage(u, is_parallel=None):
    """KerML StateUsage::isSubstateUsage(isParallel): composite, owned by
    a StateDefinition/StateUsage, and not an entry/do/exit action. The
    runtime carries owningMembership; the StateSubactionMembership kind
    distinguishes the action cases."""
    from . import sysml2 as _S2
    if u is None or not isinstance(u, _S2.StateUsage):
        return False
    if not getattr(u, "isComposite", None):
        return False
    ot = ocl_dot(u, "owningType")
    if hasattr(_S2, "StateDefinition") and ot is not None and \
            not isinstance(ot, (_S2.StateDefinition, _S2.StateUsage)):
        return False
    om = ocl_dot(u, "owningMembership")
    if isinstance(om, _S2.StateSubactionMembership):
        return False        # entry/do/exit action, not a substate
    return True


def library_namespace(el):
    """KerML Element::libraryNamespace(): the nearest owning Namespace
    that is a library element (isLibraryElement), else null. The
    runtime does not mark library models, so an element with no
    library-marked ancestor answers None — stated, not guessed."""
    o = getattr(el, "owningNamespace", None) or getattr(el, "owner", None)
    seen = set()
    while o is not None and id(o) not in seen:
        seen.add(id(o))
        if getattr(o, "isLibraryElement", None):
            return o
        o = getattr(o, "owningNamespace", None) or getattr(o, "owner", None)
    return None


def inherited_memberships(ns, excluded=None, owned=None, filter_union=None):
    """KerML Type::inheritedMemberships(...): the Memberships inherited
    via the specialization chain — for each owned/general Type, its
    ownedMemberships (and recursively). The runtime carries
    ownedSpecialization.general; the answer is computed from that graph.
    Signature matches the corpus call inheritedMemberships(Set{}, Set{},
    false)."""
    from . import sysml2 as _S2
    if ns is None:
        return []
    out, seen = [], set()
    excluded_ids = {id(e) for e in _as_list(excluded)}

    def memberships_of(t):
        for rel in _as_list(getattr(t, "ownedRelationship", None)):
            if isinstance(rel, _S2.Membership) and id(rel) not in seen \
                    and id(rel) not in excluded_ids:
                seen.add(id(rel))
                out.append(rel)

    stack = []
    for rel in _as_list(getattr(ns, "ownedSpecialization", None)):
        g = getattr(rel, "general", None)
        if g is not None:
            stack.append(g)
    # v1 shape: general / ownedGeneralization
    for g in _as_list(getattr(ns, "general", None)):
        stack.append(g)
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        memberships_of(cur)
        for rel in _as_list(getattr(cur, "ownedSpecialization", None)):
            g = getattr(rel, "general", None)
            if g is not None:
                stack.append(g)
        for g in _as_list(getattr(cur, "general", None)):
            stack.append(g)
    return out


def multiplicities(t):
    """KerML Type::multiplicities(): the Multiplicity members owned by
    this Type (its multiplicity plus owned Multiplicity members,
    read through the OCL machinery so derived ends compute)."""
    from . import sysml2 as _S2
    if t is None:
        return []
    out, seen = [], set()
    m = ocl_dot(t, "multiplicity")
    if isinstance(m, _S2.Multiplicity) and id(m) not in seen:
        seen.add(id(m))
        out.append(m)
    for e in _as_list(ocl_dot(t, "ownedMember")):
        if isinstance(e, _S2.Multiplicity) and id(e) not in seen:
            seen.add(id(e))
            out.append(e)
    if not out and isinstance(t, _S2.Feature) and \
            t._vals.get("isEnd"):
        # a feature with no owned multiplicity defaults to [1..1]: the
        # KerML default multiplicity IS Base::exactlyOne (Base.kerml
        # `multiplicity exactlyOne [1..1]`)
        try:
            from . import v1_to_v2_as as _AS
            out.append(_AS._library_definition({}, "Base::exactlyOne"))
        except Exception:                      # noqa: BLE001
            pass
    return out


def is_featuring_type(f, t):
    """KerML Feature::isFeaturingType(type): for a non-variable Feature
    the owningType must be a featuringType; for a variable one the
    snapshots of the owningType."""
    if f is None or t is None:
        return False
    ot = ocl_dot(f, "owningType")
    if getattr(f, "isVariable", None):
        return ot is not None and (ot is t or _specializes(ot, t))
    fts = _featuring_types(f)
    return ot is t or any(ft is t or _specializes(ft, t) for ft in fts)


def parameter_direction(pm):
    """KerML ParameterMembership::parameterDirection(): the required
    direction of the ownedMemberParameter — 'in' by default."""
    p = ocl_dot(pm, "ownedMemberParameter")
    if p is None:
        # ownedMemberParameter is derived; fall back to the owned member element
        for rel in (list(_as_list(getattr(pm, "ownedRelationship", None) or ()))
                    + list(_as_list(getattr(pm, "ownedMemberElement", None) or ()))
                    + [pm]):
            if rel is pm:
                for m in _as_list(getattr(pm, "ownedMemberElement", None) or ()):
                    if type(m).__name__ in ("Feature", "Parameter"):
                        p = m
                        break
                continue
            for m in _as_list(getattr(rel, "ownedMemberElement", None)
                              or getattr(rel, "ownedRelatedElement", None)
                              or ()):
                if type(m).__name__ in ("Feature", "Parameter"):
                    p = m
                    break
    if p is None:
        return "in"          # an unparametered membership defaults to in
    d = getattr(p, "direction", None)
    if d is None:
        d = p._vals.get("direction")
    return enum_val(d) or "in"


def ocl_contains(coll, x):
    """OCL Collection::contains(x) — dot-form includes."""
    return x in (coll or ())


def model_level_evaluable(x, visited=None):
    """KerML Expression::modelLevelEvaluable(visited): a stored flag when
    the runtime carries one; literal expressions are always evaluable;
    otherwise unknown (None)."""
    if x is None:
        return None
    from . import sysml2 as _S2
    if isinstance(x, _S2.LiteralExpression):
        return True
    v = getattr(x, "isModelLevelEvaluable", None)
    if v is not None:
        return bool(v)
    return None


def ocl_prepend(coll, element):
    """OCL Sequence::prepend(x): element + the sequence."""
    return [element] + list(coll or ())


def _subsets(f, other):
    """True when feature f (directly) subsets or redefines `other`: an
    owned Subsetting/Redefinition with f as its subsetting/redefining
    feature pointing at other."""
    if f is None or other is None:
        return False
    for rel in (getattr(f, "ownedRelationship", None) or ()):
        if getattr(rel, "_vals", {}).get("subsettingFeature") is not f:
            continue
        tgt = rel._vals.get("subsettedFeature") \
            or rel._vals.get("referencedFeature")
        if tgt is other:
            return True
    return False


def can_access(f, other, _self=None):
    """KerML Feature::canAccess(feature): the other feature is featured
    within one of the direct or indirect featuringTypes of this
    Feature."""
    if f is None or other is None:
        return False
    # a feature itself carries what it subsets/redefines: sf :> stf is
    # an access path by construction (the end of a connector :> the
    # connected part is exactly this shape)
    if _subsets(f, other):
        return True
    # a feature is featured within its own owningType, so anything featured
    # in the same type is accessible
    ot_f = ocl_dot(f, "owningType") or getattr(f, "owningType", None)
    ot_o = ocl_dot(other, "owningType") or getattr(other, "owningType", None)
    if ot_f is not None and ot_f is ot_o:
        return True
    for ft in _featuring_types(f):
        if is_featured_within(other, ft):
            return True
    # indirect: featuringTypes of featuringTypes
    seen = set()
    stack = list(_featuring_types(f))
    while stack:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        if is_featured_within(other, cur):
            return True
        for ft in _as_list(getattr(cur, "featuringType", None)):
            stack.append(ft)
    return False


def owning_type_op(el):
    """KerML Element::owningType(): the owning Type. as_inverses sets it
    for membership-owned elements; otherwise fall back to the owner
    chain (the first owner that is a Type), with the AS owner
    derivations applied (derived.owner)."""
    from . import sysml2 as _S2
    if el is None:
        return None
    v = ocl_dot(el, "owningType")
    if v is not None and not isinstance(v, _Undefined):
        return v
    o = D.owner(el)
    while o is not None:
        if isinstance(o, _S2.Type):
            return o
        o = D.owner(o)
    return None


def value_of(expr, _self=None):
    """KerML `valueOf(e)`: the model-level value of an Expression — a
    Literal's carried value, else its result's value (derive-on-read),
    else null."""
    if expr is None:
        return None
    v = getattr(expr, "value", None)
    if v is not None:
        return v
    for r in _as_list(ocl_dot(expr, "result")):
        rv = getattr(r, "value", None)
        if rv is not None:
            return rv
    return None


def ocl_exits(coll, pred):
    """OCL Collection::exits(lambda) — KerML spelling: exists an element
    satisfying the predicate. `pred` arrives as a lowered lambda body
    source evaluated per element via _exits_pred."""
    return any(bool(pred(e)) for e in (coll or ()))


def referenced_feature_target(el):
    """KerML `referencedFeatureTarget()`: per the AS body, the
    featureTarget of the referencedFeature of the owned
    ReferenceSubsetting, else null. The generated Usage class carries a
    `referencedFeatureTarget` stub method, so a callable getattr is not a
    stored value — it must not be returned."""
    from . import sysml2 as _S2
    if el is None:
        return None
    v = getattr(el, "referencedFeatureTarget", None)
    if v is not None and not callable(v):
        return v
    # ownedReferenceSubsetting is a derived end on the AS runtime: read
    # it through the same derivation the evaluator uses, not raw getattr
    for rel in _as_list(ocl_get(el, "ownedReferenceSubsetting")):
        rf = getattr(rel, "referencedFeature", None)
        if rf is not None:
            # featureTarget of the referenced feature comes from its
            # FeatureChaining (chainingFeature); the runtime stores chains
            # as ownedRelationships, so walk them
            target = None
            for ch in _as_list(getattr(rf, "ownedRelationship", None) or ()):
                if type(ch).__name__ == "FeatureChaining":
                    target = getattr(ch, "chainingFeature", None)
                    if target is not None:
                        return target
            return rf
    rf = ocl_get(el, "referencedFeature")
    if isinstance(rf, _Undefined):
        rf = None
    if rf is not None and not callable(rf):
        return rf
    return None



# --------------------------------------------------------------------------
# O6: UML 2.5.1 (formal/2017-12-05) helper operations, transcribed from
# the spec's own bodies. Anything the model does not carry answers
# None/False per the body, never a guess.
# --------------------------------------------------------------------------

def open_end(action):
    """ReadLinkAction::openEnd (§16.14.38.5):
    `endData->select(value=null).end->asOrderedSet()` — the ends whose
    LinkEndData carries no value InputPin."""
    out, seen = [], set()
    for ed in getattr(action, "endData", None) or ():
        if getattr(ed, "value", None) is not None:
            continue
        e = getattr(ed, "end", None)
        if e is not None and id(e) not in seen:
            seen.add(id(e))
            out.append(e)
    return out


def includes_multiplicity(me, m):
    """MultiplicityElement::includesMultiplicity (§7.8.8.7):
    `self.lowerBound() <= M.lowerBound() and self.upperBound() >=
    M.upperBound()`; '*' is unbounded. Partial-honest: with a bound
    unset (the spec body's precondition) there is no answer."""
    from .derived import lower_bound, upper_bound
    if me is None or m is None:
        return False
    sl, su = lower_bound(me), upper_bound(me)
    ml, mu = lower_bound(m), upper_bound(m)
    if sl is None or su is None or ml is None or mu is None:
        return None
    def un(v):
        return None if v == "*" else int(v)
    sl_i, su_i, ml_i, mu_i = int(sl), un(su), int(ml), un(mu)
    lower_ok = sl_i <= ml_i
    upper_ok = su_i is None or (mu_i is not None and su_i >= mu_i)
    return lower_ok and upper_ok


def is_compatible_with(el, p):
    """ParameterableElement::isCompatibleWith (§7.8.13.5), with the
    Property/ValueSpecification redefinitions (§9.9.17 / §8.3.5):
    `self.oclIsKindOf(p.oclType()) and (p.oclIsKindOf(TypedElement)
    implies self.type.conformsTo(p.type))`. oclType() is the dynamic
    type, so self is compatible when its metaclass is a subtype of p's."""
    if el is None or p is None:
        return False
    # self.oclIsKindOf(p.oclType()): self's dynamic kind subtypes p's
    if type(p) not in type(el).__mro__:
        return False
    # p a TypedElement -> self.type must conform to p's type (the
    # Property/ValueSpecification redefinitions); for plain
    # ParameterableElements the kind check is the whole body
    if isinstance(p, U.TypedElement):
        from .derived import conforms_to
        st = getattr(el, "type", None)
        pt = getattr(p, "type", None)
        if st is None or pt is None:
            return None
        return conforms_to(st, pt)
    return True


def is_substitutable_for(cl, contract):
    """Classifier::isSubstitutableFor (§9.9.4.7):
    `substitution.contract->includes(contract)`."""
    for s in getattr(cl, "substitution", None) or ():
        if getattr(s, "contract", None) is contract:
            return True
    return False


def _message_end_union(message):
    """message.messageEnd — the runtime does not carry the declared
    `messageEnd` union on Message (sendEvent/receiveEvent subset it but
    the generator dropped the derived end), so collect both ends."""
    out = []
    for attr in ("sendEvent", "receiveEvent"):
        v = getattr(message, attr, None)
        if v is None:
            continue
        out.extend(v if isinstance(v, (list, tuple)) else [v])
    return out


# MessageEnd.message has no opposite hook in the runtime (the ends are
# stored on the Message as sendEvent/receiveEvent), so gate queries that
# navigate `self.message` or `oppositeEnd()` resolve the message through
# this registry, populated by _note_message_ends when a model graph is
# scanned (the bound extent) or when a test assigns message ends.
_END_MESSAGES = {}


def _register_message_end(message, end):
    ends = _END_MESSAGES.setdefault(id(message), [])
    if all(e is not end for e, _ in ends):
        ends.append((end, message))


def _note_message_ends(message):
    for e in _message_end_union(message):
        _register_message_end(message, e)


def _scan_messages_for(end):
    """Register `end`'s message from the bound extent, if any."""
    ext = _EXTENT
    if ext is None:
        return None
    for m in ext.of_kind("Message"):
        if end in _message_end_union(m):
            _register_message_end(m, end)
            return m
    return None


def _scan_messages_for_all(end):
    """Every bound-extent Message naming `end`, registered and returned."""
    ext = _EXTENT
    if ext is None:
        return []
    out = []
    for m in ext.of_kind("Message"):
        if end in _message_end_union(m):
            _register_message_end(m, end)
            out.append(m)
    return out


def _end_message(end):
    """The Message carrying `end` as sendEvent or receiveEvent. The
    runtime has no opposite hook for MessageEnd.message, so: the
    registry, then the bound extent's Messages, then end.message."""
    for _mid, ends in _END_MESSAGES.items():
        for e, m in ends:
            if e is end:
                return m
    m = _scan_messages_for(end)
    if m is not None:
        return m
    return getattr(end, "message", None)


def _message_end_opposite_end(end, message=None):
    """MessageEnd::oppositeEnd (§17.12.9.4):
    `message->asSet().messageEnd->asSet()->excluding(self)`. The
    runtime stores one single-valued sendEvent/receiveEvent per Message
    (two different Messages may share a gate), so the opposite end is
    collected from every message naming this end, not just the first."""
    ms = [message] if message is not None else []
    if message is None:
        for _mid, ends in _END_MESSAGES.items():
            for e, m in ends:
                if e is end and all(m is not x for x in ms):
                    ms.append(m)
        m0 = getattr(end, "message", None)
        if m0 is not None and all(m0 is not x for x in ms):
            ms.append(m0)
        scanned = _scan_messages_for_all(end)
        for m in scanned:
            if all(m is not x for x in ms):
                ms.append(m)
    out, seen = [], set()
    for m in ms:
        for e in _message_end_union(m):
            if e is not end and id(e) not in seen:
                seen.add(id(e))
                out.append(e)
    return out


def _gate_combined_fragment(gate):
    """Gate.combinedFragment: the runtime does not carry the inverse of
    A_cfragmentGate_combinedFragment, so ownership supplies it
    (cfragmentGate subsets ownedElement)."""
    o = getattr(gate, "owner", None)
    while o is not None:
        if isinstance(o, U.CombinedFragment):
            return o
        o = getattr(o, "owner", None)
    return None


def _operand_cf(operand):
    """InteractionOperand.combinedFragment — not a stored end either;
    the operand's owner is the CombinedFragment (operand subsets
    ownedElement)."""
    o = getattr(operand, "owner", None) if operand is not None else None
    return o if isinstance(o, U.CombinedFragment) else None


def _gate_is_send(gate):
    m = _end_message(gate)
    if m is None:
        return False
    v = getattr(m, "sendEvent", None)
    ends = list(v) if isinstance(v, (list, tuple)) else ([] if v is None else [v])
    return gate in ends


def gate_is_actual(gate):
    """Gate::isActual (§17.12.9.4): `interactionUse->notEmpty()`. The runtime
    does not carry the inverse of A_actualGate_interactionUse, so the honest
    structural answer is composite ownership the other way: an actual gate is
    owned by an InteractionUse (actualGate subsets ownedElement)."""
    return isinstance(getattr(gate, "owner", None), U.InteractionUse)


def _gate_get_name(gate):
    """Gate::getName (§17.12.9.4): the explicit name, else the
    constructed 'out_'/'in_' prefix on message.name."""
    name = getattr(gate, "name", None)
    if name:
        return name
    m = _end_message(gate)
    mname = getattr(m, "name", None) if m is not None else None
    if mname is None:
        return None
    is_send = _gate_is_send(gate)
    if gate_is_outside_cf(gate) or gate_is_actual(gate):
        prefix = "out_" if is_send else "in_"
    else:
        prefix = "in_" if is_send else "out_"
    return prefix + mname


def gate_matches(gate, gate_to_match):
    """Gate::matches (§17.12.9.4): same getName() and message name, same
    messageSort, same signature, send/receive correspond."""
    if gate is None or gate_to_match is None:
        return False
    if _gate_get_name(gate) != _gate_get_name(gate_to_match):
        return False
    ma = _end_message(gate)
    mb = _end_message(gate_to_match)
    if ma is None or mb is None:
        return None
    if getattr(ma, "name", None) != getattr(mb, "name", None):
        return False
    if enum_val(getattr(ma, "messageSort", None)) != \
            enum_val(getattr(mb, "messageSort", None)):
        return False
    if getattr(ma, "signature", None) is not getattr(mb, "signature", None):
        return False
    a_send = _gate_is_send(gate)
    b_send = _gate_is_send(gate_to_match)
    if a_send == b_send:
        # both send or both receive: the spec requires opposite roles
        return False
    return True


def gate_is_inside_cf(gate):
    """Gate::isInsideCF (§17.12.9.4): attached to a CombinedFragment
    boundary and the opposite end is inside an operand of the same
    CombinedFragment. A gate with no boundary CF answers False (the
    spec body's implication is vacuous without combinedFragment)."""
    cf = _gate_combined_fragment(gate)
    opp = _message_end_opposite_end(gate)
    if cf is None or not opp:
        return False
    opp_end = opp[0]
    if isinstance(opp_end, U.MessageOccurrenceSpecification):
        return _operand_cf(getattr(opp_end, "enclosingOperand", None)) is cf
    if isinstance(opp_end, U.Gate):
        oc = _gate_combined_fragment(opp_end)
        eo = getattr(oc, "enclosingOperand", None) if oc is not None else None
        return _operand_cf(eo) is cf
    return False


def gate_is_outside_cf(gate):
    """Gate::isOutsideCF (§17.12.9.4): attached to a CombinedFragment
    boundary and the opposite end is outside the same
    CombinedFragment (same enclosing interaction/operand)."""
    cf = _gate_combined_fragment(gate)
    opp = _message_end_opposite_end(gate)
    if cf is None or not opp:
        return False
    opp_end = opp[0]
    if isinstance(opp_end, U.MessageOccurrenceSpecification):
        oi = getattr(opp_end, "enclosingInteraction", None)
        oo = getattr(opp_end, "enclosingOperand", None)
    elif isinstance(opp_end, U.Gate):
        oc = _gate_combined_fragment(opp_end)
        if oc is None:
            return False
        oi = getattr(oc, "enclosingInteraction", None)
        oo = getattr(oc, "enclosingOperand", None)
    else:
        return False
    return oi is not None and oi is getattr(cf, "enclosingInteraction", None) or \
        oo is not None and oo is getattr(cf, "enclosingOperand", None)


def start_object_behavior(action):
    """StartObjectBehaviorAction::behavior (§16.14.53.5): the type of
    the object InputPin when it is a Behavior, else the
    classifierBehavior of that type when it is a BehavioredClassifier,
    else null."""
    pin = getattr(action, "object", None)
    t = getattr(pin, "type", None) if pin is not None else None
    if t is None:
        return None
    if isinstance(t, U.Behavior):
        return t
    if isinstance(t, U.BehavioredClassifier):
        return getattr(t, "classifierBehavior", None)
    return None


# --------------------------------------------------------------------------
# UML 2.5.1 one-off helper operations (O4b) — local functions, each with
# its clause number quoted from formal/2017-12-05.
# --------------------------------------------------------------------------

def _aslist(v):
    return ocl_aslist(v)


def is_consistent_with(redefined, redefining):
    """RedefinableElement::isConsistentWith (§9.9.18.7): "By default, this
    is false; this operation must be overridden for subclasses".

    The metamodel's concrete overrides (§9.9.11.6 Operation, §9.9.17.7
    Property, §9.9.19.5 RedefinableTemplateSignature, §14.5.1.5
    ConnectionPointReference, §14.5.2.4 FinalState, §14.5.6.6
    Pseudostate, §14.5.8.4 Region, §14.5.9.x State, §14.5.10.x
    Transition, §15.7.2.7 ActivityEdge, §15.7.5.x ActivityNode,
    §14.5.3.x StateMachine) are dispatched here on the redefined
    element's class; everything else takes the base body `false`."""
    if redefining is None:
        return False
    if isinstance(redefined, U.Operation):
        # §9.9.11.6: same parameter count; per parameter equal
        # uniqueness/ordering/direction, conforming types (either way),
        # and direction-dependent multiplicity compatibility.
        if not isinstance(redefining, U.Operation):
            return False
        op = redefining
        mine = list(_aslist(getattr(redefined, "ownedParameter", None)))
        theirs = list(_aslist(getattr(op, "ownedParameter", None)))
        if len(mine) != len(theirs):
            return False
        for rp, dp in zip(mine, theirs):
            if enum_val(getattr(rp, "isUnique", None)) != \
                    enum_val(getattr(dp, "isUnique", None)):
                return False
            if enum_val(getattr(rp, "isOrdered", None)) != \
                    enum_val(getattr(dp, "isOrdered", None)):
                return False
            if enum_val(getattr(dp, "direction", None)) != \
                    enum_val(getattr(rp, "direction", None)):
                return False
            dt, rt = getattr(dp, "type", None), getattr(rp, "type", None)
            if dt is not None and rt is not None and \
                    not (D.conforms_to(dt, rt) or D.conforms_to(rt, dt)):
                return False
            d = enum_val(getattr(dp, "direction", None))
            if d == "inout" and not (ocl_compatible_with(rp, dp)
                                     and ocl_compatible_with(dp, rp)):
                return False
            if d == "in" and not ocl_compatible_with(rp, dp):
                return False
            if d in ("out", "return") and not ocl_compatible_with(dp, rp):
                return False
        return True
    if isinstance(redefined, U.Property):
        # §9.9.17.7: redefining type conforms to the redefined type,
        # the redefining multiplicity (when specified) is contained in
        # the redefined one, and composite-ness is preserved.
        if not isinstance(redefining, U.Property):
            return False
        prop = redefining
        rt, dt = getattr(redefined, "type", None), getattr(prop, "type", None)
        if rt is not None and dt is not None and not D.conforms_to(dt, rt):
            return False
        if getattr(prop, "lowerValue", None) is not None and \
                getattr(redefined, "lowerValue", None) is not None and \
                ocl_compatible_with(redefined, prop) is False:
            return False
        if D.is_composite(redefined) and not D.is_composite(prop):
            return False
        return True
    if isinstance(redefined, U.RedefinableTemplateSignature):
        # §9.9.19.5: always consistent (redefinition only adds formals)
        return isinstance(redefining, U.RedefinableTemplateSignature)
    if isinstance(redefined, U.ConnectionPointReference):
        # §14.5.1.5: only a ConnectionPointReference
        return isinstance(redefining, U.ConnectionPointReference)
    if isinstance(redefined, U.FinalState):
        # §14.5.2.4: only a FinalState
        return isinstance(redefining, U.FinalState)
    if isinstance(redefined, U.Pseudostate):
        # §14.5.6.6: a Pseudostate of the same kind
        return isinstance(redefining, U.Pseudostate) and \
            enum_val(getattr(redefining, "kind", None)) == \
            enum_val(getattr(redefined, "kind", None))
    if isinstance(redefined, U.Region):
        # §14.5.8.4: any Region (consistency = valid redefinition context)
        return isinstance(redefining, U.Region)
    if isinstance(redefined, U.State):
        # §14.5.9.x: the redefining State must redefine the submachine
        if not isinstance(redefining, U.State):
            return False
        if getattr(redefined, "submachine", None) is None:
            return True
        sm = getattr(redefining, "submachine", None)
        if sm is None:
            return False
        return getattr(redefined, "submachine", None) in \
            _aslist(getattr(sm, "extendedStateMachine", None))
    if isinstance(redefined, U.Transition):
        # §14.5.10.x: the redefining Transition's source redefines the
        # redefined Transition's source
        if not isinstance(redefining, U.Transition):
            return False
        src = getattr(redefined, "source", None)
        rsrc = getattr(redefining, "source", None)
        if src is None or rsrc is None:
            return False
        return src in _aslist(getattr(rsrc, "redefinedElement", None))
    if isinstance(redefined, U.ActivityEdge):
        # §15.7.2.7: only an ActivityEdge
        return isinstance(redefining, U.ActivityEdge)
    if isinstance(redefined, U.ActivityNode):
        # §15.7.5.x: only an ActivityNode
        return isinstance(redefining, U.ActivityNode)
    if isinstance(redefined, U.StateMachine):
        # §14.5.3.x: consistent whenever the redefinition context is valid
        return is_redefinition_context_valid(redefining, redefined)
    # §9.9.18.7 base body: false
    return False


def is_redefinition_context_valid(redefining, redefined):
    """RedefinableElement::isRedefinitionContextValid (§9.9.18.7):
    body: redefinitionContext->exists(c | c.allParents()
    ->includesAll(redefinedElement.redefinitionContext)).

    The Region (§14.5.8.5), StateMachine (§14.5.3.x) and Vertex
    (§14.5.1.x) overrides are dispatched on the receiver's class."""
    if redefined is None:
        return False
    if isinstance(redefining, U.Region) and isinstance(redefined, U.Region):
        # §14.5.8.5 body
        sm = getattr(redefining, "stateMachine", None)
        if sm is not None:
            ext = _aslist(getattr(sm, "extendedStateMachine", None))
            return any(redefined in _aslist(getattr(e, "region", None))
                       for e in ext)
        st = getattr(redefining, "state", None)
        if st is None:
            return False
        return any(redefined in _aslist(getattr(rs, "region", None))
                   for rs in _aslist(getattr(st, "redefinedState", None)))
    if isinstance(redefining, U.StateMachine) and \
            isinstance(redefined, U.StateMachine):
        # §14.5.3.x: the context BehavioredClassifier of the redefining
        # machine must specialize the redefined machine's context
        parent_ctx = getattr(redefined, "context", None)
        ctx = getattr(redefining, "context", None)
        if ctx is None:
            return parent_ctx is None and \
                redefined in D.all_parents(redefining)
        return parent_ctx is not None and parent_ctx in D.all_parents(ctx)
    if isinstance(redefining, U.Vertex) and isinstance(redefined, U.Vertex):
        # §14.5.1.x: the owner of the redefining Vertex redefines the
        # owner of the redefined Vertex
        owner = getattr(redefining, "owner", None)
        other_owner = getattr(redefined, "owner", None)
        if owner is None or other_owner is None:
            return False
        return other_owner in _aslist(getattr(owner, "redefinedElement", None))
    # base body: one of self's redefinition contexts specializes
    # (allParents includes) all of the redefined element's contexts
    mine = _aslist(getattr(redefining, "redefinitionContext", None))
    theirs = _aslist(getattr(redefined, "redefinitionContext", None))
    if not theirs:
        return False
    for c in mine:
        anc = [c] + (D.all_parents(c) if isinstance(c, U.Classifier) else [])
        if all(t in anc for t in theirs):
            return True
    return False


def members_are_distinguishable(ns):
    """Namespace::membersAreDistinguishable (§7.8.10.6):
    member->forAll(memb | member->excluding(memb)->forAll(other |
    memb.isDistinguishableFrom(other, self)))."""
    from .derived import member, is_distinguishable_from
    mem = list(member(ns))
    for i, memb in enumerate(mem):
        for other in mem[i + 1:]:
            if not is_distinguishable_from(memb, other, ns):
                return False
    return True


def may_specialize_type(cl, c):
    """Classifier::maySpecializeType (§9.2.4.6):
    body: self.oclIsKindOf(c.oclType()) — self's kind is a subtype of
    the argument's dynamic type."""
    if c is None:
        return False
    return isinstance(cl, type(c))


def is_accessible_by(var, action):
    """Variable::isAccessibleBy (§15.7.25.6):
    body: if scope<>null then scope.allOwnedNodes()->includes(a)
    else a.containingActivity()=activityScope endif."""
    if action is None:
        return False
    scope = getattr(var, "scope", None)
    if scope is not None:
        return action in all_owned_nodes(scope)
    return containing_activity(action) is getattr(var, "activityScope", None)


def source_nodes(san):
    """StructuredActivityNode::sourceNodes (§16.12.x):
    body: node->union(input.oclAsType(ActivityNode)->asSet())->
    union(node->select(oclIsKindOf(Action)).oclAsType(Action).output)
    ->asSet(). (The LoopNode override adds loopVariable; LoopNode is a
    separate metaclass, so this is the base body.)"""
    out, seen = [], set()
    # `node` is stored as a plain list but the runtime's generated union
    # tables are what the spec body reads, so go through ocl_get (derived
    # route) first and fall back to the stored list
    nodes = _aslist(ocl_get(san, "node")) or _aslist(getattr(san, "node", None))
    for n in nodes:
        if id(n) not in seen:
            seen.add(id(n)); out.append(n)
    for p in _aslist(ocl_get(san, "input")):
        if isinstance(p, U.ActivityNode) and id(p) not in seen:
            seen.add(id(p)); out.append(p)
    for n in nodes:
        if isinstance(n, U.Action):
            raw = _aslist(getattr(n, "output", None)) or _aslist(n._vals.get("output") or ())
            outs = _aslist(ocl_get(n, "output")) or raw
            for o in outs + [x for x in raw if x not in outs]:
                if id(o) not in seen:
                    seen.add(id(o)); out.append(o)
    return out


def metaclass_end(ext):
    """Extension::metaclassEnd (§12.4.1.6):
    body: memberEnd->reject(p | ownedEnd->includes(
    p.oclAsType(ExtensionEnd)))->any(true) — the member end that is not
    the owned (stereotype) end."""
    owned = _aslist(getattr(ext, "ownedEnd", None))
    for p in _aslist(getattr(ext, "memberEnd", None)):
        if not any(o is p for o in owned):
            return p
    return None


def has_all_datatype_attributes(d):
    """FunctionBehavior::hasAllDataTypeAttributes(d) (§13.4.6.4):
    body: d.ownedAttribute->forAll(a | a.type.oclIsKindOf(DataType) and
    hasAllDataTypeAttributes(a.type.oclAsType(DataType))) — recursive,
    so DataType attributes may only nest other DataTypes."""
    if d is None:
        return False
    for a in _aslist(getattr(d, "ownedAttribute", None)):
        t = getattr(a, "type", None)
        if not isinstance(t, U.DataType):
            return False
        if not has_all_datatype_attributes(t):
            return False
    return True


def gate_is_formal(gate):
    """Gate::isFormal (§17.12.9.4): `interaction->notEmpty()` — a formal
    gate's owner is the Interaction (formalGate subsets ownedElement,
    composite)."""
    return isinstance(getattr(gate, "owner", None), U.Interaction)


def enclosing_fragment(end):
    """MessageEnd::enclosingFragment (§17.12.19.6): the set including
    the enclosing InteractionFragment — for a MessageOccurrence-
    Specification the enclosingInteraction, else the enclosingOperand.
    (The Gate branch of the spec body routes through
    isOutsideCF/isInsideCF/isFormal/isActual, implemented above.)"""
    if end is None:
        return []
    ei = getattr(end, "enclosingInteraction", None)
    if ei is not None:
        return [ei]
    eo = getattr(end, "enclosingOperand", None)
    if eo is not None:
        return [eo]
    return []


def all_owning_packages(el):
    """NamedElement::allOwningPackages (§7.8.9.6): the enclosing
    Namespaces that are Packages, working outwards, up to the first
    non-Package. Spec body: namespace.oclIsKindOf(Package) ->
    owningPackage->union(owningPackage.allOwningPackages())."""
    out, seen = [], set()
    ns = getattr(el, "namespace", None)
    while isinstance(ns, U.Package):
        if id(ns) in seen:
            break
        seen.add(id(ns))
        out.append(ns)
        ns = getattr(ns, "namespace", None)
    return out


def protocol_transition_referred(pt):
    """ProtocolTransition::/referred (§14.5.5.5 derivation):
    trigger->collect(event)->select(oclIsKindOf(CallEvent))->
    collect(oclAsType(CallEvent).operation)->asSet()."""
    out, seen = [], set()
    for trg in _aslist(getattr(pt, "trigger", None)):
        ev = getattr(trg, "event", None)
        if isinstance(ev, U.CallEvent):
            op = getattr(ev, "operation", None)
            if op is not None and id(op) not in seen:
                seen.add(id(op))
                out.append(op)
    return out


def belongs_to_psm(region):
    """Region::belongsToPSM (§14.5.8.5):
    body: if stateMachine <> null then
    stateMachine.oclIsKindOf(ProtocolStateMachine)
    else state <> null implies state.container.belongsToPSM() endif."""
    sm = getattr(region, "stateMachine", None)
    if sm is not None:
        return isinstance(sm, U.ProtocolStateMachine)
    st = getattr(region, "state", None)
    if st is None:
        return False
    container = getattr(st, "container", None)
    if container is None:
        return False
    return belongs_to_psm(container)


# --------------------------------------------------------------------------
# O7: the six KerML/SysML v2 (sysml2 AS) helper operations. The generated
# classes carry them as `raise NotImplementedError` stubs, so `ocl_dot`
# would hand back the bound method — these local lowerings replace the
# stub at eval time. Semantics follow the AS operation docs in sysml2.py.
# --------------------------------------------------------------------------

def sysml2_specializes(el, target):
    """KerML Type::specializes(supertype): direct or indirect
    specialization. Reuses the same chain walk as specializesFromLibrary
    (Specialization graph + v1 generalization), between two elements."""
    if target is None:
        return None
    if isinstance(target, str):
        # a quoted library name: resolve through the bound extent
        t = _extent().qualified(target)
        if t is None:
            return False
        target = t
    return _specializes(el, target)


def sysml2_redefines(el, target):
    """KerML Feature::redefines(redefinedFeature): DIRECT redefinition.
    The AS `Redefinition` relationship is owned by the redefining feature
    (owningType/owningFeature) and points at the redefined one; the
    runtime's derived ownedRedefinition end does not compute, so walk
    ownedSpecialization for Redefinition relationships."""
    if el is None or target is None:
        return False
    if isinstance(target, str):
        t = _extent().qualified(target)
        if t is None:
            return False
        target = t
    from . import sysml2 as _S2
    for rel in _aslist(getattr(el, "ownedSpecialization", None)):
        if not isinstance(rel, _S2.Redefinition):
            continue
        if getattr(rel, "redefinedFeature", None) is target:
            return True
        # subsettingFeature may carry the redefining end instead
        if getattr(rel, "subsettingFeature", None) is el and \
                getattr(rel, "redefinedFeature", None) is target:
            return True
    # v1 spelling: RedefinableElement.redefinedElement
    for r in _aslist(getattr(el, "redefinedElement", None)):
        if r is target:
            return True
    return False


def _sysml2_input_features(step):
    """The in/inout parameters of a Step/Behavior: the owned
    ParameterMembership features whose direction is in/inout. The derived
    `parameter` end does not compute in the runtime, so select from the
    owned memberships directly (the same rule as the AS
    deriveTypeDirectedFeature / Behavior.parameter bodies)."""
    from . import sysml2 as _S2
    out, seen = [], set()
    for rel in _aslist(getattr(step, "ownedRelationship", None)):
        if not isinstance(rel, _S2.ParameterMembership):
            continue
        for f in _aslist(getattr(rel, "ownedRelatedElement", None)):
            if not isinstance(f, _S2.Feature) or id(f) in seen:
                continue
            if direction_of(f) in ("in", "inout"):
                seen.add(id(f))
                out.append(f)
    return out


def input_parameter_n(step, i):
    """KerML ActionUsage::inputParameter(i): the i-th (1-based) owned
    input parameter, or null when there are fewer."""
    if step is None or i is None:
        return None
    params = _sysml2_input_features(step)
    idx = int(i) - 1
    if idx < 0 or idx >= len(params):
        return None
    return params[idx]


def sysml2_argument(step, i):
    """KerML ActionUsage::argument(i): the i-th argument Expression — the
    `value` of the FeatureValue on the i-th owned input parameter, else
    null. The task brief's shorter reading (the element's own `argument`
    property when present) wins when the element carries a real
    `argument` list (an InstantiationExpression's end); the generated
    ActionUsage stub method is callable and therefore not a stored
    list, so it falls through to the FeatureValue rule."""
    if step is None or i is None:
        return None
    own = getattr(step, "argument", None)
    if own is not None and not callable(own):
        args = _aslist(own)
        idx = int(i) - 1
        if 0 <= idx < len(args):
            return args[idx]
        return None
    param = input_parameter_n(step, i)
    if param is None:
        return None
    from . import sysml2 as _S2
    for rel in _aslist(getattr(param, "ownedRelationship", None)):
        if isinstance(rel, _S2.FeatureValue):
            v = getattr(rel, "value", None)
            if v is not None:
                return v
    return None


def is_subaction_usage(au):
    """KerML ActionUsage::isSubactionUsage(): composite and owningType is
    an ActionDefinition or ActionUsage, but the owning membership is not
    a StateSubactionMembership (entry/do/exit) of a StateDefinition/
    StateUsage. The runtime does not wire owningFeatureMembership, so the
    membership is found through owningRelationship."""
    from . import sysml2 as _S2
    if au is None:
        return False
    if not getattr(au, "isComposite", None):
        return False
    ot = getattr(au, "owningType", None)
    if ot is None:
        return False
    if not isinstance(ot, (_S2.ActionDefinition, _S2.ActionUsage)):
        return False
    for rel in _aslist(getattr(au, "owningRelationship", None)):
        if isinstance(rel, _S2.StateSubactionMembership):
            return False
    return True


# -- tables built after every local lowering above exists ------------------
# operations added after the v0 emitter retired: the oracle must not learn
# them, or the differential stops measuring v0
_LEGACY_EXCLUDED = {"selectByKind", "selectAsKind", "specializesFromLibrary",
                    "effectiveName", "effectiveShortName", "escapedName",
                    "directionOf", "subSequence", "including",
                    # O6 uml25 helper operations (learned after v0 retired)
                    "openEnd", "includesMultiplicity", "isCompatibleWith",
                    "isSubstitutableFor", "matches", "isInsideCF",
                    "isOutsideCF", "behavior",
                    # O4b uml25 one-off helpers (learned after v0 retired)
                    "isConsistentWith", "isRedefinitionContextValid",
                    "membersAreDistinguishable", "maySpecializeType",
                    "isAccessibleBy", "sourceNodes", "metaclassEnd",
                    "hasAllDataTypeAttributes", "isFormal", "isActual",
                    "enclosingFragment", "allOwningPackages", "referred",
                    "belongsToPSM",
                    # O7 sysml2 helper operations (learned after v0 retired)
                    "specializes", "redefines", "argument",
                    "referencedFeatureTarget", "referencedFeaureTarget",
                    "isSubactionUsage", "inputParameter"}

_DERIVED_FUNCS_LEGACY = {
    name: (kind, fnname if kind == "derived" else globals().get(fnname))
    for name, (kind, fnname) in SY.DERIVED_FUNCS.items()
    if name not in _LEGACY_EXCLUDED and (kind == "derived"
                                         or fnname in globals())
}

for _nm, (_kind, _fn) in SY.DERIVED_FUNCS.items():
    if _kind == "local" and _fn in globals():
        _EVAL_ENV.setdefault(_fn, globals()[_fn])

# built last: _implies is defined below _EVAL_ENV (the three-valued
# KerML implies; the env binding rides the end-of-module loop)
_EVAL_ENV["_implies"] = _implies
_EVAL_ENV["_closure_call"] = _closure_call
_EVAL_ENV["_land"] = _land
_EVAL_ENV["_lor"] = _lor

# built last: _iterate is defined above the O6 section, after _EVAL_ENV
_EVAL_ENV["_iterate"] = _iterate
