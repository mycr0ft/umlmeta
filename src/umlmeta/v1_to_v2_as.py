#!/usr/bin/env python
"""v1_to_v2_as.py — clean-room SysML v1 → v2 abstract-syntax transformer.

Requirement 3 of the transformation conformance clause (§2 of
formal/26-03-03 — SysML v2.0 Part 2): transform an abstract-syntax
representation of an input
SysML v1 model into an abstract-syntax representation of a SysML v2
model. This module constructs umlmeta.sysml2 objects (R2 artifact) from
umlmeta.uml25 + umlmeta.sysml objects (R1 artifacts) — the same normative
mappings v1_to_v2.py implements for textual notation, but building the
AS the clause demands.

Mapping authority: OMG "SysML v2.0 Beta 4, Part 2: SysML v1 to SysML v2
Transformation" (formal/26-03-03, SysML v2.0 Part 2, content
September 2025 — same normative machine-readable XMI as Beta 4;
anchors re-verified against the formal text), same anchors as
v1_to_v2.py. Anything
without a normative mapping raises UnmappedFeature.

Wave A: core structural mappings
  Block→PartDefinition (7.8.4.3.3) via ToPartUsage_Init family,
  Property typed by block + isComposite→PartUsage (7.8.4.3.13),
  non-composite block-typed Property→PartUsage w/ isComposite=false
  (the 'ref part' form), Property untyped→Feature, ValueType→
  AttributeDefinition (7.8.4.3.15), Enumeration→EnumerationDefinition,
  EnumerationLiteral→EnumerationUsage, ConstraintBlock→
  ConstraintDefinition (7.8.5.2.1), plain Class→OccurrenceDefinition,
  Property typed by plain Class→OccurrenceUsage (7.7.4.2.37),
  Generalization→Subclassification (7.7.4.2.12), typing via
  FeatureTyping (Core-Features), Comment→Documentation
  (7.4.2.1.9 ToDocumentation_Init).

Wave B: state machines and activities (7.7.11.2.x, 7.7.3.3.x) —
  States/Pseudostates/FinalStates→StateUsage, Transitions→
  TransitionUsage with source/target ends (ends = the mapped ends per
  the .2.18 rule; a transition from the initial sources the entry
  ActionUsage), regions inlined, initial → unnamed ActionUsage as the
  StateDefinition's entry subaction (7.7.11.2.8/.9, formal 2.0);
  OpaqueAction→ActionUsage, ControlFlow→SuccessionAsUsage, object
  flows→SuccessionFlowUsage.

Wave C: requirements chain (7.8.8.3.x) — Requirement→RequirementUsage
  (id on aliasIds, text→Documentation), TestCase→
  VerificationCaseDefinition, Satisfy→SatisfyRequirementUsage,
  Verify→RequirementVerificationMembership, DeriveReqt→ConnectionUsage,
  nested requirements; Dependency/Refine/Trace/Allocate.

Wave D: To*_Init realization (7.7.4.2.36 subsets/redefines/defaults,
  ports 7.7.12.2.36/.37 + 7.8.7.3.16, Operations→PerformActionUsage,
  Connectors→ConnectionUsage/BindingConnectorAsUsage, Signal→
  ItemDefinition/ItemUsage).

Wave E: use cases and interfaces — UseCase→UseCaseDefinition
  (7.7.13.3.4) with subject memberships, Include→IncludeUseCaseUsage
  (7.7.13.3.x, IncludeFeatureTyping to the addition's definition),
  Extend/ExtensionPoint not mapped (no normative target); InterfaceBlock→
  PortDefinition (7.8.7.3.16, replacing the wave-A PartDefinition
  carrier), InterfaceBlock-typed Property→OccurrenceUsage (7.7.4.2.37).
  See the To*_Init realization table in this file for the per-helper
  wiring/defaults/elided decisions over the normative SysMLv1Tov2.xmi
  mapping classes.

Wave F: imports and recursive namespaces — PackageImport→
  NamespaceImport and ElementImport→MembershipImport (7.7.9.3.12,
  visibility per Helper.getKerMLVisibilityKind with package→public;
  importedMembership = the AS OwningMembership of the imported element),
  and the transformer now populates nested packages recursively.

Wave G: associations and multiplicities — Association/AssociationClass
  → ConnectionDefinition (7.7.12.2.x; ends must be Usages) with
  memberEnd → end ReferenceUsages (isEnd) via EndFeatureMembership
  typed by the end definitions; v1 multiplicity bounds →
  MultiplicityRange 'multiplicity' with lowerBound/upperBound
  OwningMembership memberNames (LiteralInteger / LiteralInfinity for
  '*') carried under the feature/usage (textual parity: implicit
  [1..1] carries no multiplicity).

Wave J: conjugation (7.8.7.3.3/.20, 7.7.10.2.14) — InterfaceBlock→
  PortDefinition + an (unnamed) ConjugatedPortDefinition carrying a
  PortConjugation back to the port definition; U.Interface→
  PortDefinition with the '~'-named conjugated member
  (InterfaceConjugatedPortDefinition, '~'+name 7.7.10.2.15) - the
  conjugated-port TYPING stays plain (ToConjugatedPortTyping is a stub
  initializer with no triggering rule in the formal).

Wave I: interactions (7.7.8.3.x) — Interaction→Interaction; Lifeline→
  PartUsage typed by represents.type under FeatureMembership; Message→
  Flow (bare — the Message mapping has no rules; message-end
  occurrences are Table-11-unmapped); StateInvariant→Invariant typed
  by the invariant element; InteractionUse→Step typed by the refersTo
  interaction; ExecutionSpecification→ActionUsage EndFeatureMembership;
  CombinedFragment/InteractionOperand→nested Interactions under
  OwningMembership; plain occurrence specs/Continuations/Gates not
  mapped (Table 11).

Wave H: InformationFlow machinery — InformationFlow → FlowDefinition
  per the normative mapping class, with the normative filter (only
  flows realized by connectors/associations map; unrealized flows
  carry no AS artifact): ends → isEnd Features typed by the mapped
  end elements, conveyed → carried FeatureMembership members, an
  association realization → Subclassification to the realized
  ConnectionDefinition; reader tables extended for the InformationFlow
  end/carrier refs.

One v1 element maps to exactly ONE v2 AS object (kept in the index);
usage typings reference that object rather than duplicating it.

Honest elisions (documented, no data invented silently):
  - ElementImport alias → importedMemberName: no carrier in the
    generated AS runtime (documented elision; the import still
    resolves the named element).
  - MultiplicityMembership (the normative membership subtype for
    attached multiplicities) is not in the generated AS runtime; the
    range rides a FeatureMembership instead. Multiplicity is wired for
    properties, association ends, and behavior/operation parameters.
  - ElementFeatureMembership (the .18-tail guard rider) is likewise
    absent from the generated runtime; the guard's CalculationUsage
    rides a deviation FeatureMembership (itemized Part 32).
  - association end qualifiers/subsettings/defaults: later wave.
  - conjugated-port typing (ToConjugatedPortTyping is a stub
    initializer with no triggering mapping rule - the port carries
    isConjugated but types plainly), transition-from-initial message
    ends/payload (Table-11 occurrences behind them; the transition
    ENDS themselves are wired per the .2.18 rule), object-flow item
    ends (ObjectFlowItemFlowEnd/ToSuccessionItemFlow family), the
    transition's CommonReturnParameterReferenceUsageMembership
    (7.6.2.11), non-OpaqueExpression guard member forms,
    function synthesis, assignments, use-case objectives: elided (see
    the realization table) or raise UnmappedFeature.
"""
from __future__ import annotations

from . import uml25 as U
from . import sysml2 as S2
from . import sysml as S


class UnmappedFeature(Exception):
    """A v1 element whose normative v2 mapping is not implemented."""


def _name(el):
    n = getattr(el, "name", None)
    return n if isinstance(n, str) and n else None


def _own_membership(owner, member):
    """Owner gains *member* through an OwningMembership (the normative
    ownership mechanism for package members and nested definitions)."""
    om = S2.OwningMembership()
    om.ownedRelatedElement.append(member)
    owner.ownedRelationship.append(om)
    return om


def _feature_membership(owner_def, feature):
    """Owner gains *feature* through a FeatureMembership (the normative
    membership for features of a Type; makes the Type a featuringType)."""
    fm = S2.FeatureMembership()
    fm.ownedRelatedElement.append(feature)
    owner_def.ownedRelationship.append(fm)
    return fm


def _type_feature(feature, type_def):
    """FeatureTyping (§7.4.2.2.24 ToPortDefinition family / KerML
    Core-Features-FeatureTyping): feature.type = type_def. The typing is
    owned by the feature (ownedTyping), which back-wires owningFeature."""
    ft = S2.FeatureTyping()
    ft.type = type_def
    feature.ownedTyping.append(ft)
    return ft


def _attach_documentation(v1_el, v2_el):
    """ToDocumentation_Init (7.4.2.1.9): v1 Comment → Documentation
    owned by the transformed element (owner == documentedElement),
    plus an explicit Annotation relationship to the documented element
    (the Annotation.derived back-ends — annotatingElement, ownedAnnotation
    — are runtime-elided; the relationship itself is carried)."""
    docs = []
    for c in getattr(v1_el, "ownedComment", ()):
        d = S2.Documentation(body=c.body if isinstance(c.body, str) else None)
        _own_membership(v2_el, d)
        ann = S2.Annotation()
        ann.annotatedElement = v2_el
        d.ownedRelationship.append(ann)
        docs.append(d)
    return docs


def transform_v1_element(el, index=None):
    """Dispatch on v1 metaclass: build the v2 AS object per the
    normative mapping. Returns the v2 element (not yet owned).

    The index (id(v1) -> v2 AS object) is shared through the recursive
    population passes; pass-1 callers pass it so requirement/TestCase
    objects register before relationship ends resolve."""
    if index is None:
        index = {}
    if isinstance(el, U.Package):
        return S2.Package(declaredName=_name(el))
    if isinstance(el, S.ConstraintBlock):
        # ConstraintBlock_Mapping (7.8.5.2.1): to ConstraintDefinition
        # (before the Block check: ConstraintBlock specializes Block)
        return S2.ConstraintDefinition(declaredName=_name(el))
    if isinstance(el, S.InterfaceBlock):
        # InterfaceBlock_Mapping (7.8.7.3.16): to PortDefinition — the
        # normative typing target for Ports (7.7.12.2.36) and for
        # InterfaceBlock-typed properties (7.7.4.2.37). (Wave A carried
        # the AS as a PartDefinition; the port machinery check still
        # referenced the definition by identity.)
        return S2.PortDefinition(declaredName=_name(el))
    if isinstance(el, S.Block):
        # Block_Mapping (7.8.4.3.3): to PartDefinition
        return S2.PartDefinition(declaredName=_name(el))
    if isinstance(el, S.ValueType):
        # ValueType_Mapping (7.8.4.3.15): to AttributeDefinition
        return S2.AttributeDefinition(declaredName=_name(el))
    if isinstance(el, U.Enumeration):
        # Enumeration_Mapping: to EnumerationDefinition (before the
        # DataType check: Enumeration specializes DataType)
        return S2.EnumerationDefinition(declaredName=_name(el))
    if isinstance(el, U.DataType):
        # plain DataType (non-stereotyped): same mapping family as
        # ValueType -> AttributeDefinition (7.8.4.3.15)
        return S2.AttributeDefinition(declaredName=_name(el))
    if isinstance(el, U.EnumerationLiteral):
        # EnumerationLiteral_Mapping: to EnumerationUsage
        return S2.EnumerationUsage(declaredName=_name(el))
    if isinstance(el, U.Actor):
        # Actor_Mapping (7.7.13.3.1): to PartDefinition
        return S2.PartDefinition(declaredName=_name(el))
    if isinstance(el, (U.Signal, U.InformationItem)):
        # Signal_Mapping (7.7.10.2.22) / InformationItem_Mapping (7.7.7.2.7):
        # → ItemDefinition (Signal/InformationItem are Classifiers,
        # not Classes — dispatch must precede the Class check)
        return S2.ItemDefinition(declaredName=_name(el))
    if isinstance(el, U.UseCase):
        # UseCase_Mapping (7.7.13.3.4): to UseCaseDefinition; subject and
        # Include wiring ride the use-case population pass
        return S2.UseCaseDefinition(declaredName=_name(el))
    if isinstance(el, U.Interaction):
        # Interaction_Mapping (7.7.8.3.6): to Interaction; lifelines/
        # messages/fragments ride _populate_interaction
        return S2.Interaction(declaredName=_name(el))
    if isinstance(el, U.Interface):
        # Interface_Mapping (7.7.10.2.14): to PortDefinition; the
        # conjugated member ('~' + name, 7.7.10.2.15) and its
        # PortConjugation ride the population pass
        return S2.PortDefinition(declaredName=_name(el))
    if isinstance(el, U.StateMachine):
        # StateMachine_Mapping (7.7.11.2.16): to StateDefinition
        return S2.StateDefinition(declaredName=_name(el))
    if isinstance(el, (U.Activity, U.OpaqueBehavior)):
        # Activity_Mapping (7.7.3.3.1) / OpaqueBehavior: ActionDefinition
        return S2.ActionDefinition(declaredName=_name(el))
    if isinstance(el, U.Association):
        # Association_Mapping family (7.7.12.2.x; the machine-readable
        # AssociationClass_Mapping 'to' is Systems-Connections-
        # ConnectionDefinition and its ends must be Usages — plain
        # Association maps through the same abstract base):
        # memberEnds -> end ReferenceUsages via EndFeatureMembership
        return S2.ConnectionDefinition(declaredName=_name(el))
    if isinstance(el, U.Class):
        # Class_Mapping (7.7.4.2.37 family): plain Class to
        # OccurrenceDefinition. Metaclasses with their own normative
        # mappings (blocks, constraints, signals, use cases,
        # interactions, interfaces, associations, state machines,
        # activities) are dispatched before this catch-all - not
        # guesses.
        if isinstance(el, S.Requirement):
            # Requirement_Mapping (7.8.8.3.17)
            return _transform_requirement(el, index)
        if isinstance(el, S.TestCase):
            # TestCase_Mapping (7.8.8.3.27): TestCase →
            # VerificationCaseDefinition; the .3.35 rule set adds the
            # return verdict (VerdictKind-parameter ->
            # ReturnParameterMembership, .3.36) and the empty
            # subject/objective memberships (the factories) - the
            # objective is later carried by the verify's objective
            # membership (UniqueMapping: .3.37 wins over the empty)
            vcd = S2.VerificationCaseDefinition(declaredName=_name(el))
            for p in list(el.ownedParameter):
                pt = p._vals.get("type")
                if isinstance(pt, list):
                    pt = pt[0] if pt else None
                if pt is not None and _name(pt) == "VerdictKind":
                    rpm_v = S2.ReturnParameterMembership()
                    verdict_ref = S2.ReferenceUsage(
                        declaredName=_name(p), direction="out")
                    rpm_v.ownedRelatedElement.append(verdict_ref)
                    vcd.ownedRelationship.append(rpm_v)
            sm_e = S2.SubjectMembership()
            vcd.ownedRelationship.append(sm_e)
            om_e = S2.ObjectiveMembership()
            vcd.ownedRelationship.append(om_e)
            return vcd
        return S2.OccurrenceDefinition(declaredName=_name(el))
    raise UnmappedFeature(type(el).__name__)


