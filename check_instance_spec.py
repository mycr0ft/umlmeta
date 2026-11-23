#!/usr/bin/env python
"""Instance specifications and links: the reader, the two emitters, one story.

Fixtures are the .xmi files beside this script. Two of them are the documents
from the bug report, verbatim; the other three are the smallest document that
isolates one defect each.

  A. instance_specification.xmi
     InstanceSpecification.classifier is a multi-valued feature; reading it
     as a single reference stores a bare object where every consumer iterates
     (7.7.4.2.14 typing).  -> classifier is a one-element sequence, and the
     instance emits as 'part <name> : <classifier>;' on both paths.

  B. abstract_external_behavior.xmi
     A reference typed by an abstract metaclass (Behavior) cannot be
     instantiated; raising fails the whole file over a legal model
     (7.7.4.2.15).  -> the read succeeds, the reference is recorded in
     hrefs/external_types, no surrogate object is invented, and the
     transform refuses only what it cannot map (CallBehaviorAction), by name.

  C. unlimited_natural_multiplicity.xmi
     A LiteralUnlimitedNatural's value arrives as the text '*'.  ->
     'items[1..*]' on both paths, including for a feature with no type.

  D. slot_values.xmi
     A Slot value is a literal carried as a value= attribute (7.7.4.2.14).
     -> 'redefines speed = 42;' / 'redefines tag = "demo";' inside the
     instance body on both paths, one redefining feature per slot, each
     owning exactly one Redefinition and one FeatureValue.

  E. link_instance.xmi
     An InstanceSpecification classified by an Association is a link
     (7.7.4.2.13).  -> 'connection link1 : Link connect nodeA to nodeB;' on
     both paths, with the ends bound by ReferenceSubsetting.

Standard library only. Run: .venv/bin/python check_instance_spec.py
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))
from umlmeta import v1_to_v2, v1_to_v2_as, v2_text, xmi21  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def fixture(name):
    return str(HERE / name)


def emit_both(name):
    """(model, textual v2 text, AS-derived v2 text) for one fixture."""
    path = fixture(name)
    model = xmi21.read_xmi21(path)
    textual = v1_to_v2.emit_v2(model.roots[0])
    as_text = v2_text.emit_package(v1_to_v2_as.transform_xmi(path)[0])
    return model, textual, as_text


def children(el, tn):
    return [ch for _r, ch in v2_text._member_pairs(el)
            if type(ch).__name__ == tn]


print("== A. InstanceSpecification.classifier is a sequence, not a bare object ==")
model, textual, as_text = emit_both("instance_specification.xmi")
ins = [e for e in model.roots[0].packagedElement
       if type(e).__name__ == "InstanceSpecification"][0]
cls = ins._vals.get("classifier")
check("classifier reads as a sequence", isinstance(cls, list), type(cls).__name__)
check("classifier carries the one classifier", len(cls) == 1 and cls[0] is not None)
check("the instance is typed by its classifier",
      "part vehicle1 : VehicleType;" in textual)
check("the AS path agrees", "part vehicle1 : VehicleType;" in as_text)

print("\n== B. an abstract-typed external reference does not fail the file ==")
path = fixture("abstract_external_behavior.xmi")
model = xmi21.read_xmi21(path)
check("the read succeeds", len(model.roots) == 1)
check("the reference is recorded as an href",
      any(h[2].endswith("#behavior-1") for h in model.hrefs), str(model.hrefs))
check("its declared metaclass is recorded, not instantiated",
      model.external_types.get("behavior-1") == "Behavior",
      str(model.external_types))
check("no surrogate object was invented for it",
      not any(type(o).__name__ == "Behavior" for o in model.objects))
for label, fn in (("textual", lambda: v1_to_v2.emit_v2(model.roots[0])),
                  ("AS", lambda: v2_text.emit_package(
                      v1_to_v2_as.transform_xmi(path)[0]))):
    try:
        fn()
        check(f"the {label} path still refuses the unmapped action", False,
              "emitted without a mapping")
    except Exception as e:                      # noqa: BLE001 - the refusal is the contract
        check(f"the {label} path refuses, naming the action",
              type(e).__name__ == "UnmappedFeature"
              and "CallBehaviorAction" in str(e), f"{type(e).__name__}: {e}")

print("\n== C. an unlimited upper bound survives both paths ==")
model, textual, as_text = emit_both("unlimited_natural_multiplicity.xmi")
prop = model.roots[0].packagedElement[0].ownedAttribute[0]
bound = prop._vals["upperValue"]._vals.get("value")
check("the literal's '*' text is read as the bound",
      str(bound) == "*", f"{type(bound).__name__} {bound}")
check("the textual path keeps [1..*]", "items[1..*];" in textual)
check("the AS path keeps [1..*]", "items[1..*];" in as_text)

print("\n== D. slot values reach the instance body ==")
model, textual, as_text = emit_both("slot_values.xmi")
check("the literal integer is rendered", "redefines speed = 42;" in textual)
check("the literal string is rendered", 'redefines tag = "demo";' in textual)
check("the AS path renders the same two lines",
      "redefines speed = 42;" in as_text
      and 'redefines tag = "demo";' in as_text)
as_root = v1_to_v2_as.transform_xmi(fixture("slot_values.xmi"))[0]
part = children(as_root, "PartUsage")[0]
slots = children(part, "AttributeUsage")
check("one redefining feature per slot", len(slots) == 2, str(len(slots)))
check("each owns exactly one Redefinition and one FeatureValue",
      all(sum(type(r).__name__ == "Redefinition" for r in s.ownedRelationship) == 1
          and sum(type(r).__name__ == "FeatureValue" for r in s.ownedRelationship) == 1
          for s in slots))

print("\n== E. an association-typed instance is a link ==")
model, textual, as_text = emit_both("link_instance.xmi")
check("the textual path emits a connection with both ends",
      "connection link1 : Link connect nodeA to nodeB;" in textual)
check("the AS path emits the same connection",
      "connection link1 : Link connect nodeA to nodeB;" in as_text)
as_root = v1_to_v2_as.transform_xmi(fixture("link_instance.xmi"))[0]
conn = children(as_root, "ConnectionUsage")[0]
ends = children(conn, "ReferenceUsage")
check("the connection owns two ends", len(ends) == 2, str(len(ends)))
check("each end carries a ReferenceSubsetting to the instance it attaches to",
      all(any(type(r).__name__ == "ReferenceSubsetting"
              for r in e.ownedRelationship) for e in ends))

print(f"\nRESULT: {len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
