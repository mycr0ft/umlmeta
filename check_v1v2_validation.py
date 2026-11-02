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
check("the extent reaches the whole model", report["elements"] == 131,
      f"{report['elements']} elements")
check("checks and derivations are separated",
      len(report["checks"]) == 1898 and len(report["derivations"]) == 4030,
      f"{len(report['checks'])} checks, {len(report['derivations'])} derivations")
check("no deriveXxx body is counted as a check",
      not any(e["constraint"].startswith("derive") for e in report["checks"]))

print("== the finding ==")
families = collections.Counter(f"{e['class']}.{e['constraint']}"
                               for e in report["violations"])
check("the gate reports violations on transformed output",
      len(report["violations"]) == 284 and not report["clean"],
      f"{len(report['violations'])} violations in "
      f"{len(families)} families")
top = families.most_common(1)[0]
check("the dominant family is the missing library specialization edges",
      top[0] == "Type.checkTypeSpecialization" and top[1] == 55, str(top))

print("== skips are reported, not passed ==")
check("skips are counted with reasons",
      len(report["skipped"]) == 1872 and report["skip_reasons"],
      str(report["skip_reasons"][:2]))
check("the top skip reason is a known engine gap",
      report["skip_reasons"][0][0] in ("eval-unmapped",) or
      report["skip_reasons"][0][0].startswith("operation "),
      str(report["skip_reasons"][0]))

print("== an empty model is clean ==")
empty = V.validate()
check("no roots means nothing to check",
      empty["elements"] == 0 and empty["clean"])

print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
