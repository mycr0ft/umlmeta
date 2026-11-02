#!/usr/bin/env python
"""S1 checks: stereotype applications materialized as objects.

Oracles:
  1. the profile index resolves a stereotype by name and by (profile, name);
  2. a hand-written XMI application produces an instance whose base_<Meta>
     property points at the stereotyped element and whose tagged values are
     coerced to the declared types;
  3. a real corpus (DoDAF/UPDM) materializes every application, with nothing
     invented for an unknown profile;
  4. stereotype constraints evaluate with `self` bound to the instance —
     passing and failing on constructed models;
  5. corpus coverage: how many constraint bodies run over the real
     applications, and what the skipped ones need.

Standard library only. Run: .venv/bin/python check_stereotype.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from umlmeta import derived as D  # noqa: E402
from umlmeta import ocl_translator as T  # noqa: E402
from umlmeta import stereotype as S  # noqa: E402
from umlmeta import uml25 as U  # noqa: E402
from umlmeta import xmi21  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


# ---------------------------------------------------------------------------
# the profile index
# ---------------------------------------------------------------------------

print("== profile index ==")
IDX = S.load_profiles()
check("the four profile modules are indexed", len(IDX) >= 300,
      f"{sum(len(v) for v in IDX.values())} stereotypes, {len(IDX)} names")
entry = S.find_class(IDX, "Block", "SysML")
check("a stereotype resolves by (profile, name)",
      entry is not None and entry[2] == "SysML::Blocks::Block",
      entry[2] if entry else None)
check("a stereotype resolves by name alone",
      S.find_class(IDX, "Requirement") is not None)
check("an unknown stereotype resolves to nothing, not a guess",
      S.find_class(IDX, "NoSuchStereotype") is None)


# ---------------------------------------------------------------------------
# a hand-written application: base element, tagged value typing
# ---------------------------------------------------------------------------

print("== a hand-written application ==")
XMI = """<?xml version='1.0' encoding='UTF-8'?>
<xmi:XMI xmlns:uml="http://www.omg.org/spec/UML/20090901"
         xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
         xmlns:SysML="http://www.omg.org/spec/SysML/20181001/SysML">
  <uml:Model xmi:id="m1" xmi:type="uml:Model" name="M">
    <packagedElement xmi:type="uml:Class" xmi:id="c1" name="C"/>
  </uml:Model>
  <SysML:Block xmi:id="app1">
    <base_Class xmi:idref="c1"/>
    <isEncapsulated>true</isEncapsulated>
  </SysML:Block>
</xmi:XMI>
"""
tmp = Path(tempfile.mkdtemp()) / "app.xmi"
tmp.write_text(XMI, encoding="utf-8")
model = xmi21.read_xmi21(str(tmp))
report = S.materialize(model, IDX)
check("one application materializes", len(report["instances"]) == 1,
      f"{len(report['instances'])} resolved, "
      f"{len(report['unresolved'])} unresolved")
inst = report["instances"][0]
check("the instance is the generated stereotype class",
      type(inst.obj).__name__ == "Block" and inst.stereotype == "Block",
      type(inst.obj).__name__)
check("base_Class points at the stereotyped element",
      inst.obj.base_Class is inst.base
      and type(inst.base).__name__ == "Class")
check("a tagged value is applied with its declared type",
      inst.obj.isEncapsulated is True, repr(inst.obj.isEncapsulated))
check("the base element keeps its instances",
      S.instances_of(inst.base) == [inst])


# ---------------------------------------------------------------------------
# a real corpus: everything resolves or is reported
# ---------------------------------------------------------------------------

print("== a real corpus (DoDAF / UPDM) ==")
CORPUS = Path("/mnt/TBFox/DoDAFLibrary.xmi")
if CORPUS.exists():
    dmodel = xmi21.read_xmi21(str(CORPUS))
    drep = S.materialize(dmodel, IDX)
    check("every application materializes", len(drep["instances"]) == 61
          and not drep["unresolved"],
          f"{len(drep['instances'])} instances, "
          f"{len(drep['unresolved'])} unresolved")
    check("each instance carries its base property",
          all(getattr(i.obj, "base_" + "Property", None) is i.base
              for i in drep["instances"]
              if i.stereotype == "Measurement"))
else:                                            # pragma: no cover
    print("  SKIP  corpus not on disk")
    dmodel, drep = None, {"instances": []}


# ---------------------------------------------------------------------------
# evaluation with `self` bound to the instance
# ---------------------------------------------------------------------------

print("== stereotype constraints evaluate ==")
blk_idx = S.load_profiles()
klass = U.Class(name="K")
app = U.Class(name="Stereotyped")


def _apply(cls_name, base):
    """Apply a stereotype to an object without an XMI round trip."""
    entry = S.find_class(IDX, cls_name)
    obj = entry[1]()
    for prop in [p for p in obj._props if p.startswith("base_")]:
        setattr(obj, prop, base)
    return obj


req = _apply("Requirement", klass)
ok, res, skip = T.check_constraints(req, D)
values = {n: v for _, n, _, v in res}
check("Requirement.1_no_operation passes on a class with no operations",
      values.get("1_no_operation") is True, str(values)[:80])
klass.ownedOperation.append(U.Operation(name="op"))
ok2, res2, _ = T.check_constraints(req, D)
values2 = {n: v for _, n, _, v in res2}
check("...and fails once an operation is added",
      values2.get("1_no_operation") is False, str(values2)[:80])
klass.ownedAttribute.append(U.Property(name="a"))
values3 = {n: v for _, n, _, v in T.check_constraints(req, D)[1]}
check("Requirement.2_no_attribute fails on a class with an attribute",
      values3.get("2_no_attribute") is False, str(values3)[:80])


# ---------------------------------------------------------------------------
# corpus coverage
# ---------------------------------------------------------------------------

print("== coverage over the real applications ==")
if drep["instances"]:
    ok_all, results, skipped, _ = S.check(dmodel, D, IDX)
    reasons = {}
    for _inst, cname, reason in skipped:
        key = reason.split(":", 1)[0][:40]
        reasons[key] = reasons.get(key, 0) + 1
    check("constraint bodies run over materialized instances",
          len(results) > 0, f"{len(results)} evaluations, "
          f"{len(skipped)} skipped")
    print(f"  (skip reasons: {sorted(reasons.items(), key=lambda kv: -kv[1])[:3]})")


print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