def _as_type_name(t):
    """The v1 type object must have a name to be referenced; the
    transformation is name-resolving at package scope."""
    tn = _name(t)
    if tn is None:
        raise UnmappedFeature(
            f"property typed by unnamed {type(t).__name__}")
    return tn


def transform_property(prop, owner_def, index):
    """Property_Mapping (7.8.4.3.13 + 7.7.4.2.36): composite block-typed
    Property → PartUsage typed by the block's (already built) AS
    PartDefinition; non-composite → same PartUsage with
    isComposite=false (the 'ref part' form); value/enum/DataType-typed →
    AttributeUsage; plain-Class-typed → OccurrenceUsage (composite) or
    referential OccurrenceUsage; untyped → Feature.

    Helpers realized here: ToFeature_Init (defaults), ToFeatureMembership,
    ToFeatureTyping, ToFeatureValue (defaultValue → Expression carrier
    with a FeatureReferenceExpression for InstanceValue, 7.7.4.2.16),
    ToSubsetting_Init / ToRedefinition_Init / ToReferenceSubsetting_Init
    (subsettedProperty / redefinedProperty, 7.7.4.2.36), ToPartUsage /
    ToReferenceUsage / ToOccurrenceUsage / ToOccurenceDefinition,
    ToItemDefinition / ToItemUsage (Signal 7.7.10.2.22, InformationItem
  7.7.7.2.7),
    ToPortDefinition / ToPortUsage (Port machinery, 7.8.7.3.16 /
    7.7.12.2.36/.37), ToPerformActionUsage (Operation, 7.7.4.2.23),
    ToConnectionUsage (Connector, 7.7.12.2.14), ToBindingConnectorAsUsage
    (BindingConnector, 7.8.4.3.2)."""
    nm = _name(prop)
    t = prop._vals.get("type")
    composite = prop._vals.get("aggregation") is U.AggregationKind.composite
    if t is None:
        if isinstance(prop, (S.FullPort, U.Port)):
            # untyped ports (the port family dispatches before the
            # generic untyped-Feature rule):
            #   - a FULL port -> untyped PartUsage + PortData metadata
            #     (FullPortUntyped_Mapping, 7.8.7.3.15, via the same
            #     CommonFullPort construction, 7.8.7.3.2);
            #   - other ports -> bare PortUsage (PortUntyped_Mapping,
            #     7.7.12.2.37); ProxyPort rides the base Port mapping
            #     (Table 30 lists no full mapping; SYSML2_-329).
            if isinstance(prop, S.FullPort):
                usage = S2.PartUsage(declaredName=nm)
                _feature_membership(owner_def, usage)
                _attach_fullport_metadata(usage)
                index[id(prop)] = usage
                return usage
            usage = S2.PortUsage(declaredName=nm)
            _feature_membership(owner_def, usage)
            index[id(prop)] = usage
            return usage
        # normative: untyped Property → Feature (bare usage declaration)
        f = S2.Feature(declaredName=nm)
        _feature_membership(owner_def, f)
        index[id(prop)] = f
        return f
    tdef = index.get(id(t))
    if tdef is None:
        raise UnmappedFeature(
            f"Property {nm!r} typed by external/unordered "
            f"{type(t).__name__} {_as_type_name(t)!r}")
    if isinstance(prop, S.FullPort):
        # FullPort_Mapping (7.8.7.3.7 via CommonFullPort 7.8.7.3.2): a
        # full port maps to a PartUsage carrying the PortData metadata
        # machinery (7.8.7.3.8-.14). The SysMLv1Library::PortData
        # definition is EXTERNAL (the library is not part of the input),
        # so the metadata typing (.3.10) and the isFullPort Redefinition
        # (.3.14) have library objects as targets and are not
        # constructible: the member carries the NAME ('isFullPort', the
        # same name-reference treatment as DeriveReqt's Derivation
        # connection) and its FeatureValue LiteralBoolean(true) (.3.13).
        usage = S2.PartUsage(declaredName=nm)
        _type_feature(usage, tdef)
        _feature_membership(owner_def, usage)
        _attach_fullport_metadata(usage)
        index[id(prop)] = usage
        return usage
    if isinstance(prop, U.Port):
        # Port_Mapping family (7.7.12.2.36/.37, 7.8.7.3.16): typed by
        # InterfaceBlock → PortUsage typed by the interface's
        # PortDefinition; untyped → bare PortUsage. ProxyPort itself has
        # no normative mapping (Table 30; SYSML2_-329) — the base Port
        # mapping still applies (documented in the textual emitter).
        usage = S2.PortUsage(declaredName=nm)
        _type_feature(usage, tdef)
        _feature_membership(owner_def, usage)
        index[id(prop)] = usage
        return usage
    if isinstance(t, S.InterfaceBlock):
        # PropertyTypedByClassInterface (7.7.4.2.37): InterfaceBlock is
        # a Class — the reference is an OccurrenceUsage typed by the
        # PortDefinition (before the Block check: InterfaceBlock
        # specializes Block)
        usage = S2.OccurrenceUsage(declaredName=nm)
        if not composite:
            usage.isComposite = False     # referential occurrence
    elif isinstance(t, S.Block):
        usage = S2.PartUsage(declaredName=nm)
        if not composite:
            usage.isComposite = False     # 'ref part' (7.8.4.3.13)
    elif isinstance(t, (S.ValueType, U.DataType, U.Enumeration)):
        usage = S2.AttributeUsage(declaredName=nm)
    elif isinstance(t, (U.Signal, U.InformationItem)):
        usage = S2.ItemUsage(declaredName=nm)   # 7.7.10.2.22
    elif isinstance(t, U.Class):
        usage = S2.OccurrenceUsage(declaredName=nm)
        if not composite:
            usage.isComposite = False     # 'ref occurrence' (7.7.4.2.37)
    else:
        raise UnmappedFeature(
            f"Property {nm!r} typed by {type(t).__name__}")
    _type_feature(usage, tdef)
    _feature_membership(owner_def, usage)
    index[id(prop)] = usage
    return usage


def _stereo_metadata(el, feature):
    """7.8.2.3 (the activities metadata families): the
    Probability/Rate stereotypes on a v1 element carry the
    corresponding MetadataUsage on its mapped usage - the usage is
    typed (name-only; the SysMLv1Library MetadataDefinition is
    external) and the tag value rides a FeatureValue (the .5/.10
    ReferenceUsage-FeatureValue machinery, redefinition onto the
    library attribute name-only). Continuous/Discrete markers and the
    ControlValues library (Table 21's item definitions) are queued."""
    sters = getattr(el, "_applied_stereotypes", None) or []
    for _profile, stereo, _app_id in sters:
        if stereo not in ("Probability", "Rate"):
            continue
        tag = (getattr(el, "_stereo_tags", None) or {}).get(stereo, {})
        mu = S2.MetadataUsage(declaredName="SysMLv1Library::" + stereo)
        fm = S2.FeatureMembership()
        ru = S2.ReferenceUsage(
            declaredName="probability" if stereo == "Probability"
            else "rate")
        pv = tag.get("probability" if stereo == "Probability" else "rate")
        if pv not in (None, ""):
            fv = S2.FeatureValue()
            fv.value = S2.LiteralRational(value=float(pv))
            ru.ownedRelationship.append(fv)
        fm.ownedRelatedElement.append(ru)
        mu.ownedRelationship.append(fm)
        _own_membership(feature, mu)


def _attach_feature_extras(prop, usage, index):
    """Shared property→feature plumbing (7.7.4.2.36): subsets/redefines/
    defaultValue. subsetting/redefinition targets resolve by identity
    through the index (property → AS feature, populated by pass 2);
    a value becomes a FeatureValue whose owned expression is a
    FeatureReferenceExpression (InstanceValue → feature reference,
    7.7.4.2.16) or a literal-carried Expression. Multiplicity bounds
    ride _attach_multiplicity (MultiplicityElement_Mapping)."""
    _attach_multiplicity(prop, usage)
    subs = [t for t in list(prop.subsettedProperty)]
    for sub in subs:
        target = index.get(id(sub))
        if target is None:
            raise UnmappedFeature(
                f"Property {_name(prop)!r} subsets an unmapped/unnamed "
                f"{type(sub).__name__}")
        ss = S2.Subsetting()
        ss.subsettedFeature = target
        usage.ownedRelationship.append(ss)
    for red in list(prop.redefinedProperty):
        target = index.get(id(red))
        if target is None:
            raise UnmappedFeature(
                f"Property {_name(prop)!r} redefines an unmapped/unnamed "
                f"{type(red).__name__}")
        rd = S2.Redefinition()
        rd.redefinedFeature = target
        rd.redefiningFeature = usage
        usage.ownedRelationship.append(rd)
    dflt = prop._vals.get("defaultValue")
    if dflt is not None:
        if isinstance(dflt, list):        # raw single-store unwraps
            dflt = dflt[0] if dflt else None
    if dflt is not None:
        vs2 = _map_value_spec(dflt, index)
        if vs2 is not None:
            # 7.7.14.3.33: a literal default maps to the Literal-
            # Expression itself (return membership + typing)
            fv = S2.FeatureValue()
            fv.value = vs2
            usage.ownedRelationship.append(fv)
            return
        fv = S2.FeatureValue()
        val = dflt._vals.get("value") if isinstance(dflt, U.InstanceValue) \
            else None
        inst = dflt._vals.get("instance") if isinstance(dflt, U.InstanceValue) \
            else None
        expr = S2.FeatureReferenceExpression()
        if inst is not None:
            iname = _name(inst) or "instance"
            # v2 carries the instance by a literal reference to its name
            _own_membership(expr, S2.LiteralString(value=iname))
        else:
            spec = dflt._vals.get("specification") if hasattr(dflt, "_vals") \
                else None
            _own_membership(expr, S2.LiteralString(
                value=str(getattr(spec, "body", "") or "")))
        try:
            expr.referent = usage
        except AttributeError:
            pass
        fv.ownedRelatedElement.append(expr)
        usage.ownedRelationship.append(fv)


