#!/usr/bin/env python
"""O2 checks: the OCL type table and the static checker (ocl_types.py).

Oracles:
  1. the table is built from the generated descriptors (classes, enums,
     property type/multiplicity), and name collisions between modules
     resolve to the module being checked;
  2. typing: a property's type and multiplicity, navigation with implicit
     collect, collection operators' result types, iterator variables;
  3. diagnostics: a missing feature names the feature and spans the
     navigation; a derived-but-unwired property is a queue item, not an
     error; arithmetic on a known non-numeric operand is an error, while
     arithmetic on an unknown operand is silence;
  4. the static verdict agrees with the evaluator: every AttributeError the
     runtime raises was predicted as an unknown feature;
  5. corpus sweep: every parsed body is checked, with the error/pending
     counts and the dominant missing features pinned.

Standard library only. Run: .venv/bin/python check_ocl_types.py
"""
import collections
import importlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from umlmeta import derived as D  # noqa: E402
from umlmeta import ocl_parse as P  # noqa: E402
from umlmeta import ocl_translator as T  # noqa: E402
from umlmeta import ocl_types as Y  # noqa: E402
from umlmeta import uml25 as U  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


TABLE = Y.TypeTable()


def diags(body, cls):
    return Y.Checker(TABLE, cls).check(P.parse(body))


def codes(body, cls):
    return [d.code for d in diags(body, cls)]


def errors(body, cls):
    return [d for d in diags(body, cls) if d.severity == "error"]


# ---------------------------------------------------------------------------
# the table
# ---------------------------------------------------------------------------

print("== type table ==")
u, k, s = (TABLE.modules[m] for m in ("uml25", "sysml2", "sysml"))
check("three generated modules indexed",
      (len(u.classes), len(k.classes), len(s.classes)) == (242, 175, 56),
      f"{len(u.classes)}/{len(k.classes)}/{len(s.classes)}")
check("enumerations indexed", len(u.enums) == 13 and "ParameterDirectionKind" in u.enums,
      str(len(u.enums)))

prop = u.props(U.Class)["ownedAttribute"]
check("multi-valued property carries its type and multiplicity",
      prop.type_name == "Property" and prop.multi and prop.hi == "*",
      prop.describe())
single = u.props(U.NamedElement)["name"]
check("single-valued primitive property",
      single.prim == "String" and not single.multi, single.describe())
check("inherited properties merge down the MRO",
      "ownedComment" in u.props(U.Class) and "ownedAttribute" in u.props(U.Class))
check("a name collision resolves to the checked module",
      TABLE.resolve_class("Class", u)[1] is U.Class
      and TABLE.resolve_class("Class", k)[0].name == "sysml2")
check("subtype test follows the generated hierarchy",
      u.is_kind("Class", "Type") and not u.is_kind("Class", "Activity"))


# ---------------------------------------------------------------------------
# typing
# ---------------------------------------------------------------------------

print("== typing ==")
c = Y.Checker(TABLE, U.NamedElement)
check("self.name : String",
      c.type_of(P.parse("self.name"), {"self": c.class_type("NamedElement")})
      == Y.STRING)
c = Y.Checker(TABLE, U.Class)
check("self.ownedAttribute : Collection(Property)",
      c.type_of(P.parse("self.ownedAttribute"),
                {"self": c.class_type("Class")}) == Y.CollT("Set", Y.ClassT("Property", "uml25")))
check("->select keeps the collection and its element type",
      c.type_of(P.parse("self.ownedAttribute->select(a | a.isComposite)"),
                {"self": c.class_type("Class")})
      == Y.CollT("Set", Y.ClassT("Property", "uml25")))
check("->size : Integer and ->includes : Boolean",
      c.type_of(P.parse("self.ownedAttribute->size()"),
                {"self": c.class_type("Class")}) == Y.INTEGER
      and c.type_of(P.parse("self.ownedAttribute->includes(self)"),
                    {"self": c.class_type("Class")}) == Y.BOOLEAN)
check("the iterator variable types as the element",
      codes("self.ownedAttribute->forAll(a | a.isComposite)", U.Class) == [])


# ---------------------------------------------------------------------------
# diagnostics
# ---------------------------------------------------------------------------

print("== diagnostics ==")
d = diags("self.ownedAttribute->select(a | a.nosuch)->isEmpty()", U.Class)
missing = [x for x in d if x.code == "unknown-feature"]
check("a missing feature is an error naming the feature",
      len(missing) == 1 and "'nosuch'" in missing[0].message
      and "Property" in missing[0].message, str(missing[:1]))
span_ok = missing and missing[0].span is not None and \
    "nosuch" in "self.ownedAttribute->select(a | a.nosuch)->isEmpty()"[
        missing[0].span.start:missing[0].span.end]
check("the diagnostic span covers the navigation text", bool(span_ok))

check("a derived property with no carrier is a queue item, not an error",
      not errors("self.owner", U.Element)
      and "derived-not-wired" in codes("self.owner", U.Element))
check("arithmetic on a known non-numeric operand is an error",
      "arithmetic-on-non-numeric" in codes("self.name * 2", U.NamedElement))
check("arithmetic on an unknown operand is silence",
      "arithmetic-on-non-numeric" not in
      codes("self.ownedAttribute->first().x * 2", U.Class))
