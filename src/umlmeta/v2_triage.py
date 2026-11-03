"""v2_triage.py — attribute the validation gate's findings, and check the
model's own derived structure against what it emits.

Two jobs, both about turning numbers into knowledge:

- `ledger(report)` turns a `v2_validate` report into rows carrying a
  *disposition*: a violation family is either attributed to a known cause or
  explicitly unattributed. An unattributed family is the work queue; an
  attributed one is a record of why it is expected.
- `structure_consistency(roots)` compares the derived unions the runtime
  computes (`derived.union`) against the containment the model actually
  carries (`ownedRelationship` -> `Membership.ownedRelatedElement`). It needs
  no library and no OCL: it is the invariant the AS is supposed to hold, and
  a mismatch means either the model or the derivation is wrong.

Standard library only.
"""
from __future__ import annotations

from collections import Counter

from . import derived as D
from . import extent as extent_mod

# Known causes, by family name. Anything not here is unattributed work.
DISPOSITIONS = {
    # -- library fidelity: the rules read KerML library structure behind our
    # name-only stubs (a tool running against the real library models
    # satisfies them); the remedy is a library materialization, not a
    # transform or engine defect
    "Feature.checkFeatureParameterRedefinition":
        ("engine", "the positional check evaluates against the REAL materialized "
                   "library now (Cases::Case, UseCases::UseCase); the remaining "
                   "rows are the chained-ancestor readings still settling"),
    "Type.checkTypeSpecialization":
        ("transform", "the transform emits no library specialization edges (O6)"),
    "Feature.checkFeatureSpecialization":
        ("transform", "same: no library specialization edge on features"),
    "Class.checkClassSpecialization":
        ("transform", "same: no library specialization edge on classes"),
    # -- worked 2026-11: the 17 families that were unattributed, each traced
    # to its carrier. Two causes, both upstream of the engine.
    "EndFeatureMembership.validateEndFeatureMembershipIsEnd":
        ("runtime", "isEnd is derived from owningMembership, and the inverse "
                    "is not maintained when a membership owns a feature"),
    "ParameterMembership.validateParameterMembershipOwningType":
        ("runtime", "owningType is the inverse of owningMembership; not set"),
    "StateSubactionMembership.validateStateSubactionMembershipOwningType":
        ("runtime", "same inverse-maintenance gap"),
    "MultiplicityRange.validateMultiplicityRangeBounds":
        ("runtime", "bound memberships carry no value; derived bound is null"),
    "Connector.validateConnectorRelatedFeatures":
        ("transform", "ConnectionUsage carries no relatedFeature ends"),
    "PartUsage.validatePartUsagePartDefinition":
        ("transform", "ConnectionUsage is never typed by a PartDefinition"),
    "ConnectorAsUsage.validateUsageIsReferential":
        ("transform", "same missing featuring type as the other IsReference rules"),
    "TransitionUsage.validateTransitionUsageSuccession":
        ("transform", "the succession edge the rule needs is not emitted"),
    "Expression.validateExpressionResultParameterMembership":
        ("transform", "LiteralInteger built without its ReturnParameterMembership"),
    "Function.validateFunctionResultParameterMembership":
        ("corpus", "the joined body counts inheritedMembership results too: "
                   "the real type chain (Cases::Case, Performances::"
                   "Evaluation) carries `return ref result` members, so "
                   "`featureMembership->selectByKind(RPM)->size() = 1` "
                   "fails every case whose own result exists; as written "
                   "the check cannot hold for any model"),
    "CaseDefinition.validateCaseDefinitionSubjectParameterPosition":
        ("transform", "subject parameter emitted without its position"),
    "CaseUsage.validateCaseUsageSubjectParameterPosition":
        ("transform", "same"),
    "EnumerationDefinition.validateEnumerationDefinitionIsVariation":
        ("transform", "variation flag not emitted on an enumeration definition"),
    "ConnectionDefinition.checkConnectionDefinitionSpecializations":
        ("transform", "no library specialization edge (the O6 family)"),
    "ConnectionDefinition.validateConnectionDefinitionIsSufficient":
        ("transform", "connection ends not sufficient: related features missing"),
    "Association.validateAssociationRelatedTypes":
        ("model", "the vehicle model types frontAxle AND rearAxle both as "
                  "Axle, so relatedType is a 1-element set; relatedType "
                  "size >= 2 fails under set semantics"),
    "Import.validateImportTopLevelVisibility":
        ("transform", "import emitted without its visibility"),
    # worked after the O4/O5b/O7 batch raised coverage to 76%: the 8
    # previously-unattributed rows, traced. All are "the transform did not
    # emit the featuring/subsetting edge the rule tests" except two, which
    # are the same inverse-maintenance gap already attributed on the
    # ParameterMembership side.
    "Subsetting.validateSubsettingFeaturingTypes":
        ("transform", "subsettingFeature.canAccess(subsettedFeature) needs the "
                      "featuring-type edges; the transform emits subsetting "
                      "but not featuring"),
    "ReferenceSubsetting.validateSubsettingFeaturingTypes":
        ("transform", "same rule on the reference subsetting"),
    "ParameterMembership.validateParameterMembershipParameterDirection":
        ("runtime", "parameterDirection default is derivable but the "
                    "membership's ownedMemberParameter inverse is not set"),
    "Connector.checkConnectorTypeFeaturing":
        ("transform", "connector featuringType not emitted; rule falls back "
                      "to isFeaturedWithin(null) which needs featuring edges"),
    "TransitionUsage.checkTransitionUsageSuccessionBindingConnector":
        ("transform", "the succession binding connector the rule requires is "
                      "not emitted"),
    "TransitionUsage.checkTransitionUsageSourceBindingConnector":
        ("transform", "same, for the source binding connector"),
    "Multiplicity.checkMultiplicityTypeFeaturing":
        ("transform", "multiplicity's featuringType derives from its owning "
                      "feature's featuringType; the owning chain is incomplete"),
    "Association.validateAssociationEndTypes":
        ("transform", "an end feature carries no type; the transform emits "
                      "end usages untyped"),
    "Usage.validateUsageIsReferential":
        ("runtime", "isReference is derived in the KerML AS "
                    "(deriveUsageIsReference); the runtime stores it as None "
                    "and nothing computes it on read"),
}


