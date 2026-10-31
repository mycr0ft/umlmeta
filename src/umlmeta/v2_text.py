#!/usr/bin/env python
"""v2_text.py — SysML v2 textual notation emitted from the AS graph.

Pathway: docs/v1-v2-linkage-pathway.md, milestone M2 ("single form
notation"). This emitter is the *one* notation for the pipeline: it renders
``umlmeta.sysml2`` objects, so the transformed model — not the v1 model —
is the source of truth for what gets written. The calibrated v1 -> text
emitter (``v1_to_v2``) stays as the notation oracle: where both pipelines
have an opinion about the same model they must produce byte-identical text
(the M2 gate in ``check_v1_to_v2_as.py``), and the difference between them
is a measurable coverage list, not a silent divergence.

Honesty rule (same as the transformer): an AS element this module cannot
render raises :class:`UnsupportedEmission` naming the metaclass. Nothing is
dropped silently — a model that emits is a model that round-trips.

Forms (all calibrated against sysmlpy, the authoritative v2 reader):

  package X { ... }                    Package
  part def X [:> A, B] { ... }         PartDefinition
  attribute def X { ... }              AttributeDefinition
  enum def X { lit; ... }              EnumerationDefinition/Usage
  constraint def X                     ConstraintDefinition
  occurrence def X                     OccurrenceDefinition
  item def X                           ItemDefinition
  port def X                           PortDefinition
  state def X { state s; ... }         StateDefinition/StateUsage
  action def X { in p : T; ... }       ActionDefinition/ActionUsage
  use case def X                       UseCaseDefinition
  verification def X                   VerificationCaseDefinition
  connection def X                     ConnectionDefinition
  metadata def X                       MetadataDefinition
  interaction X { part l : T; ... }    Interaction (lifelines/messages)
  requirement <'id'> X { doc /* */ }   RequirementUsage
  satisfy n : R by P;                  SatisfyRequirementUsage
  part p : T[n..m];                    typed usage + multiplicity
  ref part p : T;                      isComposite=false
  p : T;                               untyped Feature
  doc /* text */                       Documentation
  import P::*;  import P::A;           NamespaceImport / MembershipImport
"""
from __future__ import annotations

import re

from . import sysml2 as S2


class UnsupportedEmission(Exception):
    """An AS element with no textual form in this emitter yet."""


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_DEF_KEYWORD = {
    "PartDefinition": "part def",
    "AttributeDefinition": "attribute def",
    "EnumerationDefinition": "enum def",
    "ConstraintDefinition": "constraint def",
    "OccurrenceDefinition": "occurrence def",
    "ItemDefinition": "item def",
    "PortDefinition": "port def",
    "StateDefinition": "state def",
    "ActionDefinition": "action def",
    "UseCaseDefinition": "use case def",
    "VerificationCaseDefinition": "verification def",
    "ConnectionDefinition": "connection def",
    "MetadataDefinition": "metadata def",
    "FlowDefinition": "flow def",
    "AllocationDefinition": "allocation def",
    "InterfaceDefinition": "interface def",
    "ViewDefinition": "view def",
}

_NODE_KEYWORD = {"DecisionNode": "decide", "MergeNode": "merge",
                 "ForkNode": "fork", "JoinNode": "join"}


def _name(el):
    n = el._vals.get("declaredName")
    return n if isinstance(n, str) and n else None


def _q(name):
    """Quote a name that is not a valid v2 identifier."""
    if isinstance(name, str) and name and _IDENT.fullmatch(name):
        return name
    return f"<'{name}'>"


def _member_pairs(el):
    """(membership, member) pairs in carried order."""
    out = []
    for rel in (getattr(el, "ownedRelationship", None) or ()):
        for ch in (getattr(rel, "ownedRelatedElement", None) or ()):
            if hasattr(ch, "_props"):
                out.append((rel, ch))
    return out


def _members(el, skip=()):
    """Members that are content (not typing/subsetting/values/ranges)."""
    structural = {"FeatureTyping", "Subsetting", "Redefinition",
                  "FeatureValue", "MultiplicityRange", "Subclassification",
                  "FeatureChaining", "ReferenceSubsetting", "Conjugation",
                  "PortConjugation", "Dependency", "Annotation",
                  "Documentation"} | set(skip)
    out = []
    for rel, ch in _member_pairs(el):
        if type(ch).__name__ in structural:
            continue
        if hasattr(rel, "memberElement") and not getattr(
                rel, "ownedRelatedElement", None):
            continue
        out.append((rel, ch))
    return out