def _populate_class(v1cls, v2def, index, pending):
    """Features, nested classifiers and generalizations of a v1
    class-like element onto its AS definition (documentation was
    attached in pass 1)."""
    for attr in list(v1cls.ownedAttribute):
        transform_property(attr, v2def, index)
        index.setdefault("_prop_uses", []).append(attr)
    for op in list(v1cls.ownedOperation):
        # Operation_Mapping (7.7.4.2.23): → PerformActionUsage; the
        # operation name carries; parameters ride the perform's
        # ParameterMembership ends (7.7.4.2.24)
        pau = S2.PerformActionUsage(declaredName=_name(op))
        for prm in list(op.ownedParameter):
            ref = S2.ReferenceUsage(declaredName=_name(prm))
            d = prm._vals.get("direction")
            if d is not None:
                val = str(getattr(d, "value", d))
                ref.direction = "out" if val == "return" else val
            _attach_multiplicity(prm, ref)
            pm = S2.ParameterMembership()
            pm.ownedRelatedElement.append(ref)
            pau.ownedRelationship.append(pm)
        _feature_membership(v2def, pau)
    for conn in getattr(v1cls, "ownedConnector", ()):
        # Connector_Mapping (7.7.12.2.14) / BindingConnector (7.8.4.3.2):
        # → ConnectionUsage / BindingConnectorAsUsage between the
        # connected roles (resolved through the property index)
        roles = []
        for end in list(conn.end):
            r = end._vals.get("role")
            r_usage = index.get(id(r)) if r is not None else None
            if r_usage is None:
                raise UnmappedFeature(
                    f"Connector {_name(conn)!r} end with unmapped role")
            roles.append(r_usage)
        if isinstance(conn, S.BindingConnector):
            cu = S2.BindingConnectorAsUsage(declaredName=_name(conn))
            if len(roles) >= 2:
                cu.source.append(roles[0])
                cu.target.append(roles[1])
        else:
            cu = S2.ConnectionUsage(declaredName=_name(conn))
            if len(roles) >= 2:
                cu.source.append(roles[0])
                cu.target.append(roles[1])
        _feature_membership(v2def, cu)
    for nested in getattr(v1cls, "nestedClassifier", ()):
        nv2 = transform_v1_element(nested)
        index[id(nested)] = nv2
        _own_membership(v2def, nv2)
        _populate_class(nested, nv2, index, pending)
    for g in list(v1cls.generalization):
        pending.append((v2def, g))


def _populate_usecase(uc, v2def, index, pkg):
    """UseCase internals (7.7.13.3.x, per the normative SysMLv1Tov2.xmi
    mapping classes):

    - Include → IncludeUseCaseUsage owned by the including definition
      (FeatureMembership; the metamodel constraint requires the owning
      type to be UseCaseDefinition/UseCaseUsage), typed by the addition's
      UseCaseDefinition — IncludeFeatureTyping_Mapping.type = from.addition.
      Includes are the UseCase's ownedMembers / the containing package's
      Include relationships (the v1 runtime's UseCase.include is a pure
      derived union with no storage, the same fallback the validated
      textual emitter uses).
    - subject → SubjectMembership whose ownedMemberParameter is a
      ReferenceUsage 'subject_<name>' typed by the subject's definition
      (UseCaseSubjectMembership_Mapping + UseCaseSubjectReferenceUsage_
      Mapping: declaredName = 'subject_' + subject->get(0).name; the
      mapping class supports one subject). Subject-less use cases get
      no SubjectMembership (the EmptySubjectReferenceUsage stub of the
      mapping is left un-carried, as it is a factory default).
    - ObjectiveMembership / ReturnParameterFeatureMembership /
      actor memberships (UseCaseActorMembership), classifier behavior:
      elided — v1 carries no objective, the actor machinery is the
      elided ToActorMembership_Init of the realization table.
    """
    pkg_members = list(pkg.ownedMember) + list(uc.ownedMember)

    # Includes: Include relationships whose includingCase is this use case
    includes = [m for m in pkg_members if isinstance(m, U.Include)]
    includes = [inc for inc in includes
                if inc._vals.get("includingCase") is uc] \
        + list(uc._vals.get("include") or [])
    includes = list(dict.fromkeys(includes))
    for inc in includes:
        addition = inc._vals.get("addition")
        adef = index.get(id(addition)) if addition is not None else None
        if adef is None:
            raise UnmappedFeature(
                f"Include with external/unordered addition "
                f"{_name(addition)!r}")
        iucu = S2.IncludeUseCaseUsage(declaredName=_name(inc))
        _type_feature(iucu, adef)
        _feature_membership(v2def, iucu)

    # subject: the classifier(s) whose useCase association end names this
    # use case (UML: Classifier.useCase; UseCase.subject is a pure
    # derived union, the same fallback pattern as Include). The normative
    # mapping class supports exactly one subject; the first wins.
    subjects = [c for c in pkg_members
                if isinstance(c, U.Class)  # only Class can carry the
                and uc in (c._vals.get("useCase") or [])]  # useCase end
    if subjects:
        subj = subjects[0]
        sdef = index.get(id(subj))
        if sdef is None:
            raise UnmappedFeature(
                f"UseCase subject {type(subj).__name__!r} not mapped first")
        ru = S2.ReferenceUsage(
            declaredName="subject_" + (_name(subj) or "?"))
        _type_feature(ru, sdef)
        sm = S2.SubjectMembership()
        sm.ownedRelatedElement.append(ru)
        v2def.ownedRelationship.append(sm)

    # actors: associations with a memberEnd typed by this use case carry
    # the actor end (each OTHER memberEnd) as a PartUsage (named from
    # the end) owned via ActorMembership — UseCaseActorMembership_Mapping
    # (ownedMemberParameter = UseCaseActor_Mapping result: "the PartUsage
    # representing an actor of the use case", typed by the actor's AS
    # definition via UseCaseActorFeatureTyping).
    for assoc in pkg_members:
        if not isinstance(assoc, U.Association):
            continue
        ends = [e for e in (assoc._vals.get("memberEnd") or [])]
        if not any(e._vals.get("type") is uc for e in ends):
            continue
        for end in ends:
            actor_type = end._vals.get("type")
            if actor_type is uc or actor_type is None:
                continue
            adef = index.get(id(actor_type))
            if adef is None:
                raise UnmappedFeature(
                    f"use case actor end {_name(end)!r} typed by "
                    f"external/unordered {type(actor_type).__name__}")
            pu = S2.PartUsage(declaredName=_name(end))
            _type_feature(pu, adef)
            am = S2.ActorMembership()
            am.ownedRelatedElement.append(pu)
            v2def.ownedRelationship.append(am)


def _attach_fullport_metadata(usage):
    """FullPort MetadataUsage machinery (7.8.7.3.8-.14; the
    FullPortMetadataOwningMembership rule of
    CommonFullPort_Mapping 7.8.7.3.2): the part usage gains an
    OwningMembership (.3.11) owning a MetadataUsage (.3.8) whose
    FeatureMembership (.3.9) carries a ReferenceUsage named
    'isFullPort' (.3.12 - the member name of the external library's
    SysMLv1Library::PortData::isFullPort, carried by name as with
    DeriveReqt's Derivation connection) with a FeatureValue (.3.13)
    LiteralBoolean(true). The library-dependent typing (.3.10) and
    Redefinition (.3.14) are not constructible without the library
    object (elided, documented)."""
    mu = S2.MetadataUsage()
    ru = S2.ReferenceUsage(declaredName="isFullPort")
    fv = S2.FeatureValue()
    lit = S2.LiteralBoolean()
    lit.value = True
    fv.ownedRelatedElement.append(lit)
    ru.ownedRelationship.append(fv)
    fm = S2.FeatureMembership()
    fm.ownedRelatedElement.append(ru)
    mu.ownedRelationship.append(fm)
    om = S2.OwningMembership()
    om.ownedRelatedElement.append(mu)
    usage.ownedRelationship.append(om)


def _attach_port_conjugation(iface_v1, pdef, named):
    """ConjugatedPortDefinition_Mapping (7.8.7.3.3) +
    PortConjugation_Mapping (7.8.7.3.20): the interface's PortDefinition
    owns a ConjugatedPortDefinition (unnamed for InterfaceBlock per the
    mapping class, '~' + name for UML::Interface per the
    InterfaceConjugatedPortDefinition_Mapping); the conjugated
    definition carries a PortConjugation whose originalPortDefinition
    is the PortDefinition and whose conjugatedType (derived) is the
    conjugated definition itself.

    ToConjugatedPortTyping_Init (7.4.2.2.7) stays elided: the stub has
    NO triggering mapping rule in the formal - a conjugated port still
    types its PortUsage plainly by the original PortDefinition
    (7.7.12.2.36's rules are inherited-only)."""
    conj = S2.ConjugatedPortDefinition(
        declaredName=("~" + (_name(iface_v1) or "?")) if named else None)
    pc = S2.PortConjugation()
    pc.originalPortDefinition = pdef
    conj.ownedRelationship.append(pc)
    _own_membership(pdef, conj)


def _populate_interaction(ix, v2def, index):
    """Interactions internals (7.7.8.3.x, formal 2.0):

    - Lifelines -> PartUsages (7.7.8.3.13) typed by mapped
      represents.type (7.7.8.3.14), carried by LifelineMembership
      (7.7.8.3.12 -> FeatureMembership; PartUsage is a Feature);
    - Messages -> Flow (7.7.8.3.15; ItemFlow in the prose = the KerML
      Flow payload family; the machine-readable target class is Flow)
      via MessageMembership (7.7.8.3.16 -> FeatureMembership). The
      Message mapping has NO rules of its own, so the flow carries no
      ends/payload: message-end occurrences are Table-11-unmapped
      (7.7.8.2).
    - StateInvariants -> Invariants (7.7.8.3.17) typed by the mapped
      invariant element (7.7.8.3.19) under
      StateInvariantMembership (7.7.8.3.18).
    - InteractionUses -> Steps (7.7.8.3.9) typed by the mapped
      refersTo interaction (7.7.8.3.11) under
      InteractionUseMembership (7.7.8.3.10).
    - ExecutionSpecifications -> ActionUsages (7.7.8.3.1/.2) under
      ExecutionSpecificationMembership (7.7.8.3.5 ->
      EndFeatureMembership).
    - CombinedFragments -> nested Interactions (7.7.8.3.3) under
      CombinedFragmentMembership (7.7.8.3.4 -> OwningMembership: the
      nested piece is a Type, not a Feature), with their operands ->
      nested Interactions (7.7.8.3.7) under
      InteractionOperandMembership (7.7.8.3.8 -> OwningMembership).
    - Plain OccurrenceSpecifications and Continuations are NOT mapped
      (Table 11, 7.7.8.2) - recorded, never silently lost (the
      interaction's remaining ownedElements ride generic memberships
      per the Interaction rule's `elements` set)."""
    for member in list(ix.ownedMember):
        if isinstance(member, (U.Lifeline, U.Message, U.Comment,
                               U.InteractionFragment,
                               U.OccurrenceSpecification)):
            continue   # handled below / Table-11-unmapped / docs in pass 1
        mv2 = transform_v1_element(member, index)
        _own_membership(v2def, mv2)
        index[id(member)] = mv2
        _attach_documentation(member, mv2)

    for ll in list(ix.ownedMember):
        if not isinstance(ll, U.Lifeline):
            continue
        rep = ll._vals.get("represents")
        rt = rep._vals.get("type") if rep is not None else None
        rdef = index.get(id(rt)) if rt is not None else None
        if rdef is None:
            raise UnmappedFeature(
                f"Lifeline {_name(ll)!r} typed by external/unordered "
                f"{type(rt).__name__ if rt is not None else 'none'}")
        pu = S2.PartUsage(declaredName=_name(ll))
        _type_feature(pu, rdef)
        fm = S2.FeatureMembership()
        fm.ownedRelatedElement.append(pu)
        v2def.ownedRelationship.append(fm)
        index[id(ll)] = pu

    for m1 in list(ix.ownedMember):
        if not isinstance(m1, U.Message):
            continue
        fl = S2.Flow(declaredName=_name(m1))
        fm = S2.FeatureMembership()
        fm.ownedRelatedElement.append(fl)
        v2def.ownedRelationship.append(fm)
        index[id(m1)] = fl

    for frag in list(ix.fragment):
        if isinstance(frag, U.StateInvariant):
            itype_el = frag._vals.get("invariant")
            i_obj = index.get(id(itype_el[0])) if itype_el else None
            if i_obj is None:
                raise UnmappedFeature(
                    f"StateInvariant {_name(frag)!r} invariant element "
                    f"external/unordered")
            iv = S2.Invariant(declaredName=_name(frag))
            _type_feature(iv, i_obj)
            fm = S2.FeatureMembership()
            fm.ownedRelatedElement.append(iv)
            v2def.ownedRelationship.append(fm)
            index[id(frag)] = iv
        elif isinstance(frag, U.InteractionUse):
            ref = frag._vals.get("refersTo")
            rdef = index.get(id(ref)) if ref is not None else None
            if rdef is None or not isinstance(rdef, S2.Interaction):
                raise UnmappedFeature(
                    f"InteractionUse {_name(frag)!r} refersTo external/"
                    f"unordered interaction")
            st = S2.Step(declaredName=_name(frag))
            _type_feature(st, rdef)
            fm = S2.FeatureMembership()
            fm.ownedRelatedElement.append(st)
            v2def.ownedRelationship.append(fm)
            index[id(frag)] = st
        elif isinstance(frag, U.ExecutionSpecification):
            au = S2.ActionUsage(declaredName=_name(frag))
            em = S2.EndFeatureMembership()
            em.ownedRelatedElement.append(au)
            v2def.ownedRelationship.append(em)
            index[id(frag)] = au
        elif isinstance(frag, U.CombinedFragment):
            cfi = S2.Interaction(declaredName=_name(frag))
            om2 = S2.OwningMembership()
            om2.ownedRelatedElement.append(cfi)
            v2def.ownedRelationship.append(om2)
            index[id(frag)] = cfi
            for op in list(frag.ownedElement):
                if not isinstance(op, U.InteractionOperand):
                    continue
                opf = S2.Interaction(declaredName=_name(op))
                omp = S2.OwningMembership()
                omp.ownedRelatedElement.append(opf)
                cfi.ownedRelationship.append(omp)
                index[id(op)] = opf
    # remaining fragment kinds (plain OccurrenceSpecifications,
    # Continuations, Gates) are Table-11-unmapped: recorded in the
    # element lists, never carried


