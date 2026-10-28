#!/usr/bin/env python
"""check_v1_to_v2_as.py — checks for v1_to_v2_as.py, the R3 leg of the
SysML v1 -> v2 transformation conformance chain:

  R1  xmi21.py / mdzip_import.py read SysML v1 XMI into umlmeta.uml25 +
      umlmeta.sysml objects (abstract-syntax representation of the input);
  R3  v1_to_v2_as.py transforms those objects into umlmeta.sysml2 objects
      (abstract-syntax representation of the output) per ptc/2025-04-07;
  R2  gen/sysml2.py IS the normative SysML v2 abstract syntax (from the
      OMG CMOF XMI) and provides the runtime the transformed graph
      lives in (check_sysml2.py covers it).

Oracles here:
  1. R1 leg: a hand-written v1 XMI 2.1 file (UML-20090901 dialect, the
     DoDAFLibrary.xmi spelling) is read with xmi21 and transformed —
     file -> R1 objects -> R3 -> R2 AS graph, end to end.
  2. R3 mappings: each wave-A normative mapping checked against the
     transformation spec (ptc/2025-04-07) anchors, including the
     identity rule (one v1 element = one AS object; usages type-
     reference the SAME definition object, never a copy).
  3. Parity: the AS graph re-renders to the same textual notation the
     independently-validated textual pipeline (v1_to_v2.py, checked by
     check_v1_to_v2.py with sysmlpy) emits for the same model.
  4. Honesty: UnmappedFeature for everything without a normative
     mapping — never a guess.

Needs lxml (the R1 reader); everything else stdlib.
Run: python3 check_v1_to_v2_as.py
"""
import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from umlmeta import uml25 as U  # noqa: E402
from umlmeta import sysml as S  # noqa: E402
from umlmeta import sysml2 as S2  # noqa: E402
from umlmeta import v1_to_v2 as MT  # noqa: E402  (textual pipeline, parity oracle)
from umlmeta import v1_to_v2_as as A  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def find(root, name, cls=None):
    """All AS objects with declaredName == name (optionally of a class)."""
    hits = []

    def walk(el):
        if getattr(el, "declaredName", None) == name and (
                cls is None or isinstance(el, cls)):
            hits.append(el)
        for r in getattr(el, "ownedRelationship", []):
            for e in r.ownedRelatedElement:
                walk(e)
    walk(root)
    return hits


def typing_of(feature):
    return feature.ownedTyping[0].type if feature.ownedTyping else None


# == 1. R1 leg: v1 XMI file -> umlmeta.uml25 -> transform -> umlmeta.sysml2 ========
print("== R1 leg: v1 XMI -> AS ==")
XMI = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.0"
         xmlns:xmi="http://schema.omg.org/spec/XMI/2.1">
  <uml:Package xmi:id="p1" xmi:type="uml:Package">
    <name>FromXMI</name>
    <packagedElement xmi:type="uml:Class" xmi:id="c_engine">
      <name>Engine</name>
      <ownedAttribute xmi:type="uml:Property" xmi:id="a_rpm">
        <name>rpm</name>
        <type xmi:idref="dt_rpm"/>
      </ownedAttribute>
      <ownedAttribute xmi:type="uml:Property" xmi:id="a_piston">
        <name>piston</name>
        <type xmi:idref="c_piston"/>
        <aggregation>composite</aggregation>
      </ownedAttribute>
      <ownedAttribute xmi:type="uml:Property" xmi:id="a_leg">
        <name>leg</name>
        <type xmi:idref="c_piston"/>
      </ownedAttribute>
    </packagedElement>
    <packagedElement xmi:type="uml:Class" xmi:id="c_piston">
      <name>Piston</name>
      <generalization xmi:type="uml:Generalization" xmi:id="g1">
        <general xmi:idref="c_part"/>
      </generalization>
    </packagedElement>
    <packagedElement xmi:type="uml:Class" xmi:id="c_part">
      <name>Part</name>
    </packagedElement>
    <packagedElement xmi:type="uml:DataType" xmi:id="dt_rpm">
      <name>RPM</name>
    </packagedElement>
    <packagedElement xmi:type="uml:Enumeration" xmi:id="e_state">
      <name>EngineState</name>
      <ownedLiteral xmi:type="uml:EnumerationLiteral" xmi:id="l_off"><name>off</name></ownedLiteral>
      <ownedLiteral xmi:type="uml:EnumerationLiteral" xmi:id="l_on"><name>on</name></ownedLiteral>
    </packagedElement>
  </uml:Package>