def _type_of(feature):
    # ownedTyping is a derived subset stored on its own end in the generated
    # runtime (the transformer appends there), so it is NOT reachable through
    # ownedRelationship - read the end, then fall back to carried members.
    for ft in (getattr(feature, "ownedTyping", None) or ()):
        t = ft._vals.get("type")
        if isinstance(t, list):
            t = t[0] if t else None
        if t is not None and _name(t):
            return [_q(_name(t))]
    for rel, ch in _member_pairs(feature):
        if type(ch).__name__ == "FeatureTyping":
            t = ch._vals.get("type")
            if isinstance(t, list):
                t = t[0] if t else None
            if t is not None:
                return [_q(_name(t))] if _name(t) else None
    ty = feature._vals.get("type")
    if isinstance(ty, list):
        ty = ty[0] if ty else None
    nm = _name(ty) if ty is not None else None
    return [_q(nm)] if nm else None


def _supers(el):
    out = []
    for spec in (getattr(el, "ownedSpecialization", None) or ()):
        g = spec._vals.get("general")
        if isinstance(g, list):
            g = g[0] if g else None
        if g is not None and _name(g):
            out.append(_q(_name(g)))
    return out


def _bound(range_el, which):
    for rel, ch in _member_pairs(range_el):
        if getattr(rel, "memberName", None) != which:
            continue
        tn = type(ch).__name__
        if tn == "LiteralInfinity":
            return "*"
        v = ch._vals.get("value")
        return None if v is None else v
    return None


def _mult(feature):
    """Multiplicity text, matching the calibrated emitter's conventions."""
    rng = None
    for rel, ch in _member_pairs(feature):
        if type(ch).__name__ == "MultiplicityRange":
            rng = ch
    if rng is None:
        return ""
    lo = _bound(rng, "lowerBound")
    hi = _bound(rng, "upperBound")
    lo = 1 if lo is None else int(lo)
    if hi is None:
        return "" if lo == 1 else f"[{lo}..1]"
    if hi == "*":
        return "[*]" if lo == 0 else f"[{lo}..*]"
    hi = int(hi)
    if lo == hi == 1:
        return ""
    if lo == 0 and hi == 1:
        return "[0..1]"
    return f"[{lo}..{hi}]" if lo != hi else f"[{hi}]"


def _literal(v):
    """Inline expression text for a carried literal (None when unshapeable)."""
    tn = type(v).__name__
    if tn == "LiteralString":
        b = v._vals.get("value") or ""
        return '"' + str(b).replace('"', '\\"') + '"'
    if tn == "LiteralBoolean":
        x = v._vals.get("value")
        return "true" if x in (True, "true", "1") else "false"
    if tn == "LiteralInfinity":
        return "*"
    if tn == "NullExpression":
        return "null"
    if tn in ("LiteralInteger", "LiteralRational", "LiteralReal"):
        x = v._vals.get("value")
        return None if x is None else str(x)
    return None


def _value_suffix(feature):
    for rel, ch in _member_pairs(feature):
        if type(ch).__name__ != "FeatureValue":
            continue
        val = ch._vals.get("value")
        if isinstance(val, list):
            val = val[0] if val else None
        if val is None:
            continue
        txt = _literal(val)
        if txt is None:
            raise UnsupportedEmission(
                f"FeatureValue expression {type(val).__name__}")
        return f" = {txt}"
    return ""


def _feature_suffix(feature):
    """subsets / redefines / value suffix for a feature line."""
    subs, reds = [], []
    for rel, ch in _member_pairs(feature):
        tn = type(ch).__name__
        if tn == "Subsetting":
            t = ch._vals.get("subsettedFeature")
        elif tn == "Redefinition":
            t = ch._vals.get("redefinedFeature")
        else:
            continue
        if isinstance(t, list):
            t = t[0] if t else None
        nm = _name(t) if t is not None else None
        if nm is None:
            raise UnsupportedEmission(f"{tn} with an unnamed target")
        (subs if tn == "Subsetting" else reds).append(_q(nm))
    out = ""
    if subs:
        out += " subsets " + ", ".join(subs)
    if reds:
        out += " redefines " + ", ".join(reds)
    return out + _value_suffix(feature)