def _populate_association(assoc, conn, index):
    """Association_Mapping internals (7.7.12.2.x; the machine-readable
    AssociationClass_Mapping 'to' is ConnectionDefinition, whose ends
    must be Usages): memberEnds -> end ReferenceUsages in memberEnd
    order, each owned via EndFeatureMembership (isEnd), typed by the
    end type's definition, with the end's multiplicity (7.7.12.2.x
    NonOwnedEnd/OwnedEnd family's typing + multiplicity memberships).
    Qualifiers/subsettings/defaults on ends are later-wave."""
    for e in list(assoc.memberEnd):
        ru = S2.ReferenceUsage(declaredName=_name(e))
        ru.isEnd = True
        t = e._vals.get("type")
        if t is not None:
            tdef = index.get(id(t))
            if tdef is None:
                raise UnmappedFeature(
                    f"connection end {_name(e)!r} typed by "
                    f"external/unordered {type(t).__name__} "
                    f"{_as_type_name(t)!r}")
            _type_feature(ru, tdef)
        em = S2.EndFeatureMembership()
        em.ownedRelatedElement.append(ru)
        conn.ownedRelationship.append(em)
        index[id(e)] = ru
        _attach_multiplicity(e, ru)


def _bound_value(mult_el, val_name):
    """A v1 multiplicity bound (lowerValue/upperValue literal) as an
    int or '*' — the same read the validated textual emitter uses."""
    lit = mult_el._vals.get(val_name)
    v = lit._vals.get("value") if isinstance(lit, U._Element) else None
    if isinstance(v, U.UnlimitedNatural):
        return "*" if v.unbounded else v.n
    return v


def _attach_multiplicity(mult_el, feature):
    """MultiplicityElement_Mapping (7.7.12.2.x family): v1 multiplicity
    bounds -> MultiplicityRange named 'multiplicity', its bound
    OwningMemberships named 'lowerBound'/'upperBound' (per the
    MultiplicityLower/UpperBoundOwningMembership_Mapping memberNames)
    carrying LiteralInteger / LiteralInfinity for '*'.

    Textual parity (the validated textual emitter): implicit [1..1]
    carries no multiplicity at all; absent lower is the UML default 1.
    Carrier deviation (documented): the normative membership subtype
    MultiplicityMembership is not in the generated AS runtime, so the
    range attaches through a FeatureMembership under the feature."""
    lo = _bound_value(mult_el, "lowerValue")
    hi = _bound_value(mult_el, "upperValue")
    lo = 1 if lo is None else int(lo)
    if (hi in (None, 1)) and lo == 1:
        return   # implicit [1..1]: no carrier (textual parity)
    hi_is_star = (hi == "*")
    hi_n = -1 if hi_is_star else (1 if hi is None else int(hi))

    def bound_lit(value_n, star):
        if star:
            return S2.LiteralInfinity()
        lit = S2.LiteralInteger()
        lit.value = value_n
        return lit

    rng = S2.MultiplicityRange(declaredName="multiplicity")
    for name, lit in (("lowerBound", bound_lit(lo, False)),
                      ("upperBound", bound_lit(hi_n, hi_is_star))):
        om = S2.OwningMembership()
        om.memberName = name
        om.ownedRelatedElement.append(lit)
        rng.ownedRelationship.append(om)
    fm = S2.FeatureMembership()
    fm.ownedRelatedElement.append(rng)
    feature.ownedRelationship.append(fm)


def _populate_statemachine(sm, v2def, index):
    """StateMachine internals (7.7.11.2.x): Regions inlined — States/
    Pseudostates/FinalStates → StateUsage; Transitions → TransitionUsage
    with source/target ends. InitialState (7.7.11.2.8, formal 2.0 — no
    longer the Beta-4 elision): an initial Pseudostate maps to an
    unnamed ActionUsage carried as the entry subaction
    (StateSubactionMembership, kind=entry, 7.7.11.2.9) of the
    StateDefinition."""
    for member in list(sm.ownedMember):
        if isinstance(member, U.Region):
            for st in list(member.ownedMember):
                if isinstance(st, U.Transition):
                    continue
                if isinstance(st, U.Pseudostate) \
                        and st._vals.get("kind") is U.PseudostateKind.initial:
                    # InitialState_Mapping (7.7.11.2.8) +
                    # InitialStateSubactionMembership_Mapping (7.7.11.2.9):
                    # initial -> unnamed ActionUsage carried as the ENTRY
                    # subaction (StateSubactionMembership, kind=entry) of the
                    # StateDefinition (the formal 2.0 behavior; the Beta-4
                    # elision is gone)
                    au = S2.ActionUsage()
                    ssm = S2.StateSubactionMembership()
                    ssm.kind = S2.StateSubactionKind.entry
                    ssm.ownedRelatedElement.append(au)
                    v2def.ownedRelationship.append(ssm)
                    index[id(st)] = au
                    continue
                su = S2.StateUsage(declaredName=_name(st))
                _own_membership(v2def, su)
                index[id(st)] = su
            for tr in list(member.ownedMember):
                if not isinstance(tr, U.Transition):
                    continue
                src, tgt = tr._vals.get("source"), tr._vals.get("target")
                # 7.7.11.2.18's ends rule is literal - source/target are
                # the mapped ends: a transition FROM the initial sources
                # the (unnamed) entry ActionUsage now that initial
                # pseudostates map (7.7.11.2.8)
                src_obj = index.get(id(src))
                tgt_obj = index.get(id(tgt))
                if src_obj is None or tgt_obj is None:
                    raise UnmappedFeature(
                        f"Transition {_name(tr)!r} to element outside the "
                        "state machine's owned states")
                tu = S2.TransitionUsage(declaredName=_name(tr))
                tu.source = src_obj
                tu.target = tgt_obj
                # 7.7.11.2.19-.25: the transition's Succession with the
                # named ('source'/'target') end features, isEnd,
                # subsetting the mapped states
                sux = S2.Succession()
                for end_nm, end_v in (("source", src_obj),
                                      ("target", tgt_obj)):
                    fe = S2.Feature(declaredName=end_nm)
                    fe.isEnd = True
                    ss = S2.Subsetting()
                    ss.subsettedFeature = end_v
                    fe.ownedRelationship.append(ss)
                    em = S2.EndFeatureMembership()
                    em.ownedRelatedElement.append(fe)
                    sux.ownedRelationship.append(em)
                tu.ownedRelationship.append(sux)
                # 7.7.11.2.26: the trigger feature memberships
                for tg in list(tr._vals.get("trigger") or ()):
                    tu.ownedRelationship.append(
                        _trigger_carrier(tg, tg._vals.get("event"), index))
                _own_membership(v2def, tu)
                index[id(tr)] = tu


def _map_value_spec(vs, index):
    """ValueSpecification_Mapping (7.7.14.3.33) + the literal family
    (7.7.14.3.8-.16): a LiteralSpecification maps to its SysML v2
    LiteralExpression - LiteralInteger -> LiteralInteger (.9),
    LiteralBoolean -> LiteralBoolean (.8), LiteralString ->
    LiteralString (.14), LiteralReal -> LiteralRational (.11),
    LiteralNull -> NullExpression (.10), LiteralUnlimitedNatural ->
    LiteralInfinity when -1 (the unlimited filter, .15) else
    LiteralInteger (.16) - carrying the .33 return membership
    (CommonReturnParameterFeatureMembership) and the literal's own
    typing when it states one (LiteralSpecificationTyping). Returns
    None for value-specification kinds without a literal mapping (the
    caller's calibrated machinery applies)."""
    lit = None
    if isinstance(vs, U.LiteralUnlimitedNatural):
        if vs._vals.get("value") == -1:
            lit = S2.LiteralInfinity()
        else:
            lit = S2.LiteralInteger(value=int(vs._vals.get("value") or 0))
    elif isinstance(vs, U.LiteralInteger):
        lit = S2.LiteralInteger(value=int(vs._vals.get("value") or 0))
    elif isinstance(vs, U.LiteralString):
        lit = S2.LiteralString(value=vs._vals.get("value") or "")
    elif isinstance(vs, U.LiteralBoolean):
        lit = S2.LiteralBoolean(value=bool(vs._vals.get("value")))
    elif isinstance(vs, U.LiteralReal):
        lit = S2.LiteralRational(value=float(vs._vals.get("value") or 0.0))
    elif isinstance(vs, U.LiteralNull):
        lit = S2.NullExpression()
    else:
        return None
    rpm = S2.ReturnParameterMembership()
    rpm.ownedRelatedElement.append(S2.ReferenceUsage(direction="out"))
    lit.ownedRelationship.append(rpm)
    ty = vs._vals.get("type") if hasattr(vs, "_vals") else None
    if ty is not None:
        ty2 = index.get(id(ty)) if index is not None else None
        if ty2 is not None:
            ft = S2.FeatureTyping()
            ft.type = ty2
            lit.ownedTyping.append(ft)
    return lit


def _opaque_repr(lang, body):
    """OABody_Mapping (7.7.2.3.2.3): a UML opaque language/body pair ->
    TextualRepresentation with the language/body stored as SINGLETON
    lists (the UML ends are multi [0..*]; the normative text reads
    language/body.first()- shaped singletons; the constructor-kw path
    would iterate a lone string into single characters)."""
    r = S2.TextualRepresentation()
    for name, v in (("language", lang), ("body", body)):
        if v is None or v == "":
            continue
        r._vals[name] = [v] if isinstance(v, str) else list(v)
    return r


def _opaque_body_repr(owner, opaque_el):
    """OABodyMembership_Mapping (7.7.2.3.2.4): the body's
    TextualRepresentation joins the element via OwningMembership."""
    lang = opaque_el._vals.get("language")
    body = opaque_el._vals.get("body")
    if body is None and lang is None:
        return None
    _own_membership(owner, _opaque_repr(lang, body))
    return True