</xmi:XMI>
"""
with tempfile.NamedTemporaryFile("w", suffix=".xmi", delete=False) as fp:
    fp.write(XMI)
    xmi_path = fp.name
try:
    pkgs = A.transform_xmi(xmi_path)
    check("transform_xmi returns one AS package", len(pkgs) == 1
          and isinstance(pkgs[0], S2.Package))
    as_pkg = pkgs[0]
    check("AS package carries the v1 name", as_pkg.declaredName == "FromXMI")
    eng = find(as_pkg, "Engine", S2.OccurrenceDefinition)
    check("v1 Class -> OccurrenceDefinition (7.7.4.2.37 family)",
          len(eng) == 1)
    piston = find(as_pkg, "Piston", S2.OccurrenceDefinition)[0]
    part = find(as_pkg, "Part", S2.OccurrenceDefinition)[0]
    check("XMI generalization -> Subclassification to the indexed object",
          len(piston.ownedSpecialization) == 1
          and piston.ownedSpecialization[0].general is part)
    rpm = find(as_pkg, "rpm", S2.AttributeUsage)[0]
    check("XMI property typed by DataType -> AttributeUsage typed",
          typing_of(rpm) is find(as_pkg, "RPM", S2.AttributeDefinition)[0])
    pist = find(as_pkg, "piston", S2.OccurrenceUsage)[0]
    check("XMI property typed by Class -> OccurrenceUsage typed",
          typing_of(pist) is piston)
    # R1 dialect honesty: the UML-20090901 reader carries the
    # <aggregation> child (2.1-dialect enum text feature), so the AS
    # usage is composite — matching the hand-built runtime path, not
    # silently referential (reader extension, Cameo-dialect commit)
    from umlmeta import xmi21  # noqa: E402
    reader = xmi21.read_xmi21(xmi_path)
    check("R1 reader carries <aggregation>, no unmapped entry",
          ("a_piston", "aggregation") not in reader.unmapped_features
          and pist.ownedTyping)
    pleg = find(as_pkg, "leg", S2.OccurrenceUsage)[0]
    check("XMI composite -> composite usage; unmarked -> referential",
          pist._vals.get("isComposite") is None
          and pleg._vals.get("isComposite") is False)
    est = find(as_pkg, "EngineState", S2.EnumerationDefinition)[0]
    check("XMI enumeration literals -> EnumerationUsage features",
          [f.declaredName for f in est.feature] == ["off", "on"])
finally:
    Path(xmi_path).unlink()


# == 2. R3 wave-A mappings over a stereotype-carrying v1 model =============
print("== R3 wave-A mappings ==")
V = U.Package(name="Vehicle")
engine = S.Block(name="Engine"); V.add("packagedElement", engine)
piston = S.Block(name="Piston"); V.add("packagedElement", piston)
g = U.Generalization(); g.general = engine
piston.add("generalization", g)
kg = S.ValueType(name="Kilogram"); V.add("packagedElement", kg)
color = U.Enumeration(name="Color")
for lit in ("red", "green"):
    color.ownedLiteral.append(U.EnumerationLiteral(name=lit))
V.add("packagedElement", color)
cb = S.ConstraintBlock(name="Adder"); V.add("packagedElement", cb)
legacy = U.Class(name="Legacy"); V.add("packagedElement", legacy)
actor = U.Actor(name="Operator"); V.add("packagedElement", actor)

pist = U.Property(name="piston"); pist.type = piston
pist.aggregation = U.AggregationKind.composite
engine.add("ownedAttribute", pist)
ref_part = U.Property(name="sibling"); ref_part.type = piston
engine.add("ownedAttribute", ref_part)
mass = U.Property(name="mass"); mass.type = kg
engine.add("ownedAttribute", mass)
paint = U.Property(name="paint"); paint.type = color
engine.add("ownedAttribute", paint)
loose = U.Property(name="loose")
engine.add("ownedAttribute", loose)
leg = U.Property(name="leg"); leg.type = legacy
leg.aggregation = U.AggregationKind.composite
engine.add("ownedAttribute", leg)
leg_ref = U.Property(name="legRef"); leg_ref.type = legacy
engine.add("ownedAttribute", leg_ref)
cm = U.Comment(); cm.body = "the engine block"
engine.add("ownedComment", cm)

as_pkg = A.transform_package(V)

eng_defs = find(as_pkg, "Engine", S2.PartDefinition)
check("Block -> PartDefinition (7.8.4.3.3)", len(eng_defs) == 1)
engine_as = eng_defs[0]
check("one AS definition per v1 Block (index identity)",
      len(find(as_pkg, "Piston", S2.PartDefinition)) == 1)
piston_as = find(as_pkg, "Piston", S2.PartDefinition)[0]

pist_as = find(as_pkg, "piston", S2.PartUsage)[0]
check("composite block-typed Property -> PartUsage (7.8.4.3.13)",
      pist_as._vals.get("isComposite", True) is True)
check("PartUsage types reference the indexed PartDefinition object",
      typing_of(pist_as) is piston_as)
sib_as = find(as_pkg, "sibling", S2.PartUsage)[0]
check("non-composite block-typed Property -> PartUsage isComposite=false"
      " (the 'ref part' form)", sib_as._vals.get("isComposite") is False)
mass_as = find(as_pkg, "mass", S2.AttributeUsage)[0]
check("ValueType -> AttributeDefinition (7.8.4.3.15), usage typed by it",
      typing_of(mass_as) is find(as_pkg, "Kilogram", S2.AttributeDefinition)[0])
paint_as = find(as_pkg, "paint", S2.AttributeUsage)[0]
check("Enumeration -> EnumerationDefinition; typed AttributeUsage",
      typing_of(paint_as) is find(as_pkg, "Color", S2.EnumerationDefinition)[0])
loose_as = find(as_pkg, "loose", S2.Feature)[0]
check("untyped Property -> Feature, no typing", loose_as is not None
      and loose_as.ownedTyping == [])
leg_as = find(as_pkg, "leg", S2.OccurrenceUsage)[0]
check("Class-typed composite Property -> composite OccurrenceUsage"
      " (7.7.4.2.37)", leg_as._vals.get("isComposite", True) is True
      and typing_of(leg_as) is find(as_pkg, "Legacy", S2.OccurrenceDefinition)[0])
legr_as = find(as_pkg, "legRef", S2.OccurrenceUsage)[0]
check("Class-typed referential Property -> OccurrenceUsage"
      " isComposite=false", legr_as._vals.get("isComposite") is False)
cb_as = find(as_pkg, "Adder", S2.ConstraintDefinition)
check("ConstraintBlock -> ConstraintDefinition (7.8.5.2.1)",
      len(cb_as) == 1)
actor_as = find(as_pkg, "Operator", S2.PartDefinition)
check("Actor -> PartDefinition (7.7.13.3.1)", len(actor_as) == 1)
piston_sub = piston_as.ownedSpecialization
check("Generalization -> Subclassification, general = indexed object",
      len(piston_sub) == 1 and piston_sub[0].general is engine_as)
doc = find(as_pkg, None)  # documentation has no name
docs = [e for e in engine_as.ownedElement if isinstance(e, S2.Documentation)]
check("Comment -> Documentation owned by the documented element"
      " (7.4.2.1.9)", len(docs) == 1 and docs[0].body == "the engine block"
      and docs[0] in engine_as.ownedElement)
check("Documentation annotates the engine via an Annotation relationship"
      " (runtime-elided back-ends documented)",
      len(docs) == 1
      and any(isinstance(r, S2.Annotation)
              and r.annotatedElement is engine_as
              for r in docs[0].ownedRelationship))
color_as = find(as_pkg, "Color", S2.EnumerationDefinition)[0]
check("EnumerationLiteral -> EnumerationUsage via FeatureMembership",
      [f.declaredName for f in color_as.feature] == ["red", "green"])

print()
print("== R2 runtime wiring over the transformed graph ==")
check("FeatureMembership makes the definition the featuringType"
      " (owner back-wire)", pist_as.owner is not None
      and type(pist_as.owner).__name__ == "FeatureMembership"
      and pist_as.owner.owner is engine_as)
check("membership chain: pistons reachable via ownedElement",
      pist_as in engine_as.ownedElement)
check("Type.feature (computed runtime): Engine features complete",
      [f.declaredName for f in engine_as.feature]
      == ["piston", "sibling", "mass", "paint", "loose", "leg", "legRef"])
check("FeatureTyping back-wire: typedFeature is the usage",
      pist_as.ownedTyping[0].typedFeature is pist_as
      or pist_as.ownedTyping[0].owningFeature is pist_as)
check("Subclassification owned by the specific definition",
      piston_sub[0].owner is piston_as)

print()
print("== parity with the validated textual pipeline ==")
textual = MT.emit_v2(V)

AS_KW = {"Package": "package", "PartDefinition": "part def",
         "AttributeDefinition": "attribute def",
         "EnumerationDefinition": "enum def",
         "ConstraintDefinition": "constraint def",
         "OccurrenceDefinition": "occurrence def"}


def render_as(el, ind=0):
    pad = "  " * ind
    n = el.declaredName
    if isinstance(el, S2.Documentation):
        body = " ".join((el.body or "").split())
        return ([f"{pad}doc /* {body} */"] if body else [])
    if isinstance(el, S2.EnumerationUsage):
        return [f"{pad}{n};"]          # literal: bare-name form
    if isinstance(el, (S2.PartUsage, S2.AttributeUsage, S2.ReferenceUsage)):
        t = typing_of(el)
        kw = ("part" if isinstance(el, S2.PartUsage) else "attribute")
        if not el._vals.get("isComposite", True):
            kw = "ref " + kw
        line = f"{pad}{kw} {n}" + (f" : {t.declaredName};" if t else ";")
        return [line]
    if isinstance(el, S2.OccurrenceUsage):
        t = typing_of(el)
        kw = "occurrence" if el._vals.get("isComposite", True) \
            else "ref occurrence"
        return [f"{pad}{kw} {n}" + (f" : {t.declaredName};" if t else ";")]
    if isinstance(el, S2.Feature):
        return [f"{pad}{n};"]          # untyped: bare-name feature form
    kw = AS_KW.get(type(el).__name__)
    if kw is None:
        return []                      # runtime-elided: not rendered
    kids = []
    for r in el.ownedRelationship:
        for e in r.ownedRelatedElement:
            kids.append(e)
    supers = [r.general.declaredName
              for r in getattr(el, "ownedSpecialization", ())]
    line = f"{pad}{kw} {n}"
    if supers:
        line += f" :> {', '.join(supers)}"
    if not kids:
        return [line + ";"]
    lines = [line + " {"]
    for k in kids:
        lines += render_as(k, ind + 1)
    lines.append(pad + "}")
    return lines


as_textual = "\n".join(render_as(as_pkg))
print("---- textual pipeline (v1_to_v2.py) ----")
print(textual)
print("---- AS graph rendered ----")
print(as_textual)
print("----------------------------------------")
check("AS graph renders to the same notation the textual pipeline emits",
      as_textual == textual,
      "differences above" if as_textual != textual else "identical")

print()
print("== wave B: state machines and activities ==")
smpkg = U.Package(name="Beh")
sm = U.StateMachine(name="OpMode")
region = U.Region(name="r")
sm.region.append(region)
init0 = U.Pseudostate(name="start")
init0._vals["kind"] = U.PseudostateKind.initial
idle = U.State(name="Idle")
running = U.State(name="Running")
region.subvertex.append(init0)
region.subvertex.append(idle)
region.subvertex.append(running)
t0 = U.Transition(name="boot")
region.transition.append(t0)
t0.source = init0
t0.target = idle
t1 = U.Transition(name="power_on")
region.transition.append(t1)
t1.source = idle
t1.target = running
smpkg.add("packagedElement", sm)
beh = A.transform_package(smpkg)
sm_def = beh.ownedElement[0]
check("StateMachine -> StateDefinition (7.7.11.2.16)",
      type(sm_def).__name__ == "StateDefinition",
      type(sm_def).__name__)
sm_members = [type(e).__name__ for e in sm_def.ownedElement]
check("state def holds 2 StateUsages + 2 TransitionUsages",
      sm_members.count("StateUsage") == 2
      and sm_members.count("TransitionUsage") == 2, str(sm_members))
boot_tu = [e for e in sm_def.ownedElement
           if type(e).__name__ == "TransitionUsage"
           and e.declaredName == "boot"][0]
entry_au = [x for r in sm_def.ownedRelationship
            if type(r).__name__ == "StateSubactionMembership"
            for x in r.ownedRelatedElement][0]
check("transition from initial sources the entry ActionUsage "
      "(7.7.11.2.18 ends rule)",
      boot_tu.source is entry_au
      and boot_tu.target.declaredName == "Idle")
ssms = [r for r in sm_def.ownedRelationship
        if type(r).__name__ == "StateSubactionMembership"]
check("initial Pseudostate -> unnamed ActionUsage as the ENTRY "
      "subaction of the StateDefinition (7.7.11.2.8/.9, formal 2.0)",
      len(ssms) == 1
      and str(ssms[0].kind) == "StateSubactionKind.entry"
      and [type(x).__name__ for x in ssms[0].ownedRelatedElement]
      == ["ActionUsage"]
      and ssms[0].ownedRelatedElement[0].declaredName is None,
      str([(str(r.kind), [type(x).__name__ for x in r.ownedRelatedElement])
           for r in ssms]))
tu = [e for e in sm_def.ownedElement
      if type(e).__name__ == "TransitionUsage"
      and e is not boot_tu][0]
check("transition source/target wired",
      tu.source.declaredName == "Idle" and tu.target.declaredName == "Running")

actpkg = U.Package(name="ActPkg")
act = U.Activity(name="Run")
a1 = U.OpaqueAction(name="step1"); act.node.append(a1)
a2 = U.OpaqueAction(name="step2"); act.node.append(a2)
fl = U.ControlFlow(name="f1"); act.edge.append(fl)
fl.source = a1; fl.target = a2
actpkg.add("packagedElement", act)
out2 = A.transform_package(actpkg)
act_def = out2.ownedElement[0]
check("Activity -> ActionDefinition (7.7.3.3.1)",
      type(act_def).__name__ == "ActionDefinition",
      type(act_def).__name__)
kinds = [type(e).__name__ for e in act_def.ownedElement]
check("activity: 2 ActionUsages + 1 SuccessionAsUsage",
      kinds.count("ActionUsage") == 2
      and kinds.count("SuccessionAsUsage") == 1, str(kinds))
se = [e for e in act_def.ownedElement
      if type(e).__name__ == "SuccessionAsUsage"][0]
ends_ms = [r for r in se.ownedRelationship
           if type(r).__name__ == "EndFeatureMembership"]
end_targets = [s2.subsettedFeature.declaredName
               for r in ends_ms for x in r.ownedRelatedElement
               for s2 in x.ownedRelationship
               if type(s2).__name__ == "Subsetting"]
check("succession ends wired via end features (7.7.3.3.18)",
      len(ends_ms) == 2
      and end_targets == ["step1", "step2"], str(end_targets))

print()
print("== wave P: transition-succession ends + triggers "
      "(7.7.11.2.19-.26) ==")
# extend the wave-B state machine's idle-to-run transition with a
# change trigger and give the run one a time trigger
tpkg = U.Package(name="TrigPkg")
tsm = U.StateMachine(name="TWatch")
idle = U.State(name="Idle"); run = U.State(name="Run")
reg = U.Region(name="r1"); tsm.region.append(reg)
reg.subvertex.append(idle)
reg.subvertex.append(run)
t1 = U.Transition(name="start"); t1._vals["source"] = idle
t1._vals["target"] = run
ce = U.ChangeEvent()
oe = U.OpaqueExpression()
oe._vals["language"] = "OCL2.0"
oe._vals["body"] = "i == done"
ce._vals["changeExpression"] = oe
tg1 = U.Trigger(name="onDone"); tg1._vals["event"] = ce
t1._vals["trigger"] = [tg1]
reg.transition.append(t1)
t2 = U.Transition(name="tick"); t2._vals["source"] = run
t2._vals["target"] = idle
te = U.TimeEvent(); te._vals["isRelative"] = True
texp = U.TimeExpression()
texp._vals["expr"] = U.OpaqueExpression(language="OCL2.0")
texp._vals.get("expr")._vals["body"] = "3.5s"
te._vals["when"] = texp
tg2 = U.Trigger(); tg2._vals["event"] = te
t2._vals["trigger"] = [tg2]
reg.transition.append(t2)
tpkg.add("packagedElement", tsm)
tout = A.transform_package(tpkg)
tsm_def = tout.ownedElement[0]
states = [e for e in tsm_def.ownedElement
          if type(e).__name__ == "StateUsage"]
by_name = {e.declaredName: e for e in tsm_def.ownedElement
           if type(e).__name__ == "TransitionUsage"}
t1u = by_name.get("start")
suxs = [r for r in t1u.ownedRelationship
        if type(r).__name__ == "Succession"]
end_names = [getattr(x, "declaredName", None)
             for em in suxs[0].ownedRelationship
             for x in em.ownedRelatedElement]
check("transition Succession with named source/target ends "
      "(7.7.11.2.19-.25)",
      len(suxs) == 1 and len(end_names) == 2
      and end_names == ["source", "target"], str(end_names))
checks_out = t1u.ownedRelationship
tfms = [r for r in checks_out if type(r).__name__ == "FeatureMembership"]
carriers = [x for r in tfms for x in r.ownedRelatedElement]
check("change trigger -> ConstraintUsage on the transition (7.7.11.2.26)",
      len(carriers) == 1
      and type(carriers[0]).__name__ == "ConstraintUsage"
      and carriers[0].declaredName == "onDone")
if carriers and type(carriers[0]).__name__ == "ConstraintUsage":
    rels = [type(r).__name__ for r in carriers[0].ownedRelationship]
    inners = [y for r in carriers[0].ownedRelationship
              if type(r).__name__ == "FeatureMembership"
              for y in r.ownedRelatedElement]
    lit = ([z.value for y in inners
            for om in y.ownedRelationship
            if type(om).__name__ == "OwningMembership"
            for z in om.ownedRelatedElement
            if type(z).__name__ == "LiteralString"])
    check("the change expression body carries (7.7.5.3.x core)",
          "ReturnParameterMembership" in rels
          and len(inners) == 1
          and lit == ["i == done"], str(lit))
t2u = by_name.get("tick")
t2tfms = [r for r in t2u.ownedRelationship
          if type(r).__name__ == "FeatureMembership"]
t2carry = [x for r in t2tfms for x in r.ownedRelatedElement]
check("time trigger -> CalculationUsage (7.7.5.3.35)",
      len(t2carry) == 1
      and type(t2carry[0]).__name__ == "CalculationUsage"
      and any(type(r).__name__ == "ReturnParameterMembership"
              for r in t2carry[0].ownedRelationship))

print()
print("== wave C: requirements chain (7.8.8.3.x) ==")
rpkg = U.Package(name="ReqPkg")
power = S.Requirement(name="Power"); power._vals["id"] = "R1"
power._vals["text"] = "system shall provide 10 kW"
veh = S.Block(name="Vehicle")
sat = S.Satisfy(name="sat1"); sat.client.append(veh); sat.supplier.append(power)
rpkg.packagedElement.extend([power, veh, sat])
tc = S.TestCase(name="PowerTest")
verify = S.Verify(name="v1"); verify.client.append(tc); verify.supplier.append(power)
rpkg.packagedElement.extend([tc, verify])
derived = S.Requirement(name="Derived"); derived._vals["id"] = "R2"
dr = S.DeriveReqt(name="d1"); dr.client.append(derived); dr.supplier.append(power)
rpkg.packagedElement.extend([derived, dr])
rout = MT if False else A  # transformer module
rp2 = A.transform_package(rpkg)
kinds = [type(e).__name__ for e in rp2.ownedElement]
check("Requirement->RequirementUsage + TestCase->VerificationCaseDefinition",
      kinds.count("RequirementUsage") == 2
      and kinds.count("VerificationCaseDefinition") == 1, str(kinds))
ru0 = rp2.ownedElement[0]
check("v1 id carried on aliasIds", ru0.aliasIds == ["R1"], str(ru0.aliasIds))
req_docs = [e for e in ru0.ownedElement if type(e).__name__ == "Documentation"]
check("v1 text -> Documentation",
      len(req_docs) == 1 and req_docs[0].body == "system shall provide 10 kW",
      str([d.body for d in req_docs]))
sat_u = [e for e in rp2.ownedElement
         if type(e).__name__ == "SatisfyRequirementUsage"][0]
check("Satisfy ends: satisfyingFeature/satisfiedRequirement",
      sat_u.satisfyingFeature.declaredName == "Vehicle"
      and sat_u.satisfiedRequirement.declaredName == "Power")
tc_def = [e for e in rp2.ownedElement
          if type(e).__name__ == "VerificationCaseDefinition"][0]
rvms = [e for e in tc_def.ownedElement
        if type(e).__name__ == "RequirementVerificationMembership"]
check("Verify -> RequirementVerificationMembership in the TC",
      len(rvms) == 1 and rvms[0].verifiedRequirement.declaredName == "Power")
cu = [e for e in rp2.ownedElement if type(e).__name__ == "ConnectionUsage"]
check("DeriveReqt -> ConnectionUsage with source/target",
      len(cu) == 1 and cu[0].source[0].declaredName == "Derived"
      and cu[0].target[0].declaredName == "Power")
nest = U.Package(name="Nest")
sys_req = S.Requirement(name="System"); sys_req._vals["id"] = "S1"
sub = S.Requirement(name="Sub")
nest.packagedElement.append(sys_req)
sys_req.add("nestedClassifier", sub)
nout = A.transform_package(nest)
sru = nout.ownedElement[0]
check("nested Requirement -> nested RequirementUsage",
      any(type(e).__name__ == "RequirementUsage"
          and e.declaredName == "Sub" for e in sru.ownedElement),
      str([repr(e) for e in sru.ownedElement]))

print()
print("== wave D: To*_Init realization (feature plumbing, ports, ops) ==")
spkg = U.Package(name="SPkg")
base = S.Block(name="Base"); spkg.packagedElement.append(base)
derived = S.Block(name="Derived"); spkg.packagedElement.append(derived)
gg = U.Generalization(); gg.general = base; derived.add("generalization", gg)
p1 = U.Property(name="x"); p1.type = base
p1._vals["aggregation"] = U.AggregationKind.composite
base.add("ownedAttribute", p1)
p2 = U.Property(name="y"); p2.type = base
p2._vals["aggregation"] = U.AggregationKind.composite
p2.subsettedProperty.append(p1)
derived.add("ownedAttribute", p2)
p3 = U.Property(name="z"); p3.type = base
p3._vals["aggregation"] = U.AggregationKind.composite
p3.redefinedProperty.append(p1)
derived.add("ownedAttribute", p3)
sout = A.transform_package(spkg)
d_pd = [e for e in sout.ownedElement if e.declaredName == "Derived"][0]
y_use = [e for e in d_pd.ownedElement if e.declaredName == "y"][0]
z_use = [e for e in d_pd.ownedElement if e.declaredName == "z"][0]
check("subsets -> Subsetting carrier (7.7.4.2.36)",
      any(type(r).__name__ == "Subsetting"
          and r.subsettedFeature.declaredName == "x"
          for r in y_use.ownedRelationship),
      str([type(r).__name__ for r in y_use.ownedRelationship]))
check("redefines -> Redefinition carrier",
      any(type(r).__name__ == "Redefinition"
          and r.redefinedFeature.declaredName == "x"
          for r in z_use.ownedRelationship))

ifpkg = U.Package(name="IfPkg")
ifb = S.InterfaceBlock(name="IF"); ifpkg.packagedElement.append(ifb)
blk = S.Block(name="PSU"); ifpkg.packagedElement.append(blk)
port = U.Port(name="pwr"); port.type = ifb
blk.add("ownedAttribute", port)
sig = U.Signal(name="Cmd"); ifpkg.packagedElement.append(sig)
pp = U.Property(name="lastCmd"); pp.type = sig
blk.add("ownedAttribute", pp)
oout = A.transform_package(ifpkg)
psu = [e for e in oout.ownedElement if e.declaredName == "PSU"][0]
p_use = [e for e in psu.ownedElement if type(e).__name__ == "PortUsage"][0]
check("Port -> PortUsage typed by the interface definition",
      p_use.ownedTyping and p_use.ownedTyping[0].type.declaredName == "PowerIF"
      or p_use.ownedTyping and p_use.ownedTyping[0].type.declaredName == "IF"
      or any(t.type.declaredName == "IF" for t in p_use.ownedTyping))
sig_def = [e for e in oout.ownedElement
           if type(e).__name__ == "ItemDefinition"][0]
check("Signal -> ItemDefinition (7.7.10.2.22)",
      sig_def.declaredName == "Cmd")
lu = [e for e in psu.ownedElement if e.declaredName == "lastCmd"][0]
check("Signal-typed Property -> ItemUsage",
      type(lu).__name__ == "ItemUsage")

opkg = U.Package(name="OpPkg")
dev = S.Block(name="Device"); opkg.packagedElement.append(dev)
op = U.Operation(name="reset"); dev.add("ownedOperation", op)
prm = U.Parameter(name="mode"); op.ownedParameter.append(prm)
opout = A.transform_package(opkg)
d_dev = opout.ownedElement[0]
check("Operation -> PerformActionUsage (7.7.4.2.23)",
      any(type(e).__name__ == "PerformActionUsage"
          for e in d_dev.ownedElement) if (d_dev := opout.ownedElement[0]) else False)

print()
print("== wave E: use cases and interfaces (7.7.13.3.x, 7.8.7.3.16) ==")
upkg = U.Package(name="UCPkg")
checkout = U.UseCase(name="Checkout")
upkg.add("packagedElement", checkout)
car = S.Block(name="Car")
upkg.add("packagedElement", car)
car.add("useCase", checkout)            # subject association (one subject)
ucpkg = A.transform_package(upkg)
ucd = [e for e in ucpkg.ownedElement
       if type(e).__name__ == "UseCaseDefinition"][0]
check("UseCase -> UseCaseDefinition (7.7.13.3.4)", ucd.declaredName == "Checkout")
subj_ms = [r for r in ucd.ownedRelationship
           if type(r).__name__ == "SubjectMembership"]
check("subject -> SubjectMembership with 'subject_' ReferenceUsage",
      len(subj_ms) == 1
      and any(type(x).__name__ == "ReferenceUsage"
              and x.declaredName == "subject_Car"
              and x.ownedTyping and x.ownedTyping[0].type.declaredName == "Car"
              for r in subj_ms for x in r.ownedRelatedElement),
      str([[type(x).__name__ for x in r.ownedRelatedElement] for r in subj_ms]))

subpkg = U.Package(name="IncPkg")
u1 = U.UseCase(name="Outer"); u2 = U.UseCase(name="Inner")
subpkg.packagedElement.extend([u1, u2])
inc = U.Include(name="inc1"); inc.addition = u2; inc.includingCase = u1
subpkg.packagedElement.append(inc)
inc2 = U.Include(); inc2.addition = u1; inc2.includingCase = u2
subpkg.packagedElement.append(inc2)
iout = A.transform_package(subpkg)
u1d = [e for e in iout.ownedElement if e.declaredName == "Outer"][0]
icu = [e for e in u1d.ownedElement if type(e).__name__ == "IncludeUseCaseUsage"]
check("Include -> IncludeUseCaseUsage owned by the including use case",
      any(e.ownedTyping and any(t.type is
          [d for d in iout.ownedElement if d.declaredName == "Inner"][0]
          for t in e.ownedTyping) for e in icu))
u2d = [e for e in iout.ownedElement if e.declaredName == "Inner"][0]
icu2 = [e for e in u2d.ownedElement
        if type(e).__name__ == "IncludeUseCaseUsage"]
check("cross-package Include addition resolved through the index",
      any(any(t.type is u1d for t in e.ownedTyping) for e in icu2))

ifacepkg = U.Package(name="IfacePkg")
ifb2 = S.InterfaceBlock(name="Bus"); ifacepkg.packagedElement.append(ifb2)
host = S.Block(name="Host"); ifacepkg.packagedElement.append(host)
bus_port = U.Port(name="bus"); bus_port.type = ifb2
host.add("ownedAttribute", bus_port)
ref = U.Property(name="busRole"); ref.type = ifb2
host.add("ownedAttribute", ref)
iout2 = A.transform_package(ifacepkg)
bus_def = [e for e in iout2.ownedElement
           if type(e).__name__ == "PortDefinition"][0]
check("InterfaceBlock -> PortDefinition (7.8.7.3.16)", bus_def.declaredName == "Bus")
host_def = [e for e in iout2.ownedElement if e.declaredName == "Host"][0]
port_u = [e for e in host_def.ownedElement
          if type(e).__name__ == "PortUsage"][0]
check("PortUsage typed by the SAME PortDefinition object (identity)",
      any(t.type is bus_def for t in port_u.ownedTyping))
role_u = [e for e in host_def.ownedElement if e.declaredName == "busRole"][0]
check("Property typed by InterfaceBlock -> OccurrenceUsage (7.7.4.2.37)",
      type(role_u).__name__ == "OccurrenceUsage"
      and any(t.type is bus_def for t in role_u.ownedTyping))

extpkg = U.Package(name="ExtendPkg")
e1 = U.UseCase(name="Base"); e2 = U.UseCase(name="Supplemental")
extpkg.packagedElement.extend([e1, e2])
ex = U.Extend(); ex.addition = e2; ex.includingCase = e1
extpkg.packagedElement.append(ex)
eout = A.transform_package(extpkg)
check("Extend/ExtensionPoint not mapped: no AS artifact, no guess "
      "(UseCase_Mapping comment)",
      len(eout.ownedElement) == 2
      and not any(type(x).__name__ == "IncludeUseCaseUsage"
                  for d in eout.ownedElement for x in d.ownedElement))

apkg = U.Package(name="ActorPkg")
drv = U.Actor(name="Driver")
use = U.UseCase(name="Drive")
apkg.packagedElement.extend([drv, use])
ae_uc = U.Property(name="case"); ae_uc.type = use
ae_drv = U.Property(name="who"); ae_drv.type = drv
actor_assoc = U.Association(name="driving")
actor_assoc.add("ownedEnd", ae_uc)
actor_assoc.add("ownedEnd", ae_drv)
actor_assoc.add("memberEnd", ae_uc)
actor_assoc.add("memberEnd", ae_drv)
apkg.packagedElement.append(actor_assoc)
ao = A.transform_package(apkg)
drive_def = [e for e in ao.ownedElement if e.declaredName == "Drive"][0]
am = [r for r in drive_def.ownedRelationship
      if type(r).__name__ == "ActorMembership"]
drv_as = [e for e in ao.ownedElement if e.declaredName == "Driver"][0]
actor_pu = [x for r in am for x in r.ownedRelatedElement]
check("actor association end -> ActorMembership w/ PartUsage typed "
      "by the actor (UseCaseActor_Mapping family)",
      len(am) == 1 and len(actor_pu) == 1
      and type(actor_pu[0]).__name__ == "PartUsage"
      and actor_pu[0].declaredName == "who"
      and any(t.type is drv_as for t in actor_pu[0].ownedTyping),
      str([(type(x).__name__, x.declaredName,
            [t.type.declaredName for t in x.ownedTyping])
           for x in actor_pu]))

print()
print("== wave F: imports (7.7.9.3.12) ==")
# R1 leg: the reader carries PackageImport/ElementImport
XMI_IMP = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1" xmlns:uml="http://schema.omg.org/spec/UML/2.0"
         xmlns:xmi="http://schema.omg.org/spec/XMI/2.1">
  <uml:Package xmi:id="m1" xmi:type="uml:Package">
    <name>M</name>
    <packagedElement xmi:type="uml:Package" xmi:id="p_app">
      <name>App</name>
      <packageImport xmi:type="uml:PackageImport" xmi:id="pi1"
                     visibility="private">
        <importedPackage xmi:idref="p_lib"/>
      </packageImport>
      <packageImport xmi:type="uml:PackageImport" xmi:id="pi2">
        <importedPackage xmi:idref="p_lib"/>
      </packageImport>
      <elementImport xmi:type="uml:ElementImport" xmi:id="ei1"
                     visibility="package" alias="V">
        <importedElement xmi:idref="c_engine"/>
      </elementImport>
      <packagedElement xmi:type="uml:Class" xmi:id="c_root">
        <name>Root</name>
      </packagedElement>
    </packagedElement>
    <packagedElement xmi:type="uml:Package" xmi:id="p_lib">
      <name>Lib</name>
      <packagedElement xmi:type="uml:Class" xmi:id="c_engine">
        <name>Engine</name>
      </packagedElement>
    </packagedElement>
  </uml:Package>
</xmi:XMI>
"""
with tempfile.NamedTemporaryFile("w", suffix=".xmi", delete=False) as fp:
    fp.write(XMI_IMP)
    imp_xmi_path = fp.name
