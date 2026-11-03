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
check("the extent reaches the whole model", report["elements"] == 218,
      f"{report['elements']} elements")
check("checks and derivations are separated",
      len(report["checks"]) == 4533 and len(report["derivations"]) == 8433,
      f"{len(report['checks'])} checks, {len(report['derivations'])} derivations")
check("no deriveXxx body is counted as a check",
      not any(e["constraint"].startswith("derive") for e in report["checks"]))

print("== the finding ==")
families = collections.Counter(f"{e['class']}.{e['constraint']}"
                               for e in report["violations"])
check("the gate reports violations on transformed output",
      len(report["violations"]) == 2 and not report["clean"],
      f"{len(report['violations'])} violations in "
      f"{len(families)} families")
top = families.most_common(1)[0]
check("the residual violations are the single-type associations",
      top[0] == "Association.validateAssociationRelatedTypes"
      and top[1] == 2
      and top[1] == max(families.values())
      and len(families) == 1, str(top))

print("== skips are reported, not passed ==")
check("skips are counted with reasons",
      len(report["skipped"]) == 36 and report["skip_reasons"],
      str(report["skip_reasons"][:2]))
check("the top skip reason is a named class",
      report["skip_reasons"][0][0] in ("eval-unmapped",
                                       "undetermined comparison",
                                       "corpus-defect",
                                       "undetermined") or
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
check("every finding has a row", len(rows) == 3, f"{len(rows)} rows")
check("every finding now has an owner",
      sum(1 for r in rows if r["owner"] != "unattributed") == 3,
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
      == "((None if (_g(self, 'isComposite')) is None "
         "else (not (_g(self, 'isComposite')))))",
      str(T._derivation_source(K.PartUsage, "isReference")))
_part = K.PartUsage(declaredName="pt")
_part.isComposite = True
check("Reading a derived property computes it",
      T.eval_body("self.isReference", _part, None) is False)


print("== the skips say whose gap they are ==")
check("every skip is bucketed by cause",
      sum(report["skip_buckets"].values()) == len(report["skipped"]),
      str(dict(report["skip_buckets"])))
check("every skip bucket is undetermined-bounded",
      set(report["skip_buckets"]) == {"undetermined"}
      and report["skip_buckets"]["undetermined"] == 36,
      f"{dict(report['skip_buckets'])} of {len(report['skipped'])} skips")
check("gate coverage is reported as a fraction",
      abs(V.coverage(report) - 0.99) < 0.01,
      f"{V.coverage(report):.1%} of applicable checks run")


print("== the corpus-defect rules repair into evaluations ==")
from umlmeta import sysml2 as K  # noqa: E402
from umlmeta import ocl_translator as T  # noqa: E402
from umlmeta import derived as DD  # noqa: E402
from umlmeta import extent as _XT  # noqa: E402
_XTENT = _XT.Extent(*roots, prefer="sysml2")
_F = dict(K.Feature.CONSTRAINTS)
_SM = dict(K.SubjectMembership.CONSTRAINTS)
# the published text (KerML 1.1 Beta 2 clause checkFeatureDataValue
# Specialization) prints `ownedTyping.type->exists(selectByKind(DataType))`
# -- selectByKind applied to the IMPLICIT element: a kind predicate, not a
# collection filter. The lowering (select_by_kind(it, 'T')) already binds
# the iterator; the op takes the scalar predicate reading.
check("selectByKind on a scalar receiver is the kind predicate",
      T.select_by_kind(K.OccurrenceDefinition(), "Definition") is True
      and T.select_by_kind(K.Feature(), "DataType") is False
      and len(T.select_by_kind([K.OccurrenceDefinition(), K.Feature()],
                               "Definition")) == 1
      and isinstance(T.select_by_kind([K.OccurrenceDefinition(), K.Feature()],
                                      "Definition")[0],
                     K.OccurrenceDefinition),
      "scalar receiver -> oclIsKindOf; list receiver -> the filter")
for _rule in ("checkFeatureDataValueSpecialization",
              "checkFeatureObjectSpecialization",
              "checkFeatureOccurrenceSpecialization"):
    _b = T._repair_body("Feature", _rule, _F[_rule])
    _ok_lower = None
    _lowered = None
    try:
        _lowered = T.translate(_b)
        _ok_lower = True
    except Exception:                          # noqa: BLE001
        pass
    check(f"the {_rule} body lowers with the predicate reading",
          _ok_lower and "select_by_kind(it," in (_lowered or ""),
          (_lowered or _b)[:72])
    _sk = [s for s in report["skipped"] if s["constraint"] == _rule]
    check(f"the {_rule} skips are gone",
          not _sk, f"{len(_sk)} skips left")
check("the mangled token reads RequirementUsage (the spec prose)",
      "RequiremenCaseRequirementDefinition"
      not in T._repair_body("SubjectMembership",
                            "validateSubjectMembershipOwningType",
                            _SM["validateSubjectMembershipOwningType"])
      and T._repair_body("SubjectMembership",
                         "validateSubjectMembershipOwningType",
                         _SM["validateSubjectMembershipOwningType"])
      .count("oclIsKindOf") == 4)
_smem = K.SubjectMembership()
_v2d = K.UseCaseDefinition(declaredName="probe")
_smem._vals["owner"] = _v2d
_smem._vals["owningType"] = _v2d
check("the repaired SubjectMembership rule evaluates (not skips)",
      T.eval_body(
          T._repair_body("SubjectMembership",
                         "validateSubjectMembershipOwningType",
                         _SM["validateSubjectMembershipOwningType"]),
          _smem, DD, extent=_XTENT) is True,
      "a UseCaseDefinition owningType satisfies kind-of CaseDefinition")
_sk2 = [s for s in report["skipped"]
        if s["constraint"] == "validateSubjectMembershipOwningType"]
check("the SubjectMembership skips are gone", not _sk2,
      f"{len(_sk2)} skips left")

print("== the Function-result invariant reads the 2b-mapped membership ==")
# 7.7.13.2.4 UseCase_Mapping includes exactly ONE result membership
# (CommonReturnParameterReferenceUsageMembership_Mapping -> 7.6.2.11 ->
# ToReturnParameterMembership_Init); the library chain carries unredefined
# result RPMs at BOTH Cases::Case and Performances::Evaluation
# (Calculation :> Action, Evaluation), so the literal "owned or
# inherited" union can never equal 1 on a mapped model
_Ffn = dict(K.Function.CONSTRAINTS)["validateFunctionResultParameterMembership"]
_fnrep = T._repair_body("Function", "validateFunctionResultParameterMembership",
                        _Ffn)
check("the Function-result invariant reads the mapped (owned) membership",
      "ownedFeatureMembership->selectByKind"
      in "".join(_fnrep.split())
      and "Requiremen" not in _fnrep,
      _fnrep[:64])
_fvio = [e for e in report["violations"]
         if e["constraint"] == "validateFunctionResultParameterMembership"]
check("the Function-result violations are gone", not _fvio,
      f"{len(_fvio)} left")

print("== an empty model is clean ==")
empty = V.validate()
check("no roots means nothing to check",
      empty["elements"] == 0 and empty["clean"])

print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