def _opaque_expr_calc(oe, index):
    """OpaqueExpression_Mapping (7.7.14.3.18): an OpaqueExpression as a
    value-specification -> CalculationUsage carrying the guard's
    language/body as its TextualRepresentation and the required
    'result' return parameter (out) - the .3.18 example form
    'calc <oe> { return result : <Boolean>; language ... }'. The
    return's type is the library ScalarValues::Boolean (external -
    carried by the direction + name only, as elsewhere)."""
    cu = S2.CalculationUsage(declaredName=_name(oe))
    ref = S2.ReferenceUsage(declaredName="result")
    ref.direction = "out"
    rpm = S2.ReturnParameterMembership()
    rpm.ownedRelatedElement.append(ref)
    cu.ownedRelationship.append(rpm)
    lang = oe._vals.get("language")
    body = oe._vals.get("body")
    if body is not None or lang is not None:
        _own_membership(cu, _opaque_repr(lang, body))
    return cu


def _edge_end(se, node, subset_target, is_src, cls, ref_layer):
    """CommonActivityEdgeSuccessionAsUsage_Mapping (7.7.3.3.18) end
    machinery. The source end: ActivityEdgeSourceEndFeature_Mapping
    (7.7.3.3.10, a Feature/FlowEnd with isEnd) under
    EndFeatureMembership (7.7.3.3.12), subsetting the mapped end
    (7.7.3.3.11); the target end likewise (7.7.3.3.25/.26). For an
    ObjectFlow the ends are FlowEnds (7.7.3.3.59) and the end's
    feature membership carries a ReferenceUsage redefined onto the
    mapped node (7.7.3.3.61/.60, .3.62; for the generic node case the
    redefinition target IS the mapped node - the library
    redefinitions of the special action pins need SysMLv1Library and
    stay elided). Control successions carry no .61 layer - that rule
    is object-flow (item-flow-end) specific."""
    fe = cls()
    fe.isEnd = True
    ss = S2.Subsetting()          # 7.7.3.3.11/.63: end :> mapped end
    ss.subsettedFeature = subset_target
    fe.ownedRelationship.append(ss)
    if ref_layer:
        # 7.7.3.3.61/.60: the end's reference-usage layer
        ru2 = S2.ReferenceUsage(declaredName=_name(node))
        rd = S2.Redefinition()
        rd.redefinedFeature = subset_target
        ru2.ownedRelationship.append(rd)
        fm2 = S2.FeatureMembership()
        fm2.ownedRelatedElement.append(ru2)
        fe.ownedRelationship.append(fm2)
    em = S2.EndFeatureMembership()
    em.ownedRelatedElement.append(fe)
    se.ownedRelationship.append(em)
    if is_src:
        se.source.append(fe)
    else:
        se.target.append(fe)


def _edge_param_in_membership(src_node, index):
    """CommonParameterReferenceUsageInMembership_Mapping (7.6.2.3):
    a ParameterMembership owning a ReferenceUsage with direction in
    (CommonParameterReferenceUsageIn_Mapping, 7.6.2.4), typed by the
    source node's type when it has one (7.6.2.5 typing) - the untyped
    form carries no typing."""
    ref = S2.ReferenceUsage()
    ref.direction = "in"
    st = src_node._vals.get("type")
    if st is not None:
        st2 = index.get(id(st))
        if st2 is not None:
            ft = S2.FeatureTyping()
            ft.type = st2
            ref.ownedTyping.append(ft)
    # ownedMemberParameter is a derived/composite end in the runtime -
    # the owning pass is the base Membership's ownedRelatedElement
    pm = S2.ParameterMembership()
    pm.ownedRelatedElement.append(ref)
    return pm


def _guarded_edge_transition(e, src_obj, tgt_obj, src_node,
                             target_subset, index):
    """ControlFlowTransitionUsage_Mapping (7.7.3.3.20) /
    ObjectFlowGuard_Mapping (7.7.3.3.50): a guarded activity edge maps
    (additionally, for an ObjectFlow which keeps its .47 flow) to a
    TransitionUsage carrying the .20 rule set: the .15 source
    Membership; 7.6.2.3's in-ParameterMembership; the .28/.64 guard
    TransitionFeatureMembership (kind=guard) whose member is the
    OpaqueExpressionAsValue FeatureChainExpression (7.7.14.3.17) with
    its own in ParameterMembership and out ReturnParameterMembership;
    and the CommonActivityEdgeSuccessionAsUsage (.18)
    SuccessionAsUsage carried INSIDE the transition - its target end
    subsetting the mapped flow for an ObjectFlow (7.7.3.3.51-.53) -
    with the guard's CalculationUsage (7.7.14.3.18) riding it via
    FeatureMembership (the .18-tail ElementFeatureMembership: the same
    deviation family as MultiplicityMembership - ElementFeature-
    Membership is absent from the generated runtime). Queued: the
    transition's CommonReturnParameterReferenceUsageMembership
    (7.6.2.11) and the non-OpaqueExpression guard member forms."""
    guard_el = e._vals.get("guard")
    if guard_el is None:
        return None
    guard = guard_el[0] if isinstance(guard_el, list) else guard_el
    if guard is None:
        return None
    if not isinstance(guard, U.OpaqueExpression):
        raise UnmappedFeature(
            f"edge {_name(e)!r} guard {type(guard).__name__} - only "
            "the OpaqueExpression guard member forms map")
    tu = S2.TransitionUsage(declaredName=_name(e))
    tu.source = src_obj
    # 7.7.3.3.15: the source-node Membership
    src_m = S2.Membership()
    src_m.memberElement = src_obj
    tu.ownedRelationship.append(src_m)
    # 7.6.2.3: the in-ParameterMembership
    tu.ownedRelationship.append(_edge_param_in_membership(src_node, index))
    # 7.7.3.3.28/.64: kind=guard; 7.7.14.3.17: the AsValue chain
    fce = S2.FeatureChainExpression()
    prm = S2.ParameterMembership()
    prm.ownedRelatedElement.append(S2.ReferenceUsage(direction="in"))
    fce.ownedRelationship.append(prm)
    rpm = S2.ReturnParameterMembership()
    rpm.ownedRelatedElement.append(S2.ReferenceUsage(direction="out"))
    fce.ownedRelationship.append(rpm)
    tfm = S2.TransitionFeatureMembership()
    tfm.kind = S2.TransitionFeatureKind.guard
    tfm.ownedRelatedElement.append(fce)
    tu.ownedRelationship.append(tfm)
    # 7.7.3.3.18: the SuccessionAsUsage inside the transition; the
    # .18-tail guard rider (ElementFeatureMembership -> deviating
    # FeatureMembership) carries the guard's CalculationUsage
    se = S2.SuccessionAsUsage(declaredName=_name(e))
    se.source.append(src_obj)
    se.target.append(tgt_obj)
    _edge_end(se, src_node, src_obj, True, S2.Feature, False)
    _edge_end(se, src_node, target_subset, False, S2.Feature, False)
    fm_g = S2.FeatureMembership()
    fm_g.ownedRelatedElement.append(_opaque_expr_calc(guard, index))
    se.ownedRelationship.append(fm_g)
    tu.ownedRelationship.append(se)
    return tu


def _trigger_carrier(tg, ev, index):
    """TransitionTriggerFeatureMembership_Mapping (7.7.11.2.26). A
    TimeEvent trigger maps to a CalculationUsage
    (TimeTriggerCalculationUsage_Mapping, 7.7.5.3.35: the return
    parameter membership + the feature membership carrying the 'at'
    expression); a ChangeEvent trigger maps to a ConstraintUsage
    (ChangeTriggerConstraintUsage_Mapping, 7.7.5.3.6: the feature
    membership + the return parameter membership). The invocation /
    binding end of the trigger machinery (7.7.5.3.7-.34, .5.36-.55 -
    the invocation expressions, event chaining features and binding
    connectors riding the library expression features) is queued; the
    expression text carries as a feature-reference literal - the same
    shape as the doc/defaults machinery. The membership returns the
    FeatureMembership to carry on the transition (the .26 rule) with
    the carrier inside it."""
    if ev is None:
        raise UnmappedFeature(f"Trigger {_name(tg)!r} with no event")
    if not isinstance(ev, (U.TimeEvent, U.ChangeEvent)):
        raise UnmappedFeature(
            f"Trigger {_name(tg)!r} event {type(ev).__name__} - only "
            "the time/change event forms map")
    if isinstance(ev, U.TimeEvent):
        carrier = S2.CalculationUsage(declaredName=_name(tg))
        when = ev._vals.get("when")
        expr = getattr(when, "expr", None) if when is not None else None
    else:
        carrier = S2.ConstraintUsage(declaredName=_name(tg))
        expr = ev._vals.get("changeExpression")
    rpm = S2.ReturnParameterMembership()
    rpm.ownedRelatedElement.append(
        S2.ReferenceUsage(declaredName="result", direction="out"))
    carrier.ownedRelationship.append(rpm)
    body = expr._vals.get("body") if isinstance(expr, U.OpaqueExpression) \
        else None
    fm = S2.FeatureMembership()
    fre = S2.FeatureReferenceExpression()
    if body:
        _own_membership(fre, S2.LiteralString(value=body))
    fm.ownedRelatedElement.append(fre)
    carrier.ownedRelationship.append(fm)
    ms = S2.FeatureMembership()
    ms.ownedRelatedElement.append(carrier)
    return ms


def _populate_activity(act, v2def, index):
    """Activity internals (7.7.3.3.x): nodes → action usages /
    control-node usages; edges → SuccessionAsUsage (ControlFlow) or
    SuccessionFlowUsage (ObjectFlow) with source/target."""
    nodes = list(act.node)
    edges = list(act.edge)
    for n in nodes:
        nm = _name(n)
        if isinstance(n, U.OpaqueAction):
            au = S2.ActionUsage(declaredName=nm)
            _own_membership(v2def, au)
            index[id(n)] = au
            _opaque_body_repr(au, n)   # OABody (7.7.2.3.2.3/.4)
            # Pin_Mapping (7.7.2.3.2.5) + ValuePin (.6): the action's
            # pins -> ReferenceUsages carried on the action (in/out by
            # the pin's orientation - the .2.5 example form
            # 'action a { in inPin : Integer; out outPin; }'), typed by
            # the pin's type, with the pin's multiplicity
            # (MultiplicityElement_Mapping); a ValuePin's value becomes
            # the FeatureValue (ValuePinFeatureValue_Mapping .2.7)
            for kind, pins in (("in", n._vals.get("_input") or ()),
                               ("out", n._vals.get("_output") or ())):
                for pin in list(pins):
                    pu_ref = S2.ReferenceUsage(declaredName=_name(pin))
                    pu_ref.direction = kind
                    pt = pin._vals.get("type")
                    if pt is not None:
                        pdef = index.get(id(pt))
                        if pdef is None:
                            raise UnmappedFeature(
                                f"Pin {_name(pin)!r} typed by "
                                f"external/unordered {type(pt).__name__}")
                        _type_feature(pu_ref, pdef)
                    _attach_multiplicity(pin, pu_ref)
                    pval = pin._vals.get("value")
                    if pval is not None:
                        # ValuePinFeatureValue_Mapping (7.7.2.3.2.7):
                        # the value rides a FeatureValue on the pin's
                        # reference usage; an InstanceValue carries as a
                        # feature reference, anything else as a
                        # literal-carried expression (the same shape the
                        # defaultValue plumbing, 7.7.4.2.16, builds)
                        fv = S2.FeatureValue()
                        expr = S2.FeatureReferenceExpression()
                        inst = pval._vals.get("instance") \
                            if isinstance(pval, U.InstanceValue) else None
                        if inst is not None:
                            expr.referent = index.get(id(inst))
                        spec = pval._vals.get("specification") \
                            if hasattr(pval, "_vals") else None
                        body = getattr(spec, "body", None)
                        if isinstance(body, str) and body.strip() \
                                and expr.referent is None:
                            expr.ownedRelatedElement.append(S2.LiteralString(
                                value=body.strip()))
                        fv.value = expr
                        pu_ref.ownedRelationship.append(fv)
                    _feature_membership(au, pu_ref)
                    index[id(pin)] = pu_ref
        elif isinstance(n, U.DecisionNode):
            du = S2.DecisionNode(declaredName=nm)
            _own_membership(v2def, du)
            index[id(n)] = du
        elif isinstance(n, U.MergeNode):
            mu = S2.MergeNode(declaredName=nm)
            _own_membership(v2def, mu)
            index[id(n)] = mu
        elif isinstance(n, (U.InitialNode, U.FinalNode)):
            # normative: elided (initial → source feature of outgoing
            # edges; final → done-subsetted feature; 7.7.3.3.22)
            continue
        else:
            raise UnmappedFeature(
                f"Activity node {type(n).__name__} (later wave)")
    for e in edges:
        src, tgt = e._vals.get("source"), e._vals.get("target")
        src_obj, tgt_obj = index.get(id(src)), index.get(id(tgt))
        if src_obj is None or tgt_obj is None:
            # initial/final nodes elided: the edge itself is elided
            if isinstance(src, (U.InitialNode, U.FinalNode)) or \
                    isinstance(tgt, (U.InitialNode, U.FinalNode)):
                continue
            raise UnmappedFeature(
                f"edge {_name(e)!r} touching unmapped node")
        if isinstance(e, U.ObjectFlow):
            se = S2.SuccessionFlowUsage(declaredName=_name(e))
            # ObjectFlow_Mapping (7.7.3.3.47): the ends are the mapped
            # ends - the end machinery (7.7.3.3.58/.59/.63, chained
            # source/target); the payload rides the source ObjectNode:
            # PayloadFeature (7.7.3.3.54, unnamed) typed by the node's
            # type (.3.56) under a FeatureMembership (.3.55) - the
            # 'succession flow ... of <Type>' payload.
            for node, is_src in ((src, True), (tgt, False)):
                _edge_end(se, node, index.get(id(node)), is_src,
                          S2.FlowEnd, True)
            nt = getattr(src, "_vals", {}).get("type")
            if nt is not None:
                ndef = index.get(id(nt))
                if ndef is None:
                    raise UnmappedFeature(
                        f"ObjectFlow {_name(e)!r} payload type external/"
                        f"unordered {type(nt).__name__} {_as_type_name(nt)!r}")
                pf = S2.PayloadFeature()
                _type_feature(pf, ndef)
                pfm = S2.FeatureMembership()
                pfm.ownedRelatedElement.append(pf)
                se.ownedRelationship.append(pfm)
            _own_membership(v2def, se)
            index[id(e)] = se
            # a guarded object flow ALSO carries the full .50 guard
            # transition; its internal succession's target end subsets
            # the mapped flow (7.7.3.3.51-.53)
            gtu = _guarded_edge_transition(e, src_obj, tgt_obj, src,
                                           se, index)
            if gtu is not None:
                _own_membership(v2def, gtu)
            continue
        # 7.7.3.3.18: the control flow's end machinery (the same
        # shape the object flows carry, without the .61 layer)
        se = S2.SuccessionAsUsage(declaredName=_name(e))
        if e._vals.get("guard") is None:
            se.source.append(src_obj)
            se.target.append(tgt_obj)
            _edge_end(se, src, src_obj, True, S2.Feature, False)
            _edge_end(se, tgt, tgt_obj, False, S2.Feature, False)
            _own_membership(v2def, se)
            index[id(e)] = se
            continue
        # ControlFlowTransitionUsage_Mapping (7.7.3.3.20): a guarded
        # control flow maps to a TransitionUsage (the filter routes
        # the guarded edge here only) whose .18 succession rides
        # INSIDE the transition - the activity carries the transition,
        # not a bare succession
        tu2 = _guarded_edge_transition(e, src_obj, tgt_obj, src,
                                       tgt_obj, index)
        _own_membership(v2def, tu2)
        index[id(e)] = tu2