rimp = xmi21.read_xmi21(imp_xmi_path)
app_r1 = [m for m in list(rimp.roots[0].ownedMember)
          if m._vals.get("name") == "App"][0]
pis = list(app_r1._vals.get("packageImport") or [])
eis = list(app_r1._vals.get("elementImport") or [])
check("R1 reader carries packageImport (no unmapped entry)",
      len(pis) == 2
      and ("p_app", "elementImport") not in rimp.unmapped_features)
check("R1 reader carries elementImport with importedElement + alias",
      len(eis) == 1 and eis[0]._vals.get("alias") == "V"
      and eis[0]._vals.get("importedElement") is not None)
imp_model = A.transform_xmi(imp_xmi_path)
outer_pkg2 = imp_model[0]
app_pkg2 = [p for p in outer_pkg2.ownedElement
            if p.declaredName == "App"][0]
lib_pkg2 = [p for p in outer_pkg2.ownedElement
            if p.declaredName == "Lib"][0]


def rel_kinds(ns, kind):
    """Membership children of a namespace of the given AS kind."""
    return [c for om in ns.ownedRelationship
            if isinstance(om, S2.OwningMembership)
            for c in om.ownedRelatedElement
            if type(c).__name__ == kind]


ni = rel_kinds(app_pkg2, "NamespaceImport")
check("PackageImport -> NamespaceImport under the importing package",
      len(ni) == 2 and all(r.importedNamespace is lib_pkg2 for r in ni))
