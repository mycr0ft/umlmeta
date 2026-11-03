#!/usr/bin/env python
"""O6 checks: the eight UML 2.5.1 (formal/2017-12-05) helper operations
implemented as local lowerings in ocl_translator and registered in
SY.DERIVED_FUNCS.

Oracles (each operation evaluated through the OCL translator against a
hand-built model, plus the spec body it transcribes):

  openEnd                §16.14.38.5  endData->select(value=null).end
  includesMultiplicity   §7.8.8.7     lowerBound<=M.lower and upper>=M.upper
  isCompatibleWith       §7.8.13.5    kind check (+ TypedElement conformsTo)
  isSubstitutableFor     §9.9.4.7     substitution.contract->includes
  matches                §17.12.9.4   Gate name/message/sort/signature
  isInsideCF             §17.12.9.4   opposite end in same CF operand
  isOutsideCF            §17.12.9.4   opposite end outside same CF
  behavior               §16.14.53.5  object pin type Behavior /
                                     BehavioredClassifier.classifierBehavior

Standard library only. Run: .venv/bin/python check_ocl_ops_uml25.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from umlmeta import derived as D  # noqa: E402
from umlmeta import ocl_symbols as SY  # noqa: E402
from umlmeta import ocl_translator as T  # noqa: E402
from umlmeta import uml25 as U  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


# -- shared model -----------------------------------------------------------
pkg = U.Package(name="P")
cA = U.Class(name="A")
cB = U.Class(name="B")
pkg.packagedElement += [cA, cB]

assoc = U.Association(name="assoc")
pkg.packagedElement.append(assoc)
e1 = U.Property(name="e1", type=cA)
e2 = U.Property(name="e2", type=cB)
assoc.memberEnd += [e1, e2]

rla = U.ReadLinkAction(name="rla")
pkg.packagedElement.append(rla)
ed_open = U.LinkEndData(end=e2)                       # no value pin
ed_val = U.LinkEndData(end=e1, value=U.InputPin(name="v"))
rla.endData += [ed_open, ed_val]


def prop_mult(lo, hi):
    p = U.Property(name="m")
    if lo is not None:
        p.lowerValue = U.LiteralInteger(value=lo)
    if hi is not None:
        p.upperValue = U.LiteralUnlimitedNatural(
            value="*" if hi == "*" else hi)
    return p


m11 = prop_mult(None, None)        # defaults 1..1
m01 = prop_mult(0, 1)
m2 = prop_mult(0, 2)
mstar = prop_mult(0, "*")

contract = U.Class(name="Contract")
sub1 = U.Class(name="Sub1")
sub_other = U.Class(name="SubOther")
s = U.Substitution()
sub1.substitution.append(s)
s.contract = contract

# interaction with a combined fragment, gates, messages
inter = U.Interaction(name="I")
pkg.packagedElement.append(inter)
cf = U.CombinedFragment(name="cf")
inter.fragment.append(cf)
op = U.InteractionOperand(name="op")
cf.operand.append(op)
g_out = U.Gate(name="g_out")        # boundary gate, message leaves the CF
cf.cfragmentGate.append(g_out)
g_in = U.Gate(name="g_in")          # boundary gate, message enters the CF
cf.cfragmentGate.append(g_in)
mos = U.MessageOccurrenceSpecification(name="mos")
op.fragment.append(mos)             # inside the operand of cf

m_out = U.Message(name="sig", messageSort=U.MessageSort.synchCall)
m_out.sendEvent = g_out
m_in = U.Message(name="sig", messageSort=U.MessageSort.synchCall)
m_in.receiveEvent = g_out
m_in2 = U.Message(name="sig2", messageSort=U.MessageSort.synchCall)
m_in2.sendEvent = g_in
m_in2.receiveEvent = mos
for _m in (m_out, m_in, m_in2):
    T._note_message_ends(_m)

# StartObjectBehaviorAction
soba = U.StartObjectBehaviorAction(name="soba")
pkg.packagedElement.append(soba)
beh = U.StateMachine(name="beh")
pin = U.InputPin(name="obj", type=beh)
soba.object = pin
cls_bc = U.Class(name="WithBC")
cb = U.OpaqueBehavior(name="cb") if hasattr(U, "OpaqueBehavior") else U.Activity(name="cb")
cls_bc.classifierBehavior = cb
soba2 = U.StartObjectBehaviorAction(name="soba2")
pkg.packagedElement.append(soba2)
soba2.object = U.InputPin(name="obj2", type=cls_bc)
soba3 = U.StartObjectBehaviorAction(name="soba3")
pkg.packagedElement.append(soba3)
soba3.object = U.InputPin(name="obj3", type=cA)  # a plain Class: null


print("== registration ==")
for ocl_name in ("openEnd", "includesMultiplicity", "isCompatibleWith",
                 "isSubstitutableFor", "matches", "isInsideCF",
                 "isOutsideCF", "behavior"):
    entry = SY.DERIVED_FUNCS.get(ocl_name)
    check(f"{ocl_name} registered as ('local', fn)",
          entry is not None and entry[0] == "local", str(entry))


print("== openEnd (§16.14.38.5) ==")
check("lowers to open_end(self)",
      T.translate("self.openEnd()->size()") == "len(_nav(open_end(self)))",
      T.translate("self.openEnd()->size()"))
check("the end with no value pin is the open end",
      T.eval_body("self.openEnd()->size()", rla, D) == 1)
check("it is end e2",
      T.eval_body("self.openEnd()->first().name", rla, D) == "e2")
check("the valued end is not open",
      T.eval_body("self.openEnd()->includes(endData->select(end.name='e1').end)",
                  rla, D) is False)


print("== includesMultiplicity (§7.8.8.7) ==")
check("1..1 does not include 0..2",
      T.eval_body("self.includesMultiplicity(m2)", m11, D) is False
      if False else T.includes_multiplicity(m11, m2) is False)
check("1..1 includes 1..1", T.includes_multiplicity(m11, prop_mult(None, None)) is True)
check("0..* includes 0..2", T.includes_multiplicity(mstar, m2) is True)
check("0..2 does not include 0..*", T.includes_multiplicity(m2, mstar) is False)
check("0..* includes 0..*", T.includes_multiplicity(mstar, prop_mult(0, "*")) is True)
check("0..1 includes 1..1 (every cardinality of 1..1 is in 0..1)",
      T.includes_multiplicity(m01, prop_mult(None, None)) is True)
check("1..1 does not include 0..1 (lower bound)",
      T.includes_multiplicity(prop_mult(None, None), m01) is False)
check("body through the translator (self vs self)",
      T.eval_body("self.includesMultiplicity(self)", mstar, D) is True)


print("== isCompatibleWith (§7.8.13.5) ==")
pA = U.Property(name="pA", type=cA)          # Property is a TypedElement
pB = U.Property(name="pB", type=cB)
check("a Property is compatible with a Property of conforming type",
      T.is_compatible_with(pA, pA) is True)
check("kind mismatch is False (Property vs Class)",
      T.is_compatible_with(pA, cA) is False)
sub = U.Class(name="Sub")
U.Generalization(general=cA, specific=sub)
pSub = U.Property(name="pSub", type=sub)
check("Property typed by a subtype conforms to the supertype-typed one",
      T.is_compatible_with(pSub, pA) is True)
check("the reverse does not conform",
      T.is_compatible_with(pA, pSub) is False)
check("through the translator",
      T.eval_body("self.isCompatibleWith(self)", pSub, D) is True and
      T.eval_body("self.isCompatibleWith(self)", cA, D) is True)


print("== isSubstitutableFor (§9.9.4.7) ==")
check("a substitution naming the contract satisfies it",
      T.is_substitutable_for(sub1, contract) is True)
check("another classifier does not",
      T.is_substitutable_for(sub1, cA) is False)
check("no substitutions -> False",
      T.is_substitutable_for(sub_other, contract) is False)
check("through the translator",
      T.eval_body("self.isSubstitutableFor(self)", contract, D) is False and
      T.eval_body("self.isSubstitutableFor(self)", cA, D) is False)


print("== matches (§17.12.9.4) ==")
# g_out sends m_out; a matching formal gate receives a same-named message
g_formal = U.Gate(name="g_out")
m_formal = U.Message(name="sig", messageSort=U.MessageSort.synchCall)
m_formal.receiveEvent = g_formal
T._note_message_ends(m_formal)
inter2 = U.Interaction(name="I2")
pkg.packagedElement.append(inter2)
check("same name, same message, opposite roles -> matches",
      T.gate_matches(g_out, g_formal) is True)
g_same_dir = U.Gate(name="g_out")
m_same = U.Message(name="sig", messageSort=U.MessageSort.synchCall)
m_same.sendEvent = g_same_dir           # same direction as g_out: no match
T._note_message_ends(m_same)
check("same send direction does not match", T.gate_matches(g_out, g_same_dir) is False)
g_diff = U.Gate(name="other")
m_diff = U.Message(name="sig", messageSort=U.MessageSort.synchCall)
m_diff.receiveEvent = g_diff
T._note_message_ends(m_diff)
check("different gate name does not match", T.gate_matches(g_out, g_diff) is False)
g_sort = U.Gate(name="g_out")
m_sort = U.Message(name="sig", messageSort=U.MessageSort.asynchCall)
m_sort.receiveEvent = g_sort
T._note_message_ends(m_sort)
check("different messageSort does not match", T.gate_matches(g_out, g_sort) is False)
check("through the translator",
      T.eval_body("self.matches(self)", g_out, D) is False)  # same send dir


print("== isInsideCF / isOutsideCF (§17.12.9.4) ==")
# a message whose send is the outside gate and whose receive is the
# inside gate: oppositeEnd(g_out) = g_in (same CF) -> outside CF
m_cf = U.Message(name="sig", messageSort=U.MessageSort.synchCall)
m_cf.sendEvent = g_out
m_cf.receiveEvent = g_in
T._note_message_ends(m_cf)
# a message whose receive is an occurrence specification inside cf's
# operand: oppositeEnd(g_in2) = mos -> g_in2 is inside CF
g_in2 = U.Gate(name="g_in2")
cf.cfragmentGate.append(g_in2)
m_in3 = U.Message(name="sig3", messageSort=U.MessageSort.synchCall)
m_in3.sendEvent = g_in2
m_in3.receiveEvent = mos
T._note_message_ends(m_in3)
check("g_out's opposite end (g_in) is at the same CF boundary -> outside CF",
      T.gate_is_outside_cf(g_out) is True)
check("g_out is not inside CF", T.gate_is_inside_cf(g_out) is False)
check("g_in2's opposite end (mos) is in cf's operand -> inside CF",
      T.gate_is_inside_cf(g_in2) is True)
check("g_in2 is not outside CF", T.gate_is_outside_cf(g_in2) is False)
lonely = U.Gate(name="lonely")
check("a gate with no boundary CF is neither",
      T.gate_is_inside_cf(lonely) is False and T.gate_is_outside_cf(lonely) is False)
check("through the translator",
      T.eval_body("self.isInsideCF()", g_in2, D) is True and
      T.eval_body("self.isOutsideCF()", g_out, D) is True)


print("== behavior (§16.14.53.5) ==")
check("object pin typed by a Behavior returns that Behavior",
      T.start_object_behavior(soba) is beh)
check("BehavioredClassifier type returns its classifierBehavior",
      T.start_object_behavior(soba2) is cb)
check("plain Class type returns null",
      T.start_object_behavior(soba3) is None)
check("constraint body self.behavior()<>null holds on soba",
      T.eval_body("self.behavior()<>null", soba, D) is True)
check("and fails on soba3",
      T.eval_body("self.behavior()<>null", soba3, D) is False)


print("== corpus effect ==")
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
check("1167 bodies parse", parsed == 1167, f"{parsed}")
check("the eight O6 ops lift lowering to 1153", lowered == 1153,
      f"{lowered} (was 1024 before the O6 uml25 ops)")


print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