def _populate_behavior_params(behavior, v2def):
    """Parameter → ReferenceUsage with direction (7.7.4.2.24; return →
    out per the Activity textual example); the parameter's multiplicity
    rides _attach_multiplicity (MultiplicityElement_Mapping)."""
    for p in list(behavior.ownedParameter):
        ref = S2.ReferenceUsage(declaredName=_name(p))
        d = p._vals.get("direction")
        if d is not None:
            val = str(getattr(d, "value", d))
            # normative (7.7.4.2.24): return -> out per the Activity
            # textual example
            ref.direction = "out" if val == "return" else val
        _attach_multiplicity(p, ref)
        # 7.8.2.3: the parameter's Probability/Rate metadata
        _stereo_metadata(p, ref)
        _feature_membership(v2def, ref)


def transform_package(pkg):
    """MainMapping (§7.2.2.4): transform a v1 Package (and contents)
    into a v2 AS Package. Returns the v2 root Package.

    pass 1: one AS definition per v1 member, recursively (the index is
    the conformance-critical identity: every reference resolves to it);
    pass 2: features/nested members/imports per owner namespace;
    pass 2.5: feature extras once the whole tree is indexed;
    pass 3: relationship ends (requirements chain, generalizations)
    resolved against the index by identity.
    """
    out = S2.Package(declaredName=_name(pkg) or "Package")
    index = {}   # id(v1 element) -> v2 AS object
    ns_pairs = []   # (v1 namespace, AS namespace) in discovery order

    _populate_namespace(pkg, out, index, ns_pairs)

    # pass 2.5: feature extras (subsets/redefines/values, 7.7.4.2.36)
    # after ALL owners populated so cross-block targets resolve
    for prop in index.get("_prop_uses", []):
        usage = index.get(id(prop))
        if usage is not None:
            _attach_feature_extras(prop, usage, index)
            _stereo_metadata(prop, usage)
    index.pop("_prop_uses", None)

    # pass 3: relationship machinery per namespace (7.7.13.3.x imports
    # wired in pass 2; 7.8.8.3.x chain members resolve ends here)
    for ns_v1, ns2 in ns_pairs:
        for el in list(ns_v1.ownedMember):
            if isinstance(el, S.Satisfy):
                _transform_satisfy(el, ns2, index)
            elif isinstance(el, S.Verify):
                _transform_verify(el, ns2, index)
            elif isinstance(el, S.DeriveReqt):
                _transform_derive_reqt(el, ns2, index)
            elif isinstance(el, (U.Abstraction, U.Dependency)):
                _transform_dependency(el, ns2, index,
                                      annotated=isinstance(el, (S.Refine,
                                                                S.Trace)))
            elif isinstance(el, S.Allocate):
                _transform_allocate(el, ns2, index)
            elif isinstance(el, U.InformationFlow):
                _transform_informationflow(el, ns2, index)

    # pass 3 (cont.): imports wire per namespace once the whole tree is
    # indexed (7.7.9.3.12); membership search walks the full AS tree
    index["_as_root"] = out
    for ns_v1, ns2 in ns_pairs:
        _populate_imports(ns_v1, ns2, index)

    for sub_def, g in index.get("_gens", []):
        t = g._vals.get("general")
        general = index.get(id(t))
        if general is None:
            raise UnmappedFeature(
                f"generalization to external/unnamed {_name(t)!r}")
        subc = S2.Subclassification()
        subc.general = general
        sub_def.ownedSpecialization.append(subc)
    return out


_SKIP_PASS1 = (S.Satisfy, S.Verify, S.DeriveReqt, S.Allocate,
               U.Abstraction, U.Dependency, U.Include, U.Extend,
               U.PackageImport, U.ElementImport, U.InformationFlow)


def _populate_namespace(ns_v1, ns2, index, ns_pairs):
    """pass 1 + pass 2 for ONE namespace level, recursing into nested
    packages. Wave F: the transformer previously populated only the top
    level, which both left nested definitions untransformed and made
    imports on nested namespaces unwireable.

    pass 1: definitions + memberships (+ nested recursion); pass 2:
    per-owner population. Include/Extend are relationship-owned use-case
    machinery (Include wires in _populate_usecase, Extend is normatively
    unmapped); PackageImport/ElementImport wire via _populate_imports."""
    ns_pairs.append((ns_v1, ns2))
    for el in list(ns_v1.ownedMember):
        if isinstance(el, _SKIP_PASS1):
            # Include/Extend: built in pass 2 / normatively unmapped;
            # PackageImport/ElementImport: wired via _populate_imports
            continue
        v2 = transform_v1_element(el, index)
        index[id(el)] = v2
        _own_membership(ns2, v2)
        _attach_documentation(el, v2)
        if isinstance(el, U.Enumeration):
            for lit in list(el.ownedLiteral):
                lv2 = S2.EnumerationUsage(declaredName=_name(lit))
                _feature_membership(v2, lv2)
        if isinstance(el, U.Package):
            _populate_namespace(el, v2, index, ns_pairs)

    # pass 2: features / nested members / collected generalizations
    for el in list(ns_v1.ownedMember):
        v2 = index.get(id(el))
        if v2 is None:
            continue
        if isinstance(el, (U.StateMachine, U.Activity, U.OpaqueBehavior)):
            if isinstance(el, U.StateMachine):
                _populate_statemachine(el, v2, index)
            else:
                _populate_activity(el, v2, index)
                _populate_behavior_params(el, v2)
        elif isinstance(el, U.Interface):
            # Interface attributes/operations ride the generic classifier
            # machinery (7.7.10.2.14 example: 'attribute <prop>;')
            _populate_class(el, v2, index, pending_local(index))
            _attach_port_conjugation(el, v2, named=True)
        elif isinstance(el, U.Interaction):
            _populate_interaction(el, v2, index)
        elif isinstance(el, U.Association):
            # before the Class branch: AssociationClass specializes BOTH
            _populate_association(el, v2, index)
        elif isinstance(el, U.Class):
            _populate_class(el, v2, index, pending_local(index))
        elif isinstance(el, U.UseCase):
            _populate_usecase(el, v2, index, ns_v1)
        if isinstance(el, (U.Class, U.Interface)) \
                and isinstance(el, S.InterfaceBlock) \
                and v2 is not None:
            # ConjugatedPortDefinition_Mapping (7.8.7.3.3): the interface
            # block's port definition owns an (unnamed) conjugated
            # definition carrying a PortConjugation back to it
            # (7.8.7.3.20) - the conjugation machinery of the formal
            _attach_port_conjugation(el, v2, named=False)

    # imports (7.7.9.3.12) wire in global pass 3: importing namespaces
    # at any level can reference sibling/deeper namespaces that index
    # only after every level's pass 1


def pending_local(index):
    """Generalizations collected per namespace pass 2 ride the shared
    pending list held on the index (resolutions run once at the end)."""
    return index.setdefault("_gens", [])


def _visibility_v1_to_v2(vis):
    """Helper.getKerMLVisibilityKind (normative SysMLv1Tov2.xmi):
    public→public, protected→protected, private→private,
    package→public; a missing v1 visibility is the UML default
    'public' for PackageImport/ElementImport."""
    name = str(getattr(vis, "value", vis) or "public")
    name = name.rsplit(".", 1)[-1]
    if name == "package":
        return S2.VisibilityKind.public
    lit = {l.name: l for l in S2.VisibilityKind}.get(name)
    if lit is None:
        raise UnmappedFeature(f"visibility {vis!r} has no KerML mapping")
    return lit


def _populate_imports(ns_v1, ns2, index):
    """NamespaceImport/MembershipImport wiring (7.7.9.3.12, per the
    normative PackageImport_Mapping / ElementImport_Mapping):

    - PackageImport → NamespaceImport: importedNamespace = the AS
      namespace of the imported package; visibility per Helper
      (package → public).
    - ElementImport → MembershipImport: importedMembership = the AS
      OwningMembership that owns the imported element's definition
      (ElementOwningMembership_Mapping.getMapped(from.importedElement)),
      so the import aliases the SAME membership (importedElement is
      derived: importedMembership.memberElement). The v1 alias →
      importedMemberName has no carrier in the generated AS runtime
      (documented elision).

    Import relationship ownership: OwningMembership under the importing
    namespace (importOwningNamespace is the owningRelatedElement).
    Targets outside the transformed scope raise UnmappedFeature."""
    for pi in list(ns_v1._vals.get("packageImport") or []):
        tgt = index.get(id(pi.importedPackage)) if pi.importedPackage \
            is not None else None
        if tgt is None:
            raise UnmappedFeature(
                f"PackageImport of external/unordered "
                f"{_name(pi.importedPackage)!r}")
        ni = S2.NamespaceImport()
        ni.importedNamespace = tgt
        ni._vals["visibility"] = _visibility_v1_to_v2(
            pi._vals.get("visibility"))
        _own_membership(ns2, ni)
    for ei in list(ns_v1._vals.get("elementImport") or []):
        tgt_el = ei._vals.get("importedElement")
        tgt_def = index.get(id(tgt_el)) if tgt_el is not None else None
        if tgt_def is None:
            raise UnmappedFeature(
                f"ElementImport of external/unordered "
                f"{_name(tgt_el)!r}")
        mem = _owning_membership_of(index.get("_as_root"), tgt_def)
        if mem is None:
            raise UnmappedFeature(
                f"ElementImport of {_name(tgt_el)!r} with no AS "
                f"owning membership in scope")
        mi = S2.MembershipImport()
        mi.importedMembership = mem
        mi._vals["visibility"] = _visibility_v1_to_v2(
            ei._vals.get("visibility"))
        _own_membership(ns2, mi)