vis = sorted(str(getattr(r._vals.get("visibility"), "name",
                        r._vals.get("visibility"))) for r in ni)
check("visibility mapped (v1 private -> private, absent -> public)",
      vis == ["private", "public"], str(vis))
mi = rel_kinds(app_pkg2, "MembershipImport")
engine_def = [e for e in lib_pkg2.ownedElement
              if e.declaredName == "Engine"][0]
check("ElementImport -> MembershipImport: importedMembership is the "
      "AS OwningMembership of the imported element",
      len(mi) == 1
      and isinstance(mi[0]._vals.get("importedMembership"),
                     S2.OwningMembership)
      and engine_def in mi[0]._vals["importedMembership"]
      .ownedRelatedElement,
      str(mi[0]._vals.get("importedMembership")))
os.unlink(imp_xmi_path)

# honesty: import whose target is outside the transformed scope
far = U.Package(name="Far")
mbr = U.Package(name="Mbr")
mbr.add("packagedElement", U.Class(name="C"))
pi_ext = U.PackageImport()
pi_ext.importedPackage = far
mbr._vals["packageImport"] = [pi_ext]
try:
    A.transform_package(mbr)
    check("UnmappedFeature raised for out-of-scope import", False)
except A.UnmappedFeature as e:
    check("UnmappedFeature raised for out-of-scope import",
          "external/unordered" in str(e), str(e))

