"""v2_validate.py — the semantic gate for a SysML v2 abstract-syntax model.

The transformer had shape oracles and no semantic one. This runs the
KerML/SysML constraint bodies carried in `umlmeta.sysml2` over a model the
transformer produced (or any v2 model held as `sysml2` objects), with an
extent bound so `allInstances`, `selectByKind` and `specializesFromLibrary`
answer.

What it reports, and what it refuses to do:

- `evaluations` — bodies that ran, with their value;
- `violations` — bodies that returned False, each with the element path and
  the constraint name (this is the gate: a violation is a finding, not a
  warning);
- `skipped` — bodies that could not run, keyed by reason. Skipped is not
  passed: a body that cannot run is a gap in the engine or the runtime and is
  counted as such, never as a clean result.

Standard library only.
"""
from __future__ import annotations

from collections import Counter

from . import derived as D
from . import extent as extent_mod
from . import ocl_translator as T


def validate(*roots, derived=None, limit_skip=8):
    """Run the v2 constraint bodies over `roots`; returns a report dict.

    Keys: evaluations, violations, skipped, skip_reasons, elements.
    """
    derived = derived or D
    roots = [r for r in roots if r is not None]
    ext = extent_mod.Extent(*roots, prefer="sysml2")
    elements = ext.elements()

    evaluations = []
    skipped = []
    for el in elements:
        previous = T.set_extent(ext)
        try:
            _ok, results, skips = T.check_constraints(el, derived)
        finally:
            T.set_extent(previous)
        for cls_name, cname, body, value in results:
            evaluations.append({"element": el, "class": cls_name,
                                "constraint": cname, "value": value})
        for cname, body, reason in skips:
            skipped.append({"element": el, "constraint": cname,
                            "reason": reason})

    # derivation bodies (`deriveXxx = ...`) compute a property; they are not
    # checks, and their value is the derived result, not a verdict
    derivations = [e for e in evaluations if e["constraint"].startswith("derive")]
    checks = [e for e in evaluations if not e["constraint"].startswith("derive")]
    violations = [e for e in checks if not e["value"]]
    reasons = Counter(s["reason"].split(":", 1)[0][:60] for s in skipped)
    # bucket the skips by CAUSE, not by message: the numbers only mean
    # something if a skip says whose gap it is
    buckets = Counter(skip_bucket(s["reason"]) for s in skipped)
    return {
        "elements": len(elements),
        "evaluations": evaluations,
        "checks": checks,
        "derivations": derivations,
        "violations": violations,
        "skipped": skipped,
        "skip_reasons": reasons.most_common(limit_skip),
        "skip_buckets": buckets,
        "clean": not violations,
    }


BUCKETS = ("helper-operation", "runtime-feature", "undetermined",
           "engine-other")


def skip_bucket(reason):
    """Whose gap is this skip? Named, so the ledger can be worked."""
    if reason.startswith("operation ") or reason.startswith("->"):
        return "helper-operation"
    if reason.startswith("eval-unmapped"):
        return "runtime-feature"
    if reason.startswith("undetermined"):
        return "undetermined"
    return "engine-other"


def coverage(report):
    """Checks run as a fraction of the rules that could have run."""
    run = len(report["checks"])
    total = run + len(report["skipped"])
    return run / total if total else 1.0


def summary(report):
    """One-line human summary of a validate() report."""
    return (f"{report['elements']} elements, "
            f"{len(report['checks'])} checks "
            f"(+{len(report['derivations'])} derivations), "
            f"{len(report['violations'])} violations, "
            f"{len(report['skipped'])} skipped, "
            f"coverage {coverage(report):.0%}")
