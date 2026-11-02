#!/usr/bin/env python
"""O5a checks: the extent — allInstances, selectByKind, specializesFromLibrary.

Oracles:
  1. an extent enumerates composite containment and filters by metaclass;
  2. allInstances answers from the extent and is empty (not wrong) without
     one;
  3. selectByKind/selectAsKind filter by metaclass, subtypes included;
  4. specializesFromLibrary answers from the model's own specialization
     graph — true through an ancestor, false otherwise, and it does not
     invent a library;
  5. the binding is scoped: a second extent cannot see the first;
  6. corpus effect: the two KerML extensions move lowering from 676 to 1001.

Standard library only. Run: .venv/bin/python check_ocl_extent.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from umlmeta import derived as D  # noqa: E402
from umlmeta import extent as X  # noqa: E402
from umlmeta import ocl_translator as T  # noqa: E402
from umlmeta import uml25 as U  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


# a model: package P { class C { property a } ; class D }
pkg = U.Package(name="P")
cls = U.Class(name="C")
dcl = U.Class(name="D")
pkg.packagedElement.append(cls)
pkg.packagedElement.append(dcl)
attr = U.Property(name="a")
cls.ownedAttribute.append(attr)
dcl.ownedOperation.append(U.Operation(name="f"))
EXT = X.Extent(pkg)

print("== the extent ==")
check("composite containment is enumerated", len(EXT.elements()) == 5,
      f"{[type(e).__name__ for e in EXT.elements()]}")
check("of_kind filters by metaclass", [type(e).__name__ for e in EXT.of_kind("Class")]
      == ["Class", "Class"], str(EXT.of_kind("Class")))
check("an unknown metaclass yields nothing", EXT.of_kind("NoSuch") == [])
check("a subtype matches its supertype's extent",
      len(X.Extent(pkg).of_kind("Classifier")) == 2,
      str(len(X.Extent(pkg).of_kind("Classifier"))))


print("== allInstances ==")
check("allInstances reads the extent",
      T.eval_body("Property.allInstances()->size()", cls, D, extent=EXT) == 1)
check("allInstances is empty without an extent (stated, not guessed)",
      T.eval_body("Property.allInstances()->size()", cls, D) == 0)
check("the emitted form passes the type as a name",
      T.translate("Property.allInstances()") == "all_instances('Property')",
      T.translate("Property.allInstances()"))


print("== selectByKind / selectAsKind ==")
body = "self.ownedElement->selectByKind(Property)->size()"
check("selectByKind filters the collection",
      T.eval_body(body, cls, D, extent=EXT) == 1)
check("selectAsKind agrees", T.eval_body(
    "self.ownedElement->selectAsKind(Property)->size()", cls, D, extent=EXT) == 1)
check("selectByKind keeps nothing of another metaclass",
      T.eval_body("self.ownedElement->selectByKind(Operation)->size()",
                  cls, D, extent=EXT) == 0)


print("== specializesFromLibrary ==")
anc = U.Class(name="Base")
sub = U.Class(name="Derived")
U.Generalization(general=anc, specific=sub)  # recorded on the objects
anc.ownedAttribute.append(U.Property(name="x"))
pkg.packagedElement.append(anc)
pkg.packagedElement.append(sub)
EXT2 = X.Extent(pkg)
check("an ancestor's qualified name satisfies it",
      T.eval_body("self.specializesFromLibrary('P::Base')", sub, D,
                  extent=EXT2) is True)
check("an unrelated name does not",
      T.eval_body("self.specializesFromLibrary('Base::Anything')", sub, D,
                  extent=EXT2) is False)
check("the element itself counts",
      T.eval_body("self.specializesFromLibrary('P::Derived')", sub, D,
                  extent=EXT2) is True)


print("== scoping ==")
T.eval_body("Property.allInstances()", cls, D, extent=EXT2)
check("the extent binding does not outlive the call", T.current_extent() is None)
other = U.Package(name="Q")
other.packagedElement.append(U.Class(name="Z"))
check("a different extent sees only its own roots",
      T.eval_body("Property.allInstances()->size()", cls, D,
                  extent=X.Extent(other)) == 0)


print("== corpus effect ==")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib  # noqa: E402
from umlmeta import ocl_emit as E, ocl_parse as P  # noqa: E402

lowered = parsed = 0
for modname in ("uml25", "sysml2", "sysml"):
    mod = importlib.import_module("umlmeta." + modname)
    for c in vars(mod).values():
        if not isinstance(c, type):
            continue
        for name, body in c.__dict__.get("CONSTRAINTS", ()):
            if body.strip() == "(no specification serialized)":
                continue
            try:
                tree = P.parse(body)
                parsed += 1
                E.to_python(tree)
                lowered += 1
            except Exception:                     # noqa: BLE001
                continue
check("1166 bodies parse", parsed == 1166, f"{parsed}")
check("the two extensions lift lowering to 1001", lowered == 1001,
      f"{lowered} (was 676)")


print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