print()
print("== wave G: associations (7.7.12.2.x) and multiplicities ==")
apkg = U.Package(name="AsoPkg")
wheel = S.Block(name="Wheel"); axle = S.Block(name="Axle")
apkg.packagedElement.extend([wheel, axle])
assoc = U.Association(name="Mounts")
pe1 = U.Property(name="wheels"); pe1.type = wheel
pe2 = U.Property(name="axle"); pe2.type = axle
assoc.add("ownedEnd", pe1)
assoc.add("ownedEnd", pe2)
assoc.add("memberEnd", pe1)      # real corpora carry memberEnd idrefs
assoc.add("memberEnd", pe2)
apkg.packagedElement.append(assoc)
ac = U.AssociationClass(name="Fastens")
fbe1 = U.Property(name="a"); fbe1.type = wheel
fbe2 = U.Property(name="b"); fbe2.type = axle
ac.add("ownedEnd", fbe1); ac.add("ownedEnd", fbe2)
ac.add("memberEnd", fbe1); ac.add("memberEnd", fbe2)
apkg.packagedElement.append(ac)
aout = A.transform_package(apkg)
conn = [e for e in aout.ownedElement
        if type(e).__name__ == "ConnectionDefinition"][0]
check("Association -> ConnectionDefinition (7.7.12.2.x)",
      conn.declaredName == "Mounts")
def end_usages(c):
    return [x for om in c.ownedRelationship
            if isinstance(om, S2.EndFeatureMembership)
            for x in om.ownedRelatedElement]
ends = end_usages(conn)
check("memberEnd -> end ReferenceUsages in memberEnd order, typed",
      [u.declaredName for u in ends] == ["wheels", "axle"] and all(
          u.ownedTyping and t.type.declaredName in ("Wheel", "Axle")
          for u in ends for t in [u.ownedTyping[0]]),
      str([(u.declaredName, [t.type.declaredName for t in u.ownedTyping])
           for u in ends]))
check("ends are isEnd features (EndFeatureMembership constraint)",
      all(u._vals.get("isEnd") for u in ends))
ab_conn = [e for e in aout.ownedElement if e.declaredName == "Fastens"][0]
check("AssociationClass -> ConnectionDefinition "
      "(AssociationClass_Mapping 'to' = ConnectionDefinition)",
      type(ab_conn).__name__ == "ConnectionDefinition"
      and [u.declaredName for u in end_usages(ab_conn)] == ["a", "b"])

mpkg = U.Package(name="MPkg")
mb = S.Block(name="Box")
optp = U.Property(name="opt"); optp.type = mb
lo0 = U.LiteralInteger(); lo0._vals["value"] = 0
optp._vals["lowerValue"] = lo0
up1 = U.LiteralInteger(); up1._vals["value"] = 1
optp._vals["upperValue"] = up1
manyp = U.Property(name="many"); manyp.type = mb
lo_m = U.LiteralInteger()          # value 0: EMF omits it by default
lo_m._vals["value"] = 0
manyp._vals["lowerValue"] = lo_m
u_star = U.LiteralUnlimitedNatural(); u_star._vals["value"] = \
    U.UnlimitedNatural("*")
manyp._vals["upperValue"] = u_star
plainp = U.Property(name="plain"); plainp.type = mb
mb.add("ownedAttribute", optp)
mb.add("ownedAttribute", manyp)
mb.add("ownedAttribute", plainp)
mpkg.packagedElement.append(mb)
mout = A.transform_package(mpkg)
box = mout.ownedElement[0]


def mult_range(feature):
    """The MultiplicityRange carried under a feature, if any."""
    for fm in feature.ownedRelationship:
        if isinstance(fm, S2.FeatureMembership):
            for x in fm.ownedRelatedElement:
                if type(x).__name__ == "MultiplicityRange":
                    return x
    return None


def bound_val(rng, member_name):
    for om in rng.ownedRelationship:
        if om.memberName == member_name:
            for x in om.ownedRelatedElement:
                if type(x).__name__ in ("LiteralInteger",
                                        "LiteralInfinity"):
                    return x
    return None


opt_u = [e for e in box.ownedElement if e.declaredName == "opt"][0]
rng = mult_range(opt_u)
check("[0..1] -> MultiplicityRange w/ named bound memberships",
      rng is not None and rng.declaredName == "multiplicity"
      and isinstance(bound_val(rng, "lowerBound"), S2.LiteralInteger)
      and bound_val(rng, "lowerBound")._vals.get("value") == 0
      and bound_val(rng, "upperBound")._vals.get("value") == 1,
      str(rng and [(om.memberName,
                    [type(x).__name__ for x in om.ownedRelatedElement])
                   for om in rng.ownedRelationship]
          if rng else None))
many_u = [e for e in box.ownedElement if e.declaredName == "many"][0]
rng2 = mult_range(many_u)
check("[0..*] -> MultiplicityRange with LiteralInfinity upperBound",
      rng2 is not None
      and isinstance(bound_val(rng2, "upperBound"), S2.LiteralInfinity))
plain_u = [e for e in box.ownedElement if e.declaredName == "plain"][0]
check("implicit [1..1] carries no multiplicity (textual-parity)",
      mult_range(plain_u) is None)

pmpkg = U.Package(name="ParamPkg")
pdev = S.Block(name="Dev")
pop = U.Operation(name="read")
pparm = U.Parameter(name="vals")
try:
    pparm._vals["direction"] = U.ParameterDirectionKind("out")