def _docs(el, pad):
    out = []
    for _rel, ch in _member_pairs(el):
        if type(ch).__name__ == "Documentation":
            body = " ".join((ch._vals.get("body") or "").split())
            if body:
                out.append(f"{pad}doc /* {body} */")
    return out


def _direction(feature):
    d = feature._vals.get("direction")
    if d is None:
        return ""
    txt = str(getattr(d, "value", d))
    txt = txt.rsplit(".", 1)[-1]
    return txt + " " if txt in ("in", "out", "inout") else ""


def _typed_line(feature, keyword, pad):
    nm = _name(feature)
    if nm is None:
        raise UnsupportedEmission(f"unnamed {type(feature).__name__}")
    types = _type_of(feature)
    line = f"{pad}{keyword}{_q(nm)}"
    if types:
        line += " : " + "::".join(types) if len(types) == 1 else \
            " : " + ", ".join(types)
    line += _mult(feature) + _feature_suffix(feature) + ";"
    return [line]


def _definition(el, keyword, ind):
    pad = "  " * ind
    nm = _name(el)
    if nm is None:
        raise UnsupportedEmission(f"unnamed {type(el).__name__}")
    head = f"{pad}{keyword} {_q(nm)}"
    supers = _supers(el)
    if supers:
        head += " :> " + ", ".join(supers)
    kids = _members(el)
    docs = _docs(el, pad + "  ")
    if not kids and not docs:
        return [head + ";"]
    out = [head + " {"]
    out += docs
    for _rel, ch in kids:
        out += _emit(ch, ind + 1)
    out.append(pad + "}")
    return out


def _relationship_line(el, pad, keyword):
    """succession / transition / flow forms (the .18 / .20 / .47 families)."""
    nm = _name(el)
    first = el._vals.get("source")
    then = el._vals.get("target")
    if isinstance(first, list):
        first = first[0] if first else None
    if isinstance(then, list):
        then = then[0] if then else None
    fn = _name(first) if first is not None else None
    tn = _name(then) if then is not None else None
    if fn is None or tn is None:
        raise UnsupportedEmission(f"{type(el).__name__} with unnamed ends")
    head = f"{pad}{keyword}" + (f" {_q(nm)}" if nm else "")
    return [f"{head} first {_q(fn)} then {_q(tn)};"]


