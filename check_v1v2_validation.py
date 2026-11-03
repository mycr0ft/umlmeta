#!/usr/bin/env python
"""V1 checks: the semantic gate on transformed SysML v2 models.

Oracles:
  1. the vehicle example transforms and validates: elements, checks,
     derivations and skips are reported separately;
  2. derivation bodies (`deriveXxx = ...`) are not counted as checks — they
     compute a property, and their value is not a verdict;
  3. the gate produces real findings on real output: the violations are
     itemized, and the dominant family is the missing library specialization
     edges (`check*Specialization`) — the finding this leg exists to produce;
  4. skips are counted with reasons and never reported as passes;
  5. an empty model validates cleanly.

Standard library only. Run: .venv/bin/python check_v1v2_validation.py
"""
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from umlmeta import v1_to_v2_as as AS  # noqa: E402
from umlmeta import v2_validate as V  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


print("== the vehicle example, validated ==")
roots = AS.transform_xmi(str(ROOT / "vehicle_example_cameo.xmi"))
report = V.validate(*roots)
print("  " + V.summary(report))
check("the transform produces one root package", len(roots) == 1)
check("the extent reaches the whole model", report["elements"] == 143,
      f"{report['elements']} elements")
check("checks and derivations are separated",
      len(report["checks"]) == 2411 and len(report["derivations"]) == 5272,
      f"{len(report['checks'])} checks, {len(report['derivations'])} derivations")
check("no deriveXxx body is counted as a check",
      not any(e["constraint"].startswith("derive") for e in report["checks"]))

print("== the finding ==")
families = collections.Counter(f"{e['class']}.{e['constraint']}"
                               for e in report["violations"])
check("the gate reports violations on transformed output",
      len(report["violations"]) == 189 and not report["clean"],
      f"{len(report['violations'])} violations in "
      f"{len(families)} families")
top = families.most_common(1)[0]
check("the dominant remaining family is a *Specialization rule still failing",
      top[0].endswith("Specialization") and top[1] >= 30, str(top))

print("== skips are reported, not passed ==")
check("skips are counted with reasons",
      len(report["skipped"]) == 781 and report["skip_reasons"],
      str(report["skip_reasons"][:2]))
check("the top skip reason is a known engine gap",
      report["skip_reasons"][0][0] in ("eval-unmapped",) or
      report["skip_reasons"][0][0].startswith("operation "),
      str(report["skip_reasons"][0]))

print("== undetermined is a skip, never a False ==")
und = [s for s in report["skipped"]
       if s["reason"].startswith("undetermined")]
check("a feature the runtime lacks is recorded as undetermined",
      len(und) > 0, f"{len(und)} skips, e.g. "
      f"{und[0]['reason'] if und else None}")
check("no violation comes from an undetermined read",
      all("undetermined" not in str(e) for e in report["violations"]))


print("== the triage ledger ==")
from umlmeta import v2_triage as TR  # noqa: E402
rows = TR.ledger(report)
check("every finding has a row", len(rows) == 73, f"{len(rows)} rows")
check("every finding now has an owner",
      sum(1 for r in rows if r["owner"] != "unattributed") == 73,
      f"{sum(1 for r in rows if r['owner'] != 'unattributed')} attributed")
cons = TR.structure_consistency(*roots)
check("structure consistency does not report the missing AS union as a defect",
      not cons["mismatches"] and len(cons["not_applicable"]) >= 14,
      f"{cons['checked']} checked, {len(cons['not_applicable'])} n/a "
      f"(ownedElement is derived by rule in the AS)")


print("== derived properties answer instead of reading None ==")
from umlmeta import ocl_translator as T  # noqa: E402
from umlmeta import sysml2 as K  # noqa: E402
check("a derivation body resolves through the MRO",
      T._derivation_source(K.PartUsage, "isReference")
      == "(not (_g(self, 'isComposite')))",
      str(T._derivation_source(K.PartUsage, "isReference")))
_part = K.PartUsage(declaredName="pt")
_part.isComposite = True
check("Reading a derived property computes it",
      T.eval_body("self.isReference", _part, None) is False)


print("== the skips say whose gap they are ==")
check("every skip is bucketed by cause",
      sum(report["skip_buckets"].values()) == len(report["skipped"]),
      str(dict(report["skip_buckets"])))
check("the helper-operation library is the dominant skip class",
      report["skip_buckets"]["helper-operation"] == 87,
      f"{report['skip_buckets']['helper-operation']} of "
      f"{len(report['skipped'])} skips")
check("gate coverage is reported as a fraction",
      abs(V.coverage(report) - 0.76) < 0.01,
      f"{V.coverage(report):.1%} of applicable checks run")


print("== an empty model is clean ==")
empty = V.validate()
check("no roots means nothing to check",
      empty["elements"] == 0 and empty["clean"])

print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