except (ValueError, AttributeError):
    pparm._vals["direction"] = "out"
lo_p = U.LiteralInteger(); lo_p._vals["value"] = 0
pparm._vals["lowerValue"] = lo_p
up_p = U.LiteralUnlimitedNatural(); up_p._vals["value"] = \
    U.UnlimitedNatural(3)
pparm._vals["upperValue"] = up_p
pop.ownedParameter.append(pparm)
pdev.add("ownedOperation", pop)
pmpkg.packagedElement.append(pdev)
pout = A.transform_package(pmpkg)
pdef = pout.ownedElement[0]
pau = [e for e in pdef.ownedElement
       if type(e).__name__ == "PerformActionUsage"][0]
pref = [x for om in pau.ownedRelationship
        if isinstance(om, S2.ParameterMembership)
        for x in om.ownedRelatedElement][0]
check("parameter [0..3] -> MultiplicityRange (7.7.4.2.24 + multiplicity)",
      mult_range(pref) is not None
      and bound_val(mult_range(pref), "lowerBound")._vals.get("value") == 0
      and bound_val(mult_range(pref), "upperBound")._vals.get("value") == 3)

print()
print("== wave H: InformationFlow -> FlowDefinition (7.7.9.x family) ==")
ifpkg = U.Package(name="IFPkg")
s_hot = S.Block(name="HotSide"); s_cold = S.Block(name="ColdSide")
item = U.Signal(name="Cmd")
ifpkg.packagedElement.extend([s_hot, s_cold, item])
src_host = S.Block(name="Sender"); dst_host = S.Block(name="Receiver")
ifpkg.packagedElement.extend([src_host, dst_host])
conn1 = U.Connector(name="bus1")
re1 = U.ConnectorEnd(); re1.role = s_hot
re2 = U.ConnectorEnd(); re2.role = s_cold
conn1.add("end", re1); conn1.add("end", re2)
src_host.add("ownedConnector", conn1)
flow = U.InformationFlow(name="CmdFlow")
flow.add("informationSource", s_hot)   # end elements: NamedElement kinds
flow.add("informationTarget", s_cold)
flow.add("conveyed", item)
flow.add("realizingConnector", conn1)
ifpkg.packagedElement.append(flow)
flow_bare = U.InformationFlow(name="NoReal")
ifpkg.packagedElement.append(flow_bare)
fout = A.transform_package(ifpkg)
fdef = [e for e in fout.ownedElement
        if type(e).__name__ == "FlowDefinition"][0]
check("InformationFlow w/ realizingConnector -> FlowDefinition",
      fdef.declaredName == "CmdFlow")
fl_ends = [x for om in fdef.ownedRelationship
           if isinstance(om, S2.EndFeatureMembership)
           for x in om.ownedRelatedElement]
hot_as = [e for e in fout.ownedElement if e.declaredName == "HotSide"][0]
cold_as = [e for e in fout.ownedElement if e.declaredName == "ColdSide"][0]
check("flow ends: isEnd Features typed by the mapped end elements",
      len(fl_ends) == 2
      and all(x._vals.get("isEnd") for x in fl_ends)
      and [t.type is hot_as for x in fl_ends[:1]
           for t in x.ownedTyping] == [True]
      and [t.type is cold_as for x in fl_ends[1:2]
           for t in x.ownedTyping] == [True],
      str([(x.declaredName, x._vals.get("isEnd"),
            [t.type.declaredName for t in x.ownedTyping])
           for x in fl_ends]))
conv = [x for om in fdef.ownedRelationship
        if isinstance(om, S2.FeatureMembership)
        and not isinstance(om, S2.EndFeatureMembership)
        for x in om.ownedRelatedElement]
cmd_item = [e for e in fout.ownedElement if e.declaredName == "Cmd"][0]
check("conveyed -> carried FeatureMembership member typed by the item",
      len(conv) == 1
      and any(t.type is cmd_item for t in conv[0].ownedTyping))
check("unrealized InformationFlow is not mapped (normative filter)",
      not any(type(e).__name__ == "FlowDefinition"
              and e.declaredName == "NoReal" for e in fout.ownedElement))

print()
print("== wave I: interactions (7.7.8.3.x) ==")
seqpkg = U.Package(name="SeqPkg")
blk_cli = S.Block(name="Client"); blk_srv = S.Block(name="Server")
sig_ping = U.Signal(name="Ping")
seqpkg.packagedElement.extend([blk_cli, blk_srv, sig_ping])
host1 = S.Block(name="H1"); host2 = S.Block(name="H2")
seqpkg.packagedElement.extend([host1, host2])
rep1 = U.Property(name="cli"); rep1.type = blk_cli
rep2 = U.Property(name="srv"); rep2.type = blk_srv
host1.add("ownedAttribute", rep1)
host2.add("ownedAttribute", rep2)
ix = U.Interaction(name="Sequence")
ix2 = U.Interaction(name="SubSequence")
seqpkg.packagedElement.extend([ix, ix2])
ll1 = U.Lifeline(name="ll_cli"); ll1.represents = rep1
ll2 = U.Lifeline(name="ll_srv"); ll2.represents = rep2
msg = U.Message(name="ping"); msg.signature = sig_ping
si = U.StateInvariant(name="si")
si._vals["invariant"] = [sig_ping]
iu = U.InteractionUse(name="useSub"); iu.refersTo = ix2
exec1 = U.ActionExecutionSpecification(name="exec1")
op = U.InteractionOperand(name="op")
cf = U.CombinedFragment(name="cf")
seq = U.OccurrenceSpecification(name="tick")
cf.add("operand", op)
ix.add("lifeline", ll1)
ix.add("lifeline", ll2)
ix.add("message", msg)
ix.add("fragment", si)
ix.add("fragment", iu)
ix.add("fragment", exec1)
ix.add("fragment", cf)
ix.add("fragment", seq)
iout = A.transform_package(seqpkg)
ix_def = [e for e in iout.ownedElement
          if type(e).__name__ == "Interaction"][0]
check("Interaction -> Interaction (7.7.8.3.6)", ix_def.declaredName == "Sequence")
def mem_children(ns, cls=None, kind="FeatureMembership"):
    return [x for om in ns.ownedRelationship
            if type(om).__name__ == kind
            for x in om.ownedRelatedElement
            if cls is None or type(x).__name__ == cls]
cli_as = [e for e in iout.ownedElement if e.declaredName == "Client"][0]
srv_as = [e for e in iout.ownedElement if e.declaredName == "Server"][0]
parts = mem_children(ix_def, cls="PartUsage")
check("lifelines -> PartUsages via FeatureMembership, typed by "
      "represents.type's definition (7.7.8.3.13/.14)",
      len(parts) == 2
      and any(any(t.type is cli_as for t in p.ownedTyping) for p in parts)
      and any(any(t.type is srv_as for t in p.ownedTyping) for p in parts),
      str([(p.declaredName, [t.type.declaredName for t in p.ownedTyping])
           for p in parts]))
flows = mem_children(ix_def, cls="Flow")
check("Message -> Flow via FeatureMembership (7.7.8.3.15/.16)",
      len(flows) == 1 and flows[0].declaredName == "ping")
ping_item = [e for e in iout.ownedElement if e.declaredName == "Ping"][0]
inv = mem_children(ix_def, cls="Invariant")
check("StateInvariant -> Invariant typed by the invariant ref "
      "(7.7.8.3.17/.19)",
      len(inv) == 1
      and any(t.type is ping_item for t in inv[0].ownedTyping))
sub_def = [e for e in iout.ownedElement
           if type(e).__name__ == "Interaction"
           and e.declaredName == "SubSequence"][0]
steps = mem_children(ix_def, cls="Step")
check("InteractionUse -> Step typed by the refersTo interaction "
      "(7.7.8.3.9/.11)",
      len(steps) == 1
      and any(t.type is sub_def for t in steps[0].ownedTyping))
execs = [x for om in ix_def.ownedRelationship
         if isinstance(om, S2.EndFeatureMembership)
         for x in om.ownedRelatedElement]
check("ActionExecutionSpecification -> ActionUsage via "
      "EndFeatureMembership (7.7.8.3.1/.5)",
      len(execs) == 1 and execs[0].declaredName == "exec1")
cfx = mem_children(ix_def, cls="Interaction", kind="OwningMembership")
op_int = [x for om in cfx[0].ownedRelationship
          if isinstance(om, S2.OwningMembership)
          for x in om.ownedRelatedElement
          if type(x).__name__ == "Interaction"]
check("CombinedFragment -> nested Interaction (7.7.8.3.3) with the "
      "operand as a nested Interaction (7.7.8.3.7/.8)",
      len(cfx) == 1 and cfx[0].declaredName == "cf"
      and len(op_int) == 1 and op_int[0].declaredName == "op")
check("plain OccurrenceSpecifications not mapped (7.7.8.2 Table 11)",
      not any(type(x).__name__ in ("ActionUsage", "Feature")
              and x.declaredName == "tick"
              for x in mem_children(ix_def)))