def _owning_membership_of(root, target):
    """The OwningMembership owning *target*, found by walking the
    namespace tree under *root* (BFS over namespace-owned
    relationships)."""
    seen = set()
    queue = [root]
    while queue:
        cur = queue.pop(0)
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        for om in list(cur.ownedRelationship):
            if not isinstance(om, S2.OwningMembership):
                continue
            if target in om.ownedRelatedElement:
                return om
            for owned in om.ownedRelatedElement:
                if isinstance(owned, S2.Namespace):
                    queue.append(owned)
    return None


# --------------------------------------------------------------------------
# requirements chain (7.8.8.3.x)
# --------------------------------------------------------------------------

def _transform_requirement(req, index):
    """Requirement_Mapping (7.8.8.3.17): Requirement → RequirementUsage
    with the v1 id carried as the requirement's declaredShortId-style
    text (the textual example puts the id in quotes next to the name);
    text → Documentation (normative: text → doc)."""
    ru = S2.RequirementUsage(declaredName=_name(req))
    rid = req._vals.get("id")
    if isinstance(rid, str) and rid:
        # the id travels as an aliasIds-style metadata comment in the
        # textual form; in AS it is carried on the usage's element
        ru.aliasIds.append(rid)
    txt = req._vals.get("text")
    if isinstance(txt, str) and txt:
        doc = S2.Documentation(body=txt)
        _own_membership(ru, doc)
    _attach_documentation(req, ru)
    index[id(req)] = ru
    return ru


def _transform_satisfy(sat, out, index):
    """Satisfy_Mapping (7.8.8.3.22): Satisfy → SatisfyRequirementUsage;
    v1 client (the satisfying part) → satisfyingFeature; v1 supplier
    (the requirement) → satisfiedRequirement."""
    clients = [index.get(id(c)) for c in list(sat.client)]
    reqs = [index.get(id(s)) for s in list(sat.supplier)]
    if not clients or not any(cl for cl in clients) \
            or not any(s for s in list(sat.supplier)):
        raise UnmappedFeature("Satisfy without mapped client/supplier")
    sru = S2.SatisfyRequirementUsage(declaredName=_name(sat))
    for cl in clients:
        if cl is not None:
            sru.satisfyingFeature = cl
            break
    for s in sat.supplier:
        r = index.get(id(s))
        if r is not None:
            sru.satisfiedRequirement = r
            break
    _own_membership(out, sru)
    return sru


def _transform_verify(verify, out, index):
    """Verify_Mapping (7.8.8.3.49): Verify → the verification case's
    RequirementVerificationMembership; the v1 supplier requirement is
    the verifiedRequirement; the v1 client (TestCase) must already be a
    VerificationCaseDefinition in the index."""
    tc = next((index.get(id(c)) for c in list(verify.client)
               if index.get(id(c)) is not None
               and type(index.get(id(c))).__name__
               == "VerificationCaseDefinition"), None)
    if tc is None:
        raise UnmappedFeature(
            "Verify whose client is not a mapped TestCase")
    req = next((index.get(id(s)) for s in list(verify.supplier)
                if index.get(id(s)) is not None), None)
    if req is None:
        raise UnmappedFeature("Verify without mapped supplier requirement")
    rvm = S2.RequirementVerificationMembership()
    rvm.verifiedRequirement = req
    # 7.8.8.3.49/.40: the RVM carries the verify's requirements
    # usage - required by the ReferenceSubsetting to the mapped
    # requirement, with the usage's own empty subject membership +
    # the return reference membership
    r40 = S2.RequirementUsage(declaredName=_name(verify))
    rs = S2.ReferenceSubsetting()
    rs.referencedFeature = req
    r40.ownedRelationship.append(rs)
    sm0 = S2.SubjectMembership()
    r40.ownedRelationship.append(sm0)
    rpm0 = S2.ReturnParameterMembership()
    rpm0.ownedRelatedElement.append(S2.ReferenceUsage(direction="out"))
    r40.ownedRelationship.append(rpm0)
    rvm.ownedRelatedElement.append(r40)
    # 7.8.8.3.37/.38: the objective requirement usage carries the
    # verify; the VCD's empty objective membership (the .3.35
    # factory) is replaced by the real objective (UniqueMapping)
    obj_ru = S2.RequirementUsage(
        declaredName="objective_" + (_name(verify.client[0])
                                     if list(verify.client) else None))
    obj_ru.ownedRelationship.append(rvm)
    om = S2.ObjectiveMembership()
    om.ownedObjectiveRequirement = obj_ru
    replaced = False
    for i, rel in enumerate(tc.ownedRelationship):
        inner = [rel] if type(rel).__name__ == "ObjectiveMembership" \
            else ((list(rel.ownedRelatedElement)
                   if type(rel).__name__ == "OwningMembership" else []))
        if any(type(x).__name__ == "ObjectiveMembership" and not getattr(
                x, "ownedObjectiveRequirement", None) for x in inner):
            tc.ownedRelationship[i] = om
            om._owner = tc
            replaced = True
            break
    if not replaced:
        _own_membership(tc, om)
    return om


def _transform_derive_reqt(dr, out, index):
    """DeriveReqt_Mapping (7.8.8.3.1): DeriveReqt → ConnectionUsage
    typed by the DerivationConnections::Derivation model-library
    connection (referenced by qualified name; the library itself is
    external — the same name reference the textual form emits)."""
    client = next((index.get(id(c)) for c in list(dr.client)
                   if index.get(id(c)) is not None), None)
    supplier = next((index.get(id(s)) for s in list(dr.supplier)
                     if index.get(id(s)) is not None), None)
    if client is None or supplier is None:
        raise UnmappedFeature(
            "DeriveReqt without mapped client/supplier requirements")
    cu = S2.ConnectionUsage(declaredName=_name(dr))
    # the typing target is the library-defined Derivation; carried by
    # name — wave-1 notes the FeatureTyping would need the library
    # package, which is not part of the input model
    cu.source.append(client)
    cu.target.append(supplier)
    _own_membership(out, cu)
    return cu


def _transform_dependency(dep, out, index, annotated=False):
    """Dependency_Mapping (7.7.6.2.9): Dependency/Realization/Abstraction
    → Dependency; Refine/Trace annotated with v1-library metadata."""
    clients = [index.get(id(c)) for c in list(dep.client)]
    suppliers = [index.get(id(s)) for s in list(dep.supplier)]
    if not any(clients) or not any(suppliers):
        raise UnmappedFeature("dependency without mapped client/supplier")
    dep2 = S2.Dependency(declaredName=_name(dep))
    for cl in clients:
        if cl is not None:
            dep2.client.append(cl)
    for sp in suppliers:
        if sp is not None:
            dep2.supplier.append(sp)
    if annotated:
        # Refine/Trace_Mapping (7.8.8.3.9-.15 / .41-.48): the
        # dependency is annotated with a MetadataUsage typing the
        # v1-library data definition (RefineData/TraceData - the
        # library itself is external, so the FeatureTyping target is
        # carried by qualified NAME, as in the DeriveReqt machinery);
        # the usage carries 'isRefine'/'isTrace' whose FeatureValue is
        # LiteralBoolean(true) (the .13/.45 factories). The
        # redefinition onto the library attribute
        # (RefineMetadataReferenceUsageRedefinition, .14/.46) needs
        # SysMLv1Library and stays name-only.
        mdata = S2.MetadataUsage(declaredName=_name(dep))
        fm = S2.FeatureMembership()
        ru = S2.ReferenceUsage(
            declaredName="isRefine" if isinstance(dep, S.Refine)
            else "isTrace")
        fv = S2.FeatureValue()
        fv.value = S2.LiteralBoolean(value=True)
        ru.ownedRelationship.append(fv)
        fm.ownedRelatedElement.append(ru)
        mdata.ownedRelationship.append(fm)
        # Annotation::annotatingElement is a derived end in the
        # runtime - the owning pass is the base Membership's
        # ownedRelatedElement
        ann = S2.Annotation()
        ann.ownedRelatedElement.append(mdata)
        dep2.ownedRelationship.append(ann)
    _own_membership(out, dep2)
    return dep2


def _transform_informationflow(flow, out, index):
    """InformationFlow_Mapping (7.7.9.x family, per the normative
    machine-readable mapping class): an InformationFlow is mapped to a
    FlowDefinition ONLY when it has realizing connectors or an
    association realization (the mapping's filter — anything else is
    normatively-not-mapped and carries no AS artifact). One
    FlowDefinition is created per realizing element. Wiring per the
    mapping class:

    - informationSource/informationTarget -> InformationFlowEnd
      FeatureMembership members: isEnd Features typed by the mapped
      end elements (InformationFlowFeatureTyping.type = the mapped
      element's AS object);
    - conveyed Classifiers -> carried FeatureMembership members
      (InformationFlowConveyedFeatureMembership ->
      InformationItemFlowConveyedItemUsage family) typed by the
      conveyed classifier's AS object;
    - an association realization -> Subclassification from the
      FlowDefinition to the realized ConnectionDefinition (wave G
      association machinery provides the definition).

    Realizing-connectors are the flow's own ends in the underlying
    structure; the event-occurrence machinery of the mapping factories
    (InformationFlowEventOccurrenceUsage) stays elided, as does the
    ObjectFlowItemFlowEnd family (ToItemFlow_Init rows)."""
    reals = [r for r in (flow._vals.get("realization") or [])]
    conns = [c for c in (flow._vals.get("realizingConnector") or [])]
    if not reals and not conns:
        return   # normative filter: unrealized -> not mapped
    ends = [s for s in (flow._vals.get("informationSource") or [])] \
        + [t for t in (flow._vals.get("informationTarget") or [])]
    conveyed = [i for i in (flow._vals.get("conveyed") or [])]
    carriers = reals or conns   # one FlowDefinition per realizing element
    for carrier in carriers:
        fd = S2.FlowDefinition(declaredName=_name(flow))
        for end_el in ends:
            etype = index.get(id(end_el)) if end_el is not None else None
            if etype is None:
                raise UnmappedFeature(
                    f"InformationFlow end {_name(end_el)!r} external/"
                    f"unordered")
            feat = S2.Feature()
            feat.isEnd = True
            _type_feature(feat, etype)
            em = S2.EndFeatureMembership()
            em.ownedRelatedElement.append(feat)
            fd.ownedRelationship.append(em)
        for item in conveyed:
            itype = index.get(id(item)) if item is not None else None
            if itype is None:
                raise UnmappedFeature(
                    f"InformationFlow conveyed {type(item).__name__} "
                    f"{_name(item)!r} external/unordered")
            iu = S2.ItemUsage(declaredName=_name(item))
            _type_feature(iu, itype)
            fm = S2.FeatureMembership()
            fm.ownedRelatedElement.append(iu)
            fd.ownedRelationship.append(fm)
        if reals and isinstance(carrier, U.Association):
            general = index.get(id(carrier))
            if general is None:
                raise UnmappedFeature(
                    f"InformationFlow realization external/unordered "
                    f"{_name(carrier)!r}")
            subc = S2.Subclassification()
            subc.general = general
            fd.ownedSpecialization.append(subc)
        _own_membership(out, fd)


def _transform_allocate(al, out, index):
    """Allocate_Mapping (7.8.3.3.9/.10): Allocate → AllocationUsage
    (usage ends) inside an AllocationDefinition; source/target ends."""
    src = next(iter(list(al.client)), None)
    tgt = next(iter(list(al.supplier)), None)
    if src is None or tgt is None:
        raise UnmappedFeature("Allocate without client/supplier")
    src_obj = index.get(id(src._vals.get("type"))) \
        if isinstance(src, U.Property) else index.get(id(src))
    tgt_obj = index.get(id(tgt._vals.get("type"))) \
        if isinstance(tgt, U.Property) else index.get(id(tgt))
    if src_obj is None or tgt_obj is None:
        raise UnmappedFeature(
            "Allocate ends reference unmapped definitions")
    al_def = S2.AllocationDefinition(declaredName=_name(al))
    al_usage = S2.AllocationUsage()
    al_usage.source.append(src_obj)
    al_usage.target.append(tgt_obj)
    _own_membership(al_def, al_usage)
    _own_membership(out, al_def)
    return al_def