def _classify(family):
    """Attribute by family shape where the cause is the same across classes.

    Every `check<Class>Specialization` rule asks for a library specialization
    edge, and the transform emits none: one cause, many family names.
    """
    if family.endswith("IsReference"):
        return ("transform", "isReference computes (not isComposite) but the "
                             "transform emits no featuring type, which the "
                             "same rule requires of a composite usage")
    if family.endswith("Specialization") and ".check" in family:
        return ("transform",
                "the transform emits no library specialization edges (O6)")
    return ("unattributed", "")


def ledger(report):
    """Per-family rows: violations (with disposition) and skips (with reason)."""
    vio = Counter(f"{e['class']}.{e['constraint']}"
                  for e in report["violations"])
    rows = []
    for family, count in vio.most_common():
        owner, why = DISPOSITIONS.get(family, _classify(family))
        rows.append({"kind": "violation", "family": family, "count": count,
                     "owner": owner, "note": why})
    skip = Counter(s["reason"].split(":", 1)[0][:50]
                   for s in report["skipped"])
    for family, count in skip.most_common():
        rows.append({"kind": "skip", "family": family, "count": count,
                     "owner": "engine" if family.startswith("operation")
                     else "runtime", "note": ""})
    return rows


def to_markdown(report, summary=""):
    rows = ledger(report)
    out = ["# v2 validation triage", "",
           summary or "", "",
           "| kind | family | count | owner | note |",
           "|---|---|---:|---|---|"]
    for r in rows:
        out.append(f"| {r['kind']} | `{r['family']}` | {r['count']} | "
                   f"{r['owner']} | {r['note']} |")
    return "\n".join(out) + "\n"


def structure_consistency(*roots):
    """Derived containment vs the memberships the model carries."""
    ext = extent_mod.Extent(*roots, prefer="sysml2")
    checked, mismatches, skipped_na = 0, [], []
    for el in ext.elements():
        derived_members = list(D.union(el, "ownedElement"))
        carried = []
        for rel in getattr(el, "ownedRelationship", None) or ():
            for sub in getattr(rel, "ownedRelatedElement", None) or ():
                carried.append(sub)
        if not carried:
            continue
        # `derived.union` is the UML 2.5.1 implementation: it only knows
        # classes that declare `ownedElement` as a union (in the KerML AS the
        # relation is derived from ownedRelationship by rule, not by a stored
        # union table). Comparing where the table is absent would report the
        # absent table, not a model defect.
        if "ownedElement" not in getattr(type(el), "_UNIONS", {}):
            skipped_na.append(el)
            continue
        checked += 1
        missing = [c for c in carried if c not in derived_members]
        if missing:
            mismatches.append((el, missing))
    return {"checked": checked, "mismatches": mismatches,
            "not_applicable": skipped_na, "ok": not mismatches}