print()
print("== wave J: conjugation machinery (7.8.7.3.3/.17/.20, 7.7.10.2.14) ==")
jpkg = U.Package(name="CjgPkg")
jib = S.InterfaceBlock(name="Bus")
jpkg.packagedElement.append(jib)
jif = U.Interface(name="MyIf")
jsig = U.Signal(name="Sig2")
seqpkg = None  # (wave-I scope does not leak into wave J)
jpkg.packagedElement.append(jsig)
jattr = U.Property(name="sig"); jattr.type = jsig
jif.add("ownedAttribute", jattr)
jpkg.packagedElement.append(jif)
jf = U.Port(name="bus"); jf.type = jib
jf._vals["isConjugated"] = True
jhost = S.Block(name="Host2")
jhost.add("ownedAttribute", jf)
jpkg.packagedElement.append(jhost)
jout = A.transform_package(jpkg)
ibus = [e for e in jout.ownedElement
        if type(e).__name__ == "PortDefinition"
        and e.declaredName == "Bus"][0]
conjs = [x for om in ibus.ownedRelationship
         if isinstance(om, S2.OwningMembership)
         for x in om.ownedRelatedElement
         if type(x).__name__ == "ConjugatedPortDefinition"]
check("InterfaceBlock -> PortDefinition + owned ConjugatedPortDefinition",
      len(conjs) == 1 and conjs[0].declaredName is None)
pcs = [r for r in conjs[0].ownedRelationship
       if type(r).__name__ == "PortConjugation"]
check("PortConjugation inside: originalPortDefinition = the interface def",
      len(pcs) == 1
      and pcs[0].originalPortDefinition is ibus)
myif = [e for e in jout.ownedElement
        if type(e).__name__ == "PortDefinition"
        and e.declaredName == "MyIf"][0]
iconjs = [x for om in myif.ownedRelationship
          if isinstance(om, S2.OwningMembership)
          for x in om.ownedRelatedElement
          if type(x).__name__ == "ConjugatedPortDefinition"]
check("Interface -> PortDefinition + '~'-named conjugated member "
      "(7.7.10.2.14/.15)",
      len(iconjs) == 1 and iconjs[0].declaredName == "~MyIf")
ipc = [r for r in iconjs[0].ownedRelationship
       if type(r).__name__ == "PortConjugation"]
check("InterfacePortConjugation ties original to conjugated",
      len(ipc) == 1 and ipc[0].originalPortDefinition is myif)
iface_attr = [x for x in myif.ownedElement if x.declaredName == "sig"][0]
check("Interface ownedAttribute -> feature carried by the classifier "
      "machinery (Signal-typed -> ItemUsage, 7.7.10.2.22)",
      type(iface_attr).__name__ == "ItemUsage")
host2_def = [e for e in jout.ownedElement if e.declaredName == "Host2"][0]
port_use = [x for x in host2_def.ownedElement
            if type(x).__name__ == "PortUsage"][0]
check("isConjugated port still plainly typed (ToConjugatedPortTyping "
      "is a stub initializer; no mapping rule triggers it)",
      any(t.type is ibus for t in port_use.ownedTyping))

print()
print("== wave K: FullPort -> PartUsage + PortData metadata (7.8.7.3.7-.15) ==")
kpkg = U.Package(name="FPkg")
kib = S.InterfaceBlock(name="Pwr")
kpkg.packagedElement.append(kib)
khost = S.Block(name="Dev")
full2 = S.FullPort(name="fp"); full2.type = kib
khost.add("ownedAttribute", full2)
full_un = S.FullPort(name="fpu")
khost.add("ownedAttribute", full_un)
prxy = S.ProxyPort(name="pp")
khost.add("ownedAttribute", prxy)
kpkg.packagedElement.append(khost)
kout = A.transform_package(kpkg)
kdev = [e for e in kout.ownedElement if e.declaredName == "Dev"][0]
fp_u = [e for e in kdev.ownedElement if e.declaredName == "fp"][0]
kibus = [e for e in kout.ownedElement if e.declaredName == "Pwr"][0]
check("FullPort -> PartUsage typed by the interface's PortDefinition "
      "(7.8.7.3.7)",
      type(fp_u).__name__ == "PartUsage"
      and any(t.type is kibus for t in fp_u.ownedTyping))


def meta_of(usage):
    """The PortData MetadataUsage chain: OwningMembership ->
    MetadataUsage -> FeatureMembership -> ReferenceUsage."""
    for om in usage.ownedRelationship:
        if not isinstance(om, S2.OwningMembership):
            continue
        for el in om.ownedRelatedElement:
            if type(el).__name__ == "MetadataUsage":
                return el
    return None


mu2 = meta_of(fp_u)
refs = [x for om in mu2.ownedRelationship
        if isinstance(om, S2.FeatureMembership)
        for x in om.ownedRelatedElement]
lit2 = [x for om in mu2.ownedRelationship
        if isinstance(om, S2.FeatureMembership)
        for x in om.ownedRelatedElement
        for r in x.ownedRelationship
        for y in r.ownedRelatedElement]
check("PortData metadata: MetadataUsage -> ReferenceUsage 'isFullPort'"
      " -> FeatureValue = true (7.8.7.3.8-.13)",
      mu2 is not None and len(refs) == 1
      and refs[0].declaredName == "isFullPort"
      and ((vals := refs[0].ownedRelationship) and len(vals) == 1
           and type(vals[0]).__name__ == "FeatureValue"
           and type(y := vals[0].ownedRelatedElement[0]).__name__
           == "LiteralBoolean" and y._vals.get("value") is True),
      str(mu2 and [(type(r).__name__, [t.declaredName for t in r.ownedRelatedElement])
                   for r in mu2.ownedRelationship]))
fp_un_u = [e for e in kdev.ownedElement if e.declaredName == "fpu"][0]
check("untyped FullPort -> untyped PartUsage with the same metadata "
      "(7.8.7.3.15)",
      type(fp_un_u).__name__ == "PartUsage"
      and not fp_un_u.ownedTyping and meta_of(fp_un_u) is not None)
pp_u = [e for e in kdev.ownedElement if e.declaredName == "pp"][0]
check("ProxyPort -> base Port mapping -> bare PortUsage (Table 30: no "
      "target)",
      type(pp_u).__name__ == "PortUsage" and meta_of(pp_u) is None)

print()
print("== wave M: activity pins + object-flow end/payload machinery "
      "(7.7.2.3.2.5, 7.7.3.3.47-.63) ==")
mpkg2 = U.Package(name="ActEndPkg")
wa = U.DataType(name="Water")
mpkg2.packagedElement.append(wa)
pact = U.Activity(name="Pump")
make = U.OpaqueAction(name="make")
p_out = U.OutputPin(name="tap"); p_out.type = wa
make.add("output", p_out)
consume = U.OpaqueAction(name="consume")
p_in = U.InputPin(name="mouth"); p_in.type = wa
consume.add("input", p_in)
vp = U.ValuePin(name="quota"); vp.type = wa
vspec = U.OpaqueExpression(language="OCL2.0")
vspec._vals["body"] = "42"
vp._vals["value"] = vspec
consume.add("input", vp)          # not value... a ValuePin carries 'value'
objf = U.ObjectFlow(name="stream")
objf.source = p_out
objf.target = p_in
pact.node.append(make)
pact.node.append(consume)
pact.edge.append(objf)
mpkg2.packagedElement.append(pact)
mout = A.transform_package(mpkg2)
pact_def = [e for e in mout.ownedElement
            if type(e).__name__ == "ActionDefinition"][0]
make_u = [e for e in pact_def.ownedElement if e.declaredName == "make"][0]
consume_u = [e for e in pact_def.ownedElement
             if e.declaredName == "consume"][0]
mk_refs = {x.declaredName: x for om in make_u.ownedRelationship
           if isinstance(om, S2.FeatureMembership)
           for x in om.ownedRelatedElement}
check("OutputPin -> 'out' ReferenceUsage typed by the pin's type "
      "(7.7.2.3.2.5 example form)",
      "tap" in mk_refs and mk_refs["tap"].direction == "out"
      and any(t.type.declaredName == "Water"
              for t in mk_refs["tap"].ownedTyping),
      str(sorted(k for k in mk_refs)))
stream = [e for e in pact_def.ownedElement
          if type(e).__name__ == "SuccessionFlowUsage"][0]
end_fs = [x for r in stream.ownedRelationship
          if isinstance(r, S2.EndFeatureMembership)
          for x in r.ownedRelatedElement]
check("ObjectFlow ends -> isEnd FlowEnds chained, subsetted by the "
      "mapped pin refs (7.7.3.3.58/.59/.63)",
      len(end_fs) == 2
      and all(x._vals.get("isEnd") for x in end_fs)
      and [e for e in stream.source] == [end_fs[0]]
      and [e for e in stream.target] == [end_fs[1]]
      and all(isinstance(r, S2.Subsetting)
              and (r.subsettedFeature is not None)
              and r.subsettedFeature.declaredName in ("tap", "mouth")
              for x in end_fs for r in x.ownedRelationship
              if isinstance(r, S2.Subsetting)))
end_ref = [y for x in end_fs for sm2 in x.ownedRelationship
           if isinstance(sm2, S2.FeatureMembership)
           for y in sm2.ownedRelatedElement]