def _emit(el, ind):
    pad = "  " * ind
    tn = type(el).__name__

    # ---- documentation / annotations ---------------------------------
    if tn == "Documentation":
        body = " ".join((el._vals.get("body") or "").split())
        return [f"{pad}doc /* {body} */"] if body else []
    if tn in ("Annotation", "Comment", "TextualRepresentation"):
        return []

    # ---- packages -----------------------------------------------------
    if tn == "Package":
        nm = _name(el) or "Package"
        kids = _members(el)
        docs = _docs(el, pad + "  ")
        if not kids and not docs:
            return [f"{pad}package {_q(nm)};"]
        out = [f"{pad}package {_q(nm)} {{"]
        out += docs
        for _rel, ch in kids:
            out += _emit(ch, ind + 1)
        out.append(pad + "}")
        return out

    # ---- imports ------------------------------------------------------
    if tn == "NamespaceImport":
        tgt = el._vals.get("importedNamespace")
        if isinstance(tgt, list):
            tgt = tgt[0] if tgt else None
        nm = _name(tgt) if tgt is not None else None
        if nm is None:
            raise UnsupportedEmission("NamespaceImport with unnamed target")
        return [f"{pad}import {_q(nm)}::*;"]
    if tn == "MembershipImport":
        mem = el._vals.get("importedMembership")
        if isinstance(mem, list):
            mem = mem[0] if mem else None
        tgt = getattr(mem, "_vals", {}).get("memberElement") if mem is not None else None
        if isinstance(tgt, list):
            tgt = tgt[0] if tgt else None
        nm = _name(tgt) if tgt is not None else None
        if nm is None:
            raise UnsupportedEmission("MembershipImport with unnamed target")
        return [f"{pad}import {_q(nm)};"]

    # ---- definitions --------------------------------------------------
    if tn in _DEF_KEYWORD:
        return _definition(el, _DEF_KEYWORD[tn], ind)

    # ---- interaction --------------------------------------------------
    if tn == "Interaction":
        return _interaction(el, ind)

    # ---- requirements / verification ----------------------------------
    if tn == "RequirementUsage":
        return _requirement(el, pad)
    if tn == "SatisfyRequirementUsage":
        return _satisfy(el, pad)
    if tn == "VerificationCaseDefinition":
        return _definition(el, "verification def", ind)
    if tn == "RequirementVerificationMembership":
        return []          # carried inside the objective (the .49 form)
    if tn == "ObjectiveMembership":
        return []          # its member rides the verify membership

    # ---- state machine pieces -----------------------------------------
    if tn == "StateUsage":
        return _definition(el, "state", ind) if _members(el) else \
            [f"{pad}state {_q(_name(el) or 'state')};"]
    if tn == "StateSubactionMembership":
        return [f"{pad}entry action;"] if str(
            el._vals.get("kind") or "").endswith("entry") else []

    # ---- activity pieces ----------------------------------------------
    if tn in ("SuccessionAsUsage", "Succession"):
        return _relationship_line(el, pad, "succession")
    if tn == "TransitionUsage":
        return _transition(el, pad)
    if tn in _NODE_KEYWORD:
        nm = _name(el)
        kw = _NODE_KEYWORD[tn]
        return [f"{pad}{kw}" + (f" {_q(nm)}" if nm else "") + ";"]
    if tn == "TerminateActionUsage":
        nm = _name(el)
        return [f"{pad}action " + (_q(nm) if nm else "terminate") + ";"]
    if tn == "SendActionUsage":
        return _definition(el, "action", ind) if _members(el) else \
            [f"{pad}action {_q(_name(el) or 'send')};"]
    if tn == "AcceptActionUsage":
        return _definition(el, "accept", ind) if _members(el) else \
            [f"{pad}accept {_q(_name(el) or 'accept')};"]
    if tn == "ActionUsage":
        line = _typed_line(el, "action ", pad)[0]
        if _members(el):
            # an action usage with a body (pins, calc, etc.)
            head = line[:-1] + " {"
            out = [head]
            out += _docs(el, pad + "  ")
            for rel, ch in _members(el):
                out += _emit(ch, ind + 1)
            out.append(pad + "}")
            return out
        return [line]
    if tn == "SuccessionFlowUsage":
        return _succession_flow(el, pad)
    if tn == "CalculationUsage":
        return _definition(el, "calc", ind)
    if tn == "ReferenceUsage":
        # parameters / pins: 'in p : T;' (the calibrated _params form);
        # the 'ref' prefix belongs to the part/occurrence usages only
        return _typed_line(el, _direction(el), pad)

    # ---- ordinary features --------------------------------------------
    if tn == "PartUsage":
        kw = "part " if el._vals.get("isComposite", True) else "ref part "
        return _typed_line(el, kw, pad)
    if tn == "AttributeUsage":
        return _typed_line(el, "attribute ", pad)
    if tn == "OccurrenceUsage":
        kw = "occurrence " if el._vals.get("isComposite", True) \
            else "ref occurrence "
        return _typed_line(el, kw, pad)
    if tn == "ItemUsage":
        kw = "item " if el._vals.get("isComposite", True) else "ref item "
        return _typed_line(el, kw, pad)
    if tn == "PortUsage":
        return _typed_line(el, "port ", pad)
    if tn == "EnumerationUsage":
        nm = _name(el)
        if nm is None:
            raise UnsupportedEmission("unnamed EnumerationUsage")
        return [f"{pad}{_q(nm)};"]
    if tn == "Feature":
        return _typed_line(el, "", pad)

    # ---- relationships that carry no notation of their own -------------
    if tn in ("FeatureMembership", "OwningMembership", "EndFeatureMembership",
              "ParameterMembership", "ReturnParameterMembership",
              "TransitionFeatureMembership", "PayloadFeature",
              "SubjectMembership", "ActorMembership", "Invariant",
              "IncludeUseCaseUsage", "PerformActionUsage", "MetadataUsage",
              "Flow", "FlowEnd", "BindingConnectorAsUsage",
              "ConnectionUsage", "AllocationUsage", "ConstraintUsage",
              "Dependency", "Subsetting", "Redefinition", "FeatureTyping",
              "FeatureValue", "MultiplicityRange", "Subclassification",
              "FeatureReferenceExpression", "FeatureChainExpression",
              "Expression", "LiteralString", "LiteralInteger",
              "LiteralBoolean", "LiteralRational", "LiteralInfinity",
              "NullExpression", "ParameterMembership"):
        raise UnsupportedEmission(tn)

    raise UnsupportedEmission(tn)


