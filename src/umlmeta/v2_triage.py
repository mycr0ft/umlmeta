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
    "Type.checkTypeSpecialization":
        ("transform", "the transform emits no library specialization edges (O6)"),
    "Feature.checkFeatureSpecialization":
        ("transform", "same: no library specialization edge on features"),
    "Class.checkClassSpecialization":
        ("transform", "same: no library specialization edge on classes"),
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
        return ("runtime", "isReference is derived in the KerML AS "
                          "(deriveUsageIsReference); the runtime stores None")
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