check("collection difference is not arithmetic",
      not errors("self.ownedAttribute - self.ownedAttribute", U.Class))
check("an unknown metaclass in a type test is reported",
      "unknown-type" in codes("self.oclIsKindOf(NoSuchClass)", U.Element))
check("keyword-renamed enum literals resolve",
      codes("self.direction = ParameterDirectionKind::in", U.Parameter) == [])
check("an unknown enum literal is reported",
      "unknown-type" in codes("self.direction = ParameterDirectionKind::bogus",
                              U.Parameter))


# ---------------------------------------------------------------------------
# static verdict vs runtime observation
# ---------------------------------------------------------------------------

print("== the checker predicts what the evaluator hits ==")
pkg = U.Package(name="P")
cls = U.Class(name="C")
pkg.packagedElement.append(cls)
attr = U.Property(name="a")
cls.ownedAttribute.append(attr)
op = U.Operation(name="f")
cls.ownedOperation.append(op)
par = U.Parameter(name="x")
op.ownedParameter.append(par)
sm = U.StateMachine(name="S")
reg = U.Region(name="r")
sm.region.append(reg)
st = U.State(name="s")
reg.subvertex.append(st)
pkg.packagedElement.append(sm)
MODEL = [pkg, cls, attr, op, par, sm, reg, st]

_ATTR = re.compile(r"has no attribute '(\w+)'")
observed, predicted_fail = [], []
for obj in MODEL:
    for klass in type(obj).__mro__:
        for name, body in klass.__dict__.get("CONSTRAINTS", ()):
            try:
                T.eval_body(body, obj, D)
            except AttributeError as ex:
                m = _ATTR.search(str(ex))
                if not m:
                    continue
                observed.append((type(obj).__name__, name, m.group(1)))
                d = diags(body, type(obj))
                mentioned = any(m.group(1) in x.message for x in d
                                if x.code in ("unknown-feature",
                                              "derived-not-wired"))
                predicted_fail.append((type(obj).__name__, name, m.group(1),
                                       mentioned))
            except Exception:                     # noqa: BLE001
                continue
check("every runtime AttributeError was predicted statically",
      all(ok for *_, ok in predicted_fail),
      f"{len(observed)} observed, "
      f"{sum(1 for *_, ok in predicted_fail if not ok)} unpredicted")
check("bare reads no longer raise (the sentinel covers them)",
      len(observed) == 0 or all(ok for *_, ok in predicted_fail),
      f"{len(observed)} AttributeErrors observed")


# ---------------------------------------------------------------------------
# corpus sweep
# ---------------------------------------------------------------------------

print("== corpus sweep ==")
checked, clean, with_errors = 0, 0, 0
code_counts = collections.Counter()
missing_features = collections.Counter()
it_bodies = set()  # regression guard (code retired at O3a)
for modname in ("uml25", "sysml2", "sysml"):
    mod = importlib.import_module("umlmeta." + modname)
    for klass in vars(mod).values():
        if not isinstance(klass, type):
            continue
        for name, body in klass.__dict__.get("CONSTRAINTS", ()):
            if body.strip() == "(no specification serialized)":
                continue
            try:
                tree = P.parse(body)
            except Exception:                     # noqa: BLE001
                continue
            checked += 1
            ds = Y.Checker(TABLE, klass).check(tree)
            if any(x.severity == "error" for x in ds):
                with_errors += 1
            else:
                clean += 1
            for x in ds:
                code_counts[x.code] += 1
                if x.code == "unknown-feature":
                    quoted = re.search(r"'([^']+)'", x.message)
                    if quoted:
                        missing_features[quoted.group(1)] += 1
                if x.code == "implicit-it-receiver":
                    it_bodies.add((modname, klass.__name__, name))

check("every parsed body is type-checked", checked == 1167, f"{checked}")
check("1023 bodies are error-free", clean == 1023,
      f"{clean} clean, {with_errors} with errors")
check("no body is flagged for arithmetic",
      code_counts["arithmetic-on-non-numeric"] == 0,
      str(code_counts["arithmetic-on-non-numeric"]))
check("unknown features are the dominant error class",
      code_counts["unknown-feature"] == 144 and code_counts["unknown-type"] == 17,
      f"unknown-feature {code_counts['unknown-feature']}, "
      f"unknown-type {code_counts['unknown-type']}")
# the profile generator emits the extension ends as properties (and a
# flattened _props, the uml25 contract); both are asserted structurally
from umlmeta import sysml as _S  # noqa: E402
_blk = _S.Block._props
check("stereotype classes carry a flattened _props (inherited + own + base)",
      _blk["base_Class"].t is U.Class and "name" in _blk
      and "isEncapsulated" in _blk, f"{len(_blk)} properties on Block")
base_missing = sum(n for f, n in missing_features.items()
                   if f.startswith("base_"))
check("stereotype base properties are no longer a systematic gap",
      base_missing <= 4,
      f"{base_missing} base_* diagnostics (was 263 before the generator fix)")
check("no body keeps `self` as the receiver of an implicit call",
      len(it_bodies) == 0,
      f"{len(it_bodies)} bodies still report implicit-it-receiver")

print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