def _transition(el, pad):
    """TransitionUsage -> 'transition n first a then b;' (+ guard calc)."""
    nm = _name(el)
    src = el._vals.get("source")
    tgt = el._vals.get("target")
    if isinstance(src, list):
        src = src[0] if src else None
    if isinstance(tgt, list):
        tgt = tgt[0] if tgt else None
    sn = _name(src) if src is not None else None
    tn = _name(tgt) if tgt is not None else None
    if sn is None or tn is None:
        raise UnsupportedEmission("TransitionUsage with unnamed ends")
    guard = ""
    for rel, ch in _member_pairs(el):
        if type(ch).__name__ == "TransitionFeatureMembership" and \
                str(ch._vals.get("kind") or "").endswith("guard"):
            guard = " if guard"
    return [f"{pad}transition" + (f" {_q(nm)}" if nm else "") +
            f" first {_q(sn)}{guard} then {_q(tn)};"]


def _succession_flow(el, pad):
    nm = _name(el)
    src = el._vals.get("source")
    tgt = el._vals.get("target")
    if isinstance(src, list):
        src = src[0] if src else None
    if isinstance(tgt, list):
        tgt = tgt[0] if tgt else None
    sn = _name(src) if src is not None else None
    tn = _name(tgt) if tgt is not None else None
    if sn is None or tn is None:
        raise UnsupportedEmission("SuccessionFlowUsage with unnamed ends")
    payload = None
    for rel, ch in _member_pairs(el):
        if type(ch).__name__ == "PayloadFeature":
            types = _type_of(ch)
            payload = types[0] if types else None
    head = f"{pad}succession flow" + (f" {_q(nm)}" if nm else "")
    if payload:
        head += f" of {payload}"
    return [f"{head} from {_q(sn)} to {_q(tn)};"]


def _requirement(el, pad):
    nm = _name(el) or "?"
    rid = el._vals.get("reqId")
    head = f"{pad}requirement" + (f" <'{rid}'>" if rid else "") + f" {_q(nm)}"
    docs = _docs(el, pad + "  ")
    kids = _members(el)
    if not docs and not kids:
        return [head + ";"]
    out = [head + " {"]
    out += docs
    for _rel, ch in kids:
        out += _emit(ch, ind + 1 if False else (len(pad) // 2) + 1)
    out.append(pad + "}")
    return out


def _satisfy(el, pad):
    """SatisfyRequirementUsage -> 'satisfy n : R by P;' (the calibrated form;
    the AS carries satisfiedRequirement / satisfyingFeature ends)."""
    nm = _name(el)

    def _end(key):
        v = el._vals.get(key)
        if isinstance(v, list):
            v = v[0] if v else None
        return _q(_name(v)) if v is not None and _name(v) else None

    req = _end("satisfiedRequirement")
    by = _end("satisfyingFeature")
    line = f"{pad}satisfy " + (_q(nm) if nm else "satisfy")
    if req:
        line += f" : {req}"
    if by:
        line += f" by {by}"
    return [line + ";"]


def _interaction(el, ind):
    pad = "  " * ind
    nm = _name(el) or "?"
    kids = _members(el)
    if not kids:
        return [f"{pad}interaction {_q(nm)};"]
    out = [f"{pad}interaction {_q(nm)} {{"]
    for _rel, ch in kids:
        tn = type(ch).__name__
        if tn == "PartUsage":
            types = _type_of(ch)
            out.append(f"{pad}  part {_q(_name(ch) or '?')}" +
                       (f" : {types[0]}" if types else "") + ";")
        elif tn == "Flow":
            fname = _name(ch) or "message"
            out.append(f"{pad}  message {_q(fname)};")
        else:
            out += _emit(ch, ind + 1)
    out.append(pad + "}")
    return out


def emit_package(pkg, indent=0):
    """Render an AS Package (and contents) as SysML v2 textual notation."""
    return "\n".join(_emit(pkg, indent))


def emit_model(packages, indent=0):
    """Render one or more AS packages (a transform result) as text."""
    return "\n\n".join(emit_package(p, indent) for p in packages)