# --------------------------------------------------------------------------
# To*_Init realization table (normative XMI: Mappings-Initializers)
# --------------------------------------------------------------------------
# The 78 helper initializers of the transformation spec (formal
# 2.0, Part 2) and their realization in
# this module. "wiring" = the helper's object construction is realized;
# "defaults" = the helper only supplies mapping-language default values
# that the construction path sets directly (isUnique=true, isOrdered=
# false, etc. — the XMI bodies); "elided" = the normative mapping itself
# elides the construct (same anchors as v1_to_v2.py).
#
# ToPackage_Init            wiring   transform_package (S2.Package)
# ToElement_Init            defaults transform_* (elementId/aliasId/
#                                    shortName defaults live in the
#                                    runtime constructors)
# ToNamespace_Init          wiring   every Package/definition carries
#                                    member/namespace via memberships
# ToNamespaceImport_Init    wiring   wave F: PackageImport →
#                                    NamespaceImport, importedNamespace =
#                                    AS namespace of the imported package,
#                                    visibility per Helper (package →
#                                    public), OwningMembership under the
#                                    importing namespace (7.7.9.3.12)
# ToMembershipImport_Init   wiring   wave F: ElementImport →
#                                    MembershipImport, importedMembership
#                                    = the AS OwningMembership of the
#                                    imported element (ElementImport →
#                                    MembershipImport); v1 alias →
#                                    importedMemberName elided (no
#                                    carrier in the generated runtime)
# ToImport_Init             wiring   covers both import forms; targets
#                                    outside the transformed scope raise
#                                    UnmappedFeature; requires the wave-F
#                                    recursive namespace population
#                                    (nested packages now transform)
# ToComment_Init            wiring   _attach_documentation
# ToDocumentation_Init      wiring   _attach_documentation (7.4.2.1.9)
# ToAnnotatingElement_Init  wiring   _attach_documentation (Annotation)
# ToAnnotation_Init         wiring   _attach_documentation (Annotation
#                                    owned by the Documentation)
# ToRelationship_Init       wiring   every _own_membership/_type_feature/
#                                    Subsetting/Redefinition carrier
# ToMembership_Init         wiring   _feature_membership (Feature-
#                                    Membership carrier)
# ToOwningMembership_Init   wiring   _own_membership
# ToFeatureMembership_Init  wiring   _feature_membership
# ToEndFeatureMembership_Init wiring  state/transition ends (wave B;
#                                    full end-feature machinery elided)
# ToParameterMembership_Init wiring  _populate_class (operations) and
#                                    _populate_behavior_params
# ToReturnParameterMembership_Init wiring _populate_behavior_params
#                                    (return → out)
# ToActorMembership_Init    elided   v1 Actor containment has no
#                                    normative AS membership form in
#                                    the implemented subset
# ToSubjectMembership_Init  wiring   requirement subjectParameter ends
#                                    (constructed via memberships)
# ToObjectiveMembership_Init wiring  VerificationCase objective ends
# ToStateSubactionMembership_Init wiring wave B state internals
# ToFeature_Init            defaults transform_property (bare Feature +
#                                    mapping-language defaults)
# ToFeatureValue_Init       wiring   _attach_feature_extras
#                                    (defaultValue → FeatureValue +
#                                    expression, 7.7.4.2.16)
# ToFeatureTyping_Init      wiring   _type_feature
# ToFeatureReferenceExpression_Init wiring _attach_feature_extras
#                                    (InstanceValue → feature reference)
# ToFeatureChainExpression_Init defaults  FeatureChainExpression ends
#                                    derived; carried via owned
#                                    expression trees
# ToFeatureChaining_Init    wiring   chainingFeature ends (writable)
# ToExpression_Init         defaults expression carriers (literals)
# ToOperatorExpression_Init defaults literal-carried expressions
# ToInvocationExpression_Init defaults (no invocation synthesis in
#                                    the implemented subset)
# ToPredicate_Init          defaults (guards ride SuccessionAsUsage
#                                    inline in the textual form; AS
#                                    wave elides guard synthesis)
# ToTriggerInvocationExpression_Init defaults (triggers elided with
#                                    the via-port machinery)
# ToType_Init               wiring   every _type_feature/_transform_*
#                                    typing target
# ToTypeFeaturing_Init      wiring   featuringType back-wiring through
#                                    FeatureMembership (runtime)
# ToClassifier_Init         wiring   definitions in transform_v1_element
# ToDefinition_Init         wiring   *Definition constructions
# ToUsage_Init              wiring   *Usage constructions
# ToNamespace_Init          wiring   package/namespace memberships
# ToUseCaseDefinition_Init  wiring   wave E: UseCase → UseCaseDefinition
#                                    (7.7.13.3.4; per the normative
#                                    SysMLv1Tov2.xmi mapping classes)
# ToUseCaseSubjectMembership_Init wiring wave E: SubjectMembership +
#                                    'subject_<name>' ReferenceUsage
#                                    typed by the subject's definition
#                                    (one subject per the mapping class);
#                                    the EmptySubjectReferenceUsage stub
#                                    is left un-carried (factory default)
# ToUseCaseObjectiveMembership_Init elided (v1 has no objective)
# ToUseCaseActorMembership_Init wiring wave E add-on: association ends
#                                    typed by the use case -> ActorMembership
#                                    with a PartUsage (named from the end)
#                                    typed by the actor's definition
#                                    (UseCaseActor_Mapping family);
#                                    was ToActorMembership_Init-elided
# ToIncludeFeatureTyping_Init wiring  wave E: Include → IncludeUseCaseUsage
#                                    owned by the including definition
#                                    (FeatureMembership), typed by the
#                                    addition's UseCaseDefinition (7.7.13.3.x);
#                                    Extend/ExtensionPoint not mapped
#                                    (UseCase_Mapping comment)
# ToOccurenceDefinition_Init wiring  plain-Class → OccurrenceDefinition
# ToOccurrenceUsage_Init    wiring   Property typed by Class →
#                                    OccurrenceUsage (7.7.4.2.37)
# ToEventOccurerenceUsage_Init elided (no event-occurrence synthesis
#                                    in the implemented subset)
# ToPartUsage_Init          wiring   composite block-typed Property
# ToReferenceUsage_Init     wiring   parameters ('ref' ends)
# ToItemDefinition_Init     wiring   Signal/InformationItem
#                                    (7.7.10.2.22 / 7.7.7.2.7)
# ToItemUsage_Init          wiring   Property typed by Signal/
#                                    InformationItem
# ToItemFeature_Init        defaults item features ride ItemUsage
# ToItemFlow_Init            wiring   wave H: InformationFlow ->
#                                    FlowDefinition per the normative
#                                    mapping class (filter: only flows
#                                    with realizingConnector/realization;
#                                    ends -> isEnd Features typed by the
#                                    mapped end elements; conveyed ->
#                                    carried FeatureMembership member;
#                                    association realization ->
#                                    Subclassification to the realized
#                                    ConnectionDefinition); reader tables
#                                    extended for the InformationFlow ends
# ToSuccessionItemFlow_Init wiring   the .61/.60 reference-usage layer
#                                    carries on every .47 flow end; the
#                                    library item-redefinitions of the
#                                    special action pins stay name-only
# ToFlowUsage_Init          wiring   wave B (SuccessionFlowUsage for
#                                    ObjectFlow)
# ToAssociation_Init        wiring   wave G: Association/AssociationClass
#                                    -> ConnectionDefinition (7.7.12.2.x;
#                                    AssociationClass_Mapping 'to' =
#                                    ConnectionDefinition, ends must be
#                                    Usages) - memberEnds -> end
#                                    ReferenceUsages (isEnd) via
#                                    EndFeatureMembership, typed by the
#                                    end types; end qualifiers/subsettings/
#                                    defaults later wave (AssociationBlock
#                                    has no generated stereotype class in
#                                    gen/sysml.py)
# ToPortDefinition_Init     wiring   InterfaceBlock → PortDefinition
#                                    (7.8.7.3.16 — wave E replaced the
#                                    wave-A PartDefinition carrier; the
#                                    port/typed-property ends referenced
#                                    it by identity and were upgraded
#                                    in place)
# ToPropertyTypedByClassInterface_Init wiring wave E: Property typed by
#                                    InterfaceBlock → OccurrenceUsage
#                                    (7.7.4.2.37; ref form isComposite=false)
# ToPortConjugation_Init    wiring   conjugation machinery (Part 29/30;
#                                    the conjugated member and its
#                                    PortConjugation carry on the port); needs ToConjugation +
#                                    ToConjugatedPortDefinition +
#                                    ToConjugatedPortTyping)
# ToConjugation_Init        wiring   wave J: PortConjugation inside the
#                                    ConjugatedPortDefinition (original-
#                                    PortDefinition end; 7.8.7.3.20);
#                                    conjugated-port TYPING still elided
#                                    (ToConjugatedPortTyping has no
#                                    triggering rule in the formal)
# ToConjugatedPortDefinition_Init wiring  wave J: InterfaceBlock ->
#                                    PortDefinition + owned conjugated
#                                    definition (7.8.7.3.3); Interface ->+
#                                    '~'-named member (7.7.10.2.15)
# ToConjugatedPortTyping_Init elided (a stub target - no mapping rule
#                                    triggers it; the port types plainly)
# ToConnectionUsage_Init    wiring   DeriveReqt (wave C) and Connector
# ToConnector_Init          wiring   Connector → ConnectionUsage
#                                    (7.7.12.2.14)
# ToAssociation_Init        elided   Association → ConnectionDefinition
#                                    (7.7.12.2.x) — textual-only in
#                                    this tree (later AS wave)
# ToBindingConnectorAsUsage_Init wiring Connector wiring (7.8.4.3.2)
# ToBehavior_Init           wiring   Activity/OpaqueBehavior →
#                                    ActionDefinition (wave B)
# ToFunction_Init           absent   no Function synthesis exists in
#                                    formal 2.0 Part 2 (7.7.14 audited)
# ToStep_Init               wiring   action usages (wave B)
# ToActionUsage_Init        wiring   OpaqueAction → ActionUsage
# ToAssignmentActionUsage_Init absent   no assignment mappings exist
#                                    in formal 2.0 Part 2 (audited)
# ToCalculationUsage_Init   wiring   OpaqueExpression guards/defaults:
#                                    the guard's CalculationUsage rides
#                                    the guarded edge's transition
#                                    (7.7.14.3.18; AS Part 33)
# ToPerformActionUsage_Init wiring   Operation → PerformActionUsage
# ToStateUsage_Init         wiring   wave B (Pseudostate 7.7.11.2.10,
#                                    State 7.7.11.2.12, FinalState
#                                    7.7.11.2.7) + initial -> ActionUsage
#                                    entry subaction (7.7.11.2.8/.9)
# ToTransitionUsage_Init    wiring   wave B (7.7.11.2.18)
# ToStateSubactionMembership_Init wiring wave B state internals
# ToRequirementUsage_Init   wiring   wave C (7.8.8.3.17)
# ToMetadataUsage_Init      wiring   MetadataUsage constructions for
#                                    the v1-library metadata stubs
#                                    (PortData/RefineData/TraceData)
# ToTextualRepresentation_Init defaults (textual forms are the
#                                    other pipeline's output; AS wave
#                                    carries no TextualRepresentation)
# ToInteraction_Init        wiring   wave I: Interaction->Interaction
#                                    (7.7.8.3.6) + lifelines/messages/
#                                    fragments per the family (.3.1-.19);
#                                    AS-only (the textual emitter keeps
#                                    the grammar-gap elision)
# ToInteraction_Init        elided   (textual emitter: sysmlpy textual
#                                    grammar has no interaction element)
# ToSpecialization_Init     wiring   Subclassification machinery
#                                    (generalization → Subclassification)
# ToSubclassification_Init  wiring   (same, 7.7.4.2.12)
# ToSubsetting_Init         wiring   _attach_feature_extras
# ToRedefinition_Init       wiring   _attach_feature_extras
# ToReferenceSubsetting_Init wiring  reference ends (parameters)

# --------------------------------------------------------------------------
# R3 conformance: read a v1 XMI (R1 artifact) -> AS transform (R3) -> v2 AS
# --------------------------------------------------------------------------

def transform_xmi(path):
    """R1→R2→R3 pipeline entry: read a SysML v1 XMI 2.1 file into
    umlmeta.uml25 objects (R1), transform every root Package (R3), and
    return the list of umlmeta.sysml2 Packages (R2 artifacts)."""
    from . import xmi21
    model = xmi21.read_xmi21(path)
    out = []
    for root in model.roots:
        if isinstance(root, U.Package):
            out.append(transform_package(root))
    return out