check("each FlowEnd carries its reference-usage layer (.3.61/.60/.62)",
      len(end_ref) == 2
      and all(isinstance(y, S2.ReferenceUsage) for y in end_ref)
      and end_ref[0].declaredName == "tap"
      and end_ref[1].declaredName == "mouth")
payloads = [x for r in stream.ownedRelationship
            if isinstance(r, S2.FeatureMembership)
            for x in r.ownedRelatedElement
            if type(x).__name__ == "PayloadFeature"]
wa_as = [e for e in mout.ownedElement if e.declaredName == "Water"][0]
check("ObjectNode type -> PayloadFeature typing (7.7.3.3.54/.56)",
      len(payloads) == 1
      and any(t.type is wa_as for t in payloads[0].ownedTyping))

print()
print("== wave N: opaque bodies + activity-edge guards "
      "(7.7.2.3.2.3, 7.7.14.3.18, 7.7.3.3.20/.50) ==")
npkg = U.Package(name="BodyPkg")
wat = U.DataType(name="Water")
npkg.add("packagedElement", wat)
nact = U.Activity(name="Ops")
na = U.OpaqueAction(name="step")
na._vals["language"] = "Python"
na._vals["body"] = "x = x + 1"
nact.node.append(na)
ng = U.OpaqueExpression()
ng._vals["language"] = "OCL2.0"
ng._vals["body"] = "c > 10"
cfl = U.ControlFlow(name="cf2")
cfl._vals["guard"] = [ng]
na2 = U.OpaqueAction(name="after")
nact.node.append(na2)
cfl.source = na
cfl.target = na2
nact.edge.append(cfl)
ng2 = U.OpaqueExpression()
ng2._vals["language"] = "OCL2.0"
ng2._vals["body"] = "ready"
p_out2 = U.OutputPin(name="t2")
p_out2.type = wat
na.add("output", p_out2)
ofl = U.ObjectFlow(name="of2")
ofl._vals["guard"] = [ng2]
ofl.source = p_out2
ofl.target = na2
nact.edge.append(ofl)
ofl2 = U.ObjectFlow(name="of3")
ofl2.source = p_out2
ofl2.target = na2
nact.edge.append(ofl2)
npkg.packagedElement.append(nact)
nout = A.transform_package(npkg)
ndef = [e for e in nout.ownedElement if e.declaredName == "Ops"][0]

def reprs_of(el):
    return [x for om in el.ownedRelationship
            if isinstance(om, S2.OwningMembership)
            for x in om.ownedRelatedElement
            if type(x).__name__ == "TextualRepresentation"]


step_u = [e for e in ndef.ownedElement if e.declaredName == "step"][0]
step_reprs = reprs_of(step_u)
check("OpaqueAction language/body -> TextualRepresentation (7.7.2.3.2.3)",
      len(step_reprs) == 1
      and step_reprs[0].language and step_reprs[0].language[0] == "Python"
      and step_reprs[0].body and step_reprs[0].body[0] == "x = x + 1")
# the guarded control flow's activity carries ONLY the transition
# (the .18 succession rides inside it - no bare succession for cf2)
bare_se = [e for e in ndef.ownedElement
           if type(e).__name__ == "SuccessionAsUsage"
           and e.declaredName == "cf2"]
cf_tu = [e for e in ndef.ownedElement
         if type(e).__name__ == "TransitionUsage"
         and e.declaredName == "cf2"][0]
g_ms = [r for r in cf_tu.ownedRelationship
        if type(r).__name__ == "TransitionFeatureMembership"]
chain_u = [x for r in g_ms for x in r.ownedRelatedElement]
check("guarded ControlFlow -> TransitionUsage w/ AsValue chain "
      "(7.7.3.3.20, 7.7.14.3.17)",
      len(g_ms) == 1 and str(g_ms[0].kind) == "TransitionFeatureKind.guard"
      and len(chain_u) == 1
      and type(chain_u[0]).__name__ == "FeatureChainExpression"
      and not bare_se)
in_ms = [r for r in cf_tu.ownedRelationship
         if type(r).__name__ == "ParameterMembership"]
in_ref = [x for r in in_ms for x in r.ownedRelatedElement]
check("the cf transition's in-ParameterMembership (7.6.2.3/.5)",
      len(in_ms) == 1
      and in_ref and getattr(in_ref[0], "direction", None) == "in")
src_ms = [r for r in cf_tu.ownedRelationship
          if type(r).__name__ == "Membership"]
check("the .15 source Membership", len(src_ms) == 1
      and src_ms[0].memberElement is not None)
if chain_u:
    ch_rels = [type(r).__name__ for r in chain_u[0].ownedRelationship]
    check("the AsValue chain carries in-param + out-return (7.7.14.3.17)",
          ch_rels.count("ParameterMembership") == 1
          and ch_rels.count("ReturnParameterMembership") == 1, str(ch_rels))
inner_se = [r for r in cf_tu.ownedRelationship
            if type(r).__name__ == "SuccessionAsUsage"]
calc_u = []
if inner_se:
    calc_u = [x for r in inner_se[0].ownedRelationship
              if type(r).__name__ == "FeatureMembership"
              for x in r.ownedRelatedElement
              if type(x).__name__ == "CalculationUsage"]
check("the .18 succession inside the transition carries the guard's "
      "calculation (7.7.14.3.18)",
      len(inner_se) == 1 and len(calc_u) == 1)
if calc_u:
    ret_ms = [r for r in calc_u[0].ownedRelationship
              if type(r).__name__ == "ReturnParameterMembership"]
    calc_reprs = reprs_of(calc_u[0])
    ret_ref = [x for r in ret_ms for x in r.ownedRelatedElement]
    check("guard calc: return 'result' (out) + language/body "
          "(7.7.14.3.18 example)",
          len(ret_ms) == 1
          and ret_ref and ret_ref[0].direction == "out"
          and ret_ref[0].declaredName == "result"
          and len(calc_reprs) == 1
          and calc_reprs[0].language[0] == "OCL2.0"
          and calc_reprs[0].body[0] == "c > 10")
    check("the inner succession's target end subsets the target "
          "(7.7.3.3.18)",
          any(type(s2).__name__ == "Subsetting"
              and getattr(s2, "subsettedFeature", None) is not None
              and s2.subsettedFeature.declaredName == "after"
              for em in inner_se[0].ownedRelationship
              if type(em).__name__ == "EndFeatureMembership"
              for x in em.ownedRelatedElement
              for s2 in x.ownedRelationship
              if type(s2).__name__ == "Subsetting"))
of_flows = [e for e in ndef.ownedElement
            if type(e).__name__ == "SuccessionFlowUsage"]
of_tus = [e for e in ndef.ownedElement
          if type(e).__name__ == "TransitionUsage"
          and e.declaredName == "of2"]
of_tu = of_tus[0] if of_tus else None
of_in_se = ([r for r in of_tu.ownedRelationship
             if type(r).__name__ == "SuccessionAsUsage"]
            if of_tu else [])
subsets_flow = any(
    getattr(s2, "subsettedFeature", None) is of_flows[0]
    for ise in of_in_se for em in ise.ownedRelationship
    if type(em).__name__ == "EndFeatureMembership"
    for x in em.ownedRelatedElement
    for s2 in x.ownedRelationship
    if type(s2).__name__ == "Subsetting")
of_in_ms = ([r for r in of_tu.ownedRelationship
             if type(r).__name__ == "ParameterMembership"] if of_tu else [])
of_in_ref = [x for r in of_in_ms for x in r.ownedRelatedElement]
check("guarded ObjectFlow keeps the flow AND the guard transition "
      "whose succession end subsets the flow (.3.51-.53); the "
      "unguarded of3 stays a plain flow; the in-param is typed by the "
      "source's type (7.6.2.5)",
      len(of_flows) == 2 and len(of_tus) == 1 and subsets_flow
      and (of_in_se and of_in_se[0].declaredName == "of2")
      and any(getattr(getattr(ft, "type", None), "declaredName", None)
              == "Water" for ft in of_in_ref[0].ownedTyping))

print()
print("== honesty: unmapped features refuse to guess ==")
orphan = U.Package(name="Orphan")
orphan.add("packagedElement", U.Continuation(name="CX"))
try:
    A.transform_package(orphan)
    check("UnmappedFeature raised for Continuation", False)
except A.UnmappedFeature as e:
    check("UnmappedFeature raised for Continuation",
          "Continuation" in str(e), str(e))
ext = U.Package(name="Ext")
blk = S.Block(name="B"); ext.add("packagedElement", blk)
other = S.Block(name="Elsewhere")
p2 = U.Property(name="x"); p2.type = other
blk.add("ownedAttribute", p2)
try:
    A.transform_package(ext)
    check("UnmappedFeature raised for external type", False)
except A.UnmappedFeature as e:
    check("UnmappedFeature raised for external type",
          "external" in str(e), str(e))
gen_unnamed = U.Package(name="GU")
b1 = S.Block(name="B1"); gen_unnamed.add("packagedElement", b1)
anon = U.Class()
g2 = U.Generalization(); g2.general = anon
b1.add("generalization", g2)
try:
    A.transform_package(gen_unnamed)
    check("UnmappedFeature raised for unnamed general", False)
except A.UnmappedFeature as e:
    check("UnmappedFeature raised for unnamed general",
          "external/unnamed" in str(e), str(e))

print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
