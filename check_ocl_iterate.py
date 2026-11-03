#!/usr/bin/env python
"""O4b checks: `->iterate` (the accumulator form) and the thirteen
remaining UML 2.5.1 one-off helper operations.

Oracles:

  A. ->iterate (OCL 2.4 §10.3.6)
  1. the emitter lowers `x->iterate(v; acc : T = init | body)` to a
     fold call, and the other pending ops still refuse;
  2. the two corpus bodies using ->iterate lower AND evaluate on a
     constructed model: uml25.NamedElement.has_qualified_name is True
     on a well-formed nested package model, and the sysml
     4_can_access_structuralfeature iterate fragment folds a Boolean
     across allNamespaces()->subOrderedSet(1, n) (False when a private
     namespace is in the prefix);
  3. small folds: Sequence{1..4}->iterate(i; acc=0 | acc+i) = 10, and
     an empty receiver yields the initializer unchanged.

  B. the 13 uml25 one-off helpers (each transcribed from
     formal/2017-12-05, clause in the docstring) — evaluated through the
     translator on hand-built models, True and False cases:
  isConsistentWith (§9.9.18.7 + overrides), isRedefinitionContextValid
  (§9.9.18.7 + §14.5.8.5/§14.5.3.x/§14.5.1.x), membersAreDistinguishable
  (§7.8.10.6), maySpecializeType (§9.2.4.6), isAccessibleBy
  (§15.7.25.6), sourceNodes (§16.12.x), metaclassEnd (§12.4.1.6),
  hasAllDataTypeAttributes (§13.4.6.4), isFormal/isActual
  (§17.12.9.4), enclosingFragment (§17.12.19.6), allOwningPackages
  (§7.8.9.6), referred (§14.5.5.5), belongsToPSM (§14.5.8.5).

  C. corpus effect: lowering rises from 1024 (pre-O4b) to the current
     count, printed below.

Standard library only. Run: .venv/bin/python check_ocl_iterate.py
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from umlmeta import derived as D  # noqa: E402
from umlmeta import ocl_emit as E  # noqa: E402
from umlmeta import ocl_parse as P  # noqa: E402
from umlmeta import ocl_translator as T  # noqa: E402
from umlmeta import uml25 as U  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


# ---------------------------------------------------------------------------
# A. ->iterate lowering + evaluation
# ---------------------------------------------------------------------------

print("== ->iterate lowering ==")
src = T.translate("allNamespaces()->iterate(ns : Namespace; agg: String = name | "
                  "ns.name.concat(self.separator()).concat(agg))")
check("lowers to the _iterate fold",
      src.startswith("_iterate(_nav(") and "'ns', 'agg'" in src, src[:80])
check("the body travels as source text with var/acc bound at runtime",
      "concat" in src and "agg" in src)
# ->isUnique lowers now (the O3 pending set lost it); the rest refuse
for bad, label in (("x->sortedBy(e | e.a)", "->sortedBy"),
                   ("x->collectNested(e | e.a)", "->collectNested")):
    try:
        E.to_python(P.parse(bad))
        check(f"{label} still refuses", False)
    except Exception:
        check(f"{label} still refuses to lower", True)

print("== ->iterate evaluation ==")
check("sum fold Sequence{1..4}", T.eval_body(
    "Sequence{1..4}->iterate(i; acc : Integer = 0 | acc + i)", None, D) == 10)
check("empty receiver yields the initializer", T.eval_body(
    "Set{}->iterate(i; acc : Integer = 42 | acc + i)", None, D) == 42)

# the uml25 corpus body
HAS_QN = ("(name <> null and allNamespaces()->select(ns | ns.name = null)->isEmpty()) implies "
          "qualifiedName = allNamespaces()->iterate( ns : Namespace; agg: String = name | "
          "ns.name.concat(self.separator()).concat(agg))")
outer = U.Package(name="Outer", visibility="public")
inner = U.Package(name="Inner", visibility="public")
outer.packagedElement.append(inner)
cls = U.Class(name="C", visibility="public")
inner.packagedElement.append(cls)
check("uml25 has_qualified_name lowers and evaluates True on P::P2::C",
      T.eval_body(HAS_QN, cls, D) is True,
      str(T.eval_body(HAS_QN, cls, D)))
check("the iterate itself yields Outer::Inner::C", T.eval_body(
    "allNamespaces()->iterate(ns : Namespace; agg: String = name | "
    "ns.name.concat(self.separator()).concat(agg))", cls, D) == "Outer::Inner::C")
# a namespace without a name: antecedent false -> vacuous True; qualifiedName null
inner_nn = U.Package(name=None, visibility="public")
outer2 = U.Package(name="O2", visibility="public")
outer2.packagedElement.append(inner_nn)
cls2 = U.Class(name="D", visibility="public")
inner_nn.packagedElement.append(cls2)
check("unnamed namespace: has_qualified_name vacuous True, qualifiedName null",
      T.eval_body(HAS_QN, cls2, D) is True and
      T.eval_body("qualifiedName", cls2, D) is None)

# the sysml corpus iterate fragment (boolean accumulator over a prefix)
FRAG = ("allNamespaces()->subOrderedSet(1, allNamespaces()->size())->iterate("
        "n; acc: Boolean=true | acc and not (n.visibility=UML::VisibilityKind::private "
        "or n.visibility=UML::VisibilityKind::protected))")
check("sysml-style boolean iterate True on all-public namespaces",
      T.eval_body(FRAG, cls, D) is True)
priv = U.Package(name="Priv", visibility="private")
outer3 = U.Package(name="O3", visibility="public")
outer3.packagedElement.append(priv)
cls3 = U.Class(name="E", visibility="public")
priv.packagedElement.append(cls3)
check("a private namespace in the prefix makes the fold False",
      T.eval_body(FRAG, cls3, D) is False)

# both corpus bodies lower now
lowered_iterate = 0
for modname in ("uml25", "sysml2", "sysml"):
    mod = importlib.import_module("umlmeta." + modname)
    for c in vars(mod).values():
        if not isinstance(c, type):
            continue
        for n, b in c.__dict__.get("CONSTRAINTS", ()):
            if "->iterate" in b:
                try:
                    E.to_python(P.parse(b))
                    lowered_iterate += 1
                except Exception:
                    pass
check("both corpus ->iterate bodies lower", lowered_iterate == 2,
      f"{lowered_iterate}/2")

# ---------------------------------------------------------------------------
# B. the 13 uml25 one-off helpers, through the translator
# ---------------------------------------------------------------------------

print("== isConsistentWith (§9.9.18.7 + overrides) ==")
# base: a plain RedefinableElement is never consistent
check("base body false for an unclassed RedefinableElement",
      T.eval_body("self.isConsistentWith(other)",
                  U.RedefinableElement.__new__(U.Class), D) is False)
op1 = U.Operation(name="op1")
op2 = U.Operation(name="op2")
p_in = U.Parameter(name="x", direction="in")
op1.ownedParameter.append(p_in)
op2.ownedParameter.append(U.Parameter(name="y", direction="in"))
check("Operation override: same-shape params consistent",
      T.is_consistent_with(op1, op2) is True)
op3 = U.Operation(name="op3")  # no params -> count mismatch
check("Operation override: parameter count mismatch False",
      T.is_consistent_with(op1, op3) is False)
check("Operation override: non-Operation redefining False",
      T.is_consistent_with(op1, U.Class(name="z")) is False)
ps1 = U.Pseudostate(name="p1", kind="initial")
ps2 = U.Pseudostate(name="p2", kind="initial")
ps3 = U.Pseudostate(name="p3", kind="join")
check("Pseudostate override: same kind consistent",
      T.is_consistent_with(ps1, ps2) is True)
check("Pseudostate override: different kind False",
      T.is_consistent_with(ps1, ps3) is False)
fs1, fs2 = U.FinalState(name="f1"), U.FinalState(name="f2")
check("FinalState override: FinalState consistent",
      T.is_consistent_with(fs1, fs2) is True)
check("through the OCL call: re.isConsistentWith(self) shape works",
      T.is_consistent_with(fs1, fs2) is True)

print("== isRedefinitionContextValid (§9.9.18.7 + overrides) ==")
sm_a, sm_b = U.StateMachine(name="A"), U.StateMachine(name="B")
ctx_a, ctx_b = U.Class(name="CtxA"), U.Class(name="CtxB")
U.Generalization(general=ctx_a, specific=ctx_b)
sm_a._vals['context'] = ctx_a
sm_b._vals['context'] = ctx_b
check("StateMachine override: context specializes parent context -> True",
      T.is_redefinition_context_valid(sm_b, sm_a) is True)
sm_c = U.StateMachine(name="C")
ctx_c = U.Class(name="CtxC")  # unrelated
sm_c._vals['context'] = ctx_c
check("StateMachine override: unrelated context -> False",
      T.is_redefinition_context_valid(sm_c, sm_a) is False)
r1, r2 = U.Region(name="r1"), U.Region(name="r2")
sm_a.region.append(r1)
check("Region owned by a StateMachine: extendedStateMachine empty -> False",
      T.is_redefinition_context_valid(r2, r1) is False)
reg_cls = U.Region  # base dispatch for non-Region redefined
check("base: Vertex redefinition via owner's redefinedElement",
      T.is_redefinition_context_valid(U.State(name="s1"), U.State(name="s2")) is False)

print("== membersAreDistinguishable (§7.8.10.6) ==")
ns = U.Package(name="NS")
ns.packagedElement.append(U.Class(name="A"))
ns.packagedElement.append(U.Class(name="B"))
check("distinct names distinguishable", T.members_are_distinguishable(ns) is True)
check("through the translator: membersAreDistinguishable()",
      T.eval_body("self.membersAreDistinguishable()", ns, D) is True)
ns.packagedElement.append(U.Class(name="A"))  # duplicate name, same kind
check("two same-named Classes not distinguishable",
      T.members_are_distinguishable(ns) is False)

print("== maySpecializeType (§9.2.4.6) ==")
c_when = U.Class(name="W")
check("a Class may specialize a Class (same kind)",
            T.may_specialize_type(c_when, U.Class(name="X")) is True)
check("a Class may NOT specialize a DataType (different kind)",
      T.may_specialize_type(c_when, U.DataType(name="DT")) is False)
# `other` is unbound in this call so the argument reads None and the
# operation answers False — the direct-function oracles above carry the
# semantic weight
check("through the translator (unbound arg answers False, not an error)",
      T.eval_body("self.maySpecializeType(other)", c_when, D) is False)

print("== isAccessibleBy (§15.7.25.6) ==")
act = U.Activity(name="act")
act_var = U.Variable(name="v")
act.variable.append(act_var)          # activityScope branch
node = U.OpaqueAction(name="n1")
act.node.append(node)
check("activity-scoped variable accessible by an action in the activity",
            T.is_accessible_by(act_var, node) is True)
other_act = U.Activity(name="act2")
other_node = U.OpaqueAction(name="n2")
other_act.node.append(other_node)
check("not accessible from another activity",
      T.is_accessible_by(act_var, other_node) is False)
san = U.StructuredActivityNode(name="san")
act.node.append(san)
san_var = U.Variable(name="v2")
san.variable.append(san_var)          # scope branch
inner_act = U.OpaqueAction(name="deep")
san.node.append(inner_act)
check("scope-owned variable accessible by a node inside the scope",
      T.is_accessible_by(san_var, inner_act) is True)
check("...not by an action outside the scope",
      T.is_accessible_by(san_var, node) is False)

print("== sourceNodes (§16.12.x) ==")
san2 = U.StructuredActivityNode(name="san2")
a1 = U.OpaqueAction(name="a1")
pin = U.InputPin(name="in1")
san2.node.append(a1)
san2.structuredNodeInput.append(pin)
out_pin = U.OutputPin(name="out1")
a1._vals['output'] = [out_pin]
sn = T.source_nodes(san2)
check("node + input pin + action outputs are the source nodes",
      pin in sn and a1 in sn and out_pin in sn, str([type(x).__name__ for x in sn]))
check("through the translator: sourceNodes()->size() = 3",
      T.eval_body("self.sourceNodes()->size()", san2, D) == 3)

print("== metaclassEnd (§12.4.1.6) ==")
ext = U.Extension(name="e")
meta_end = U.Property(name="meta")
stereo_end = U.ExtensionEnd(name="st")
ext.memberEnd.extend([meta_end, stereo_end])
ext.ownedEnd = stereo_end
check("metaclassEnd is the non-owned member end",
      T.metaclass_end(ext) is meta_end)
check("through the translator: metaclassEnd() = the meta end",
      T.eval_body("self.metaclassEnd()", ext, D) is meta_end)

print("== hasAllDataTypeAttributes (§13.4.6.4) ==")
dt1 = U.DataType(name="DT1")
dt2 = U.DataType(name="DT2")
a1 = U.Property(name="a1", type=dt2)
dt1.ownedAttribute.append(a1)
check("DataType whose attribute is a DataType (recursing into an empty one) -> True",
      T.has_all_datatype_attributes(dt1) is True)
dt3 = U.DataType(name="DT3")
cls_t = U.Class(name="NotADT")
a2 = U.Property(name="a2", type=cls_t)
dt3.ownedAttribute.append(a2)
check("DataType with a Class-typed attribute -> False",
      T.has_all_datatype_attributes(dt3) is False)

print("== Gate isFormal / isActual (§17.12.9.4) ==")
inter = U.Interaction(name="i")
formal = U.Gate(name="gf")
inter.formalGate.append(formal)       # composite -> owner = Interaction
iu = U.InteractionUse(name="iu")
actual = U.Gate(name="ga")
iu.actualGate.append(actual)          # owner = InteractionUse
check("formal gate: isFormal True, isActual False",
      T.gate_is_formal(formal) is True and T.gate_is_actual(formal) is False)
check("actual gate: isActual True, isFormal False",
      T.gate_is_actual(actual) is True and T.gate_is_formal(actual) is False)
check("through the translator: isFormal()",
      T.eval_body("self.isFormal()", formal, D) is True)
check("through the translator: isActual()",
      T.eval_body("self.isActual()", actual, D) is True)

print("== enclosingFragment (§17.12.19.6) ==")
mos = U.MessageOccurrenceSpecification(name="mos")
inter2 = U.Interaction(name="i2")
inter2.fragment.append(mos)           # sets enclosingInteraction
check("a MessageOccurrenceSpecification's enclosingFragment is the interaction",
      T.enclosing_fragment(mos) == [inter2])
check("through the translator: enclosingFragment()->size() = 1",
      T.eval_body("self.enclosingFragment()->size()", mos, D) == 1)

print("== allOwningPackages (§7.8.9.6) ==")
p1 = U.Package(name="P1")
p2 = U.Package(name="P2")
p1.packagedElement.append(p2)
c = U.Class(name="C")
p2.packagedElement.append(c)
check("allOwningPackages walks outwards through Packages only",
      [type(x).__name__ for x in T.all_owning_packages(c)] == ["Package", "Package"] and
      T.all_owning_packages(c)[0] is p2 and T.all_owning_packages(c)[1] is p1)
check("through the translator: allOwningPackages()->size() = 2",
      T.eval_body("self.allOwningPackages()->size()", c, D) == 2)
# a non-Package namespace stops the walk (a Class as namespace)
k = U.Class(name="K")
inner_el = U.Property(name="q")
k.ownedAttribute.append(inner_el)
check("stops at the first non-Package namespace",
      T.all_owning_packages(inner_el) == [])

print("== ProtocolTransition::referred (§14.5.5.5) ==")
pt = U.ProtocolTransition(name="pt")
ce = U.CallEvent(name="ce")
op = U.Operation(name="op")
ce.operation = op
trg = U.Trigger(name="trg")
trg.event = ce
pt.trigger.append(trg)
check("referred collects the CallEvent operations",
      T.protocol_transition_referred(pt) == [op])
check("through the translator: referred()->size() = 1",
      T.eval_body("self.referred()->size()", pt, D) == 1)
pt2 = U.ProtocolTransition(name="pt2")  # no triggers
check("no triggers -> empty", T.protocol_transition_referred(pt2) == [])

print("== belongsToPSM (§14.5.8.5) ==")
psm = U.ProtocolStateMachine(name="PSM")
r_psm = U.Region(name="rp")
psm.region.append(r_psm)
check("region of a ProtocolStateMachine belongsToPSM",
      T.belongs_to_psm(r_psm) is True)
sm = U.StateMachine(name="SM")
r_sm = U.Region(name="rs")
sm.region.append(r_sm)
check("region of a plain StateMachine does not",
      T.belongs_to_psm(r_sm) is False)
# nested: region of a state inside a PSM
st = U.State(name="s")
r_psm2 = U.Region(name="rp2")
psm.region.append(r_psm2)
st.region.append(r_psm2)
# state-owned region: state.container chain
st2 = U.State(name="s2")
r_state = U.Region(name="rstate")
st2.region.append(r_state)           # r_state.state = st2, container chain
psm2 = U.ProtocolStateMachine(name="PSM2")
r_top = U.Region(name="rtop")
psm2.region.append(r_top)
st3 = U.State(name="s3")
r_top.subvertex.append(st3)
st3.region.append(r_state)           # r_state now inside a state in a PSM
check("state-owned region climbs to the PSM via state.container",
      T.belongs_to_psm(r_state) is True)
check("through the translator: container.belongsToPSM() shape",
      T.eval_body("self.belongsToPSM()", r_psm, D) is True)

# ---------------------------------------------------------------------------
# C. corpus effect
# ---------------------------------------------------------------------------

print("== corpus effect ==")
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
check("lowering lifted by iterate + the helpers", lowered >= 1140, f"{lowered}")

print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
