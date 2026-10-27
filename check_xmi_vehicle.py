#!/usr/bin/env python
"""E3: synthetic SysML v1 XMI for the VehicleExample model -- the full
R1 -> R3 -> R2 chain from a file on disk.

check_v1_to_v2.py builds the wave-1 v1 model as gen.uml25/gen.sysml objects
in code; this script instead:

  1. builds the SAME model in faithful file form -- plain UML base elements
     (uml:Class for blocks, uml:DataType for the value type, uml:Connector
     for the binding connector, uml:Abstraction for verify/derive/refine/
     allocate, uml:Behavior for the test case) plus root-level
     <sysml:Block base_Class=...> profile application elements, with the
     Requirement id/text carried as stereotype tagged values;
  2. serializes it with xmi_write.py (EMF-dialect XMI 2.1) ->
     vehicle_example.xmi;
  3. reads it back with xmi21.py (the R1 reader), rehydrates applied
     stereotypes into gen.sysml classes and tagged values into features;
  4. runs the R3 transformer (v1_to_v2.emit_v2) and checks the emitted
     SysML v2 is byte-identical to vehicle_example_v2.sysml and parses
     with sysmlpy (the R2 reader).

Reader tables exercised (and required) beyond the DoDAF/Measurements
corpora: Parameter/Abstraction/Behavior/Actor/StateMachine/Region/State/
Transition/Activity/UseCase/Include in CONSTRUCTIBLE; end/include in
COMPOSITE; role/source/target/addition in REF_SINGLE; enum-typed text
children (aggregation, direction). See xmi21.py.

Run under ~/Projects/sysmlpy/.venv (needs sysmlpy + pint + lxml).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import umlmeta.uml25 as U       # noqa: E402
import umlmeta.sysml as S       # noqa: E402
import umlmeta.v1_to_v2 as M    # noqa: E402
import umlmeta.xmi21 as xmi21   # noqa: E402
import umlmeta.xmi_write as XW  # noqa: E402

HERE = Path(__file__).resolve().parent
XMI_OUT = HERE / "vehicle_example.xmi"
REFERENCE = HERE / "vehicle_example_v2.sysml"
FROM_XMI = HERE / "vehicle_example_from_xmi.sysml"

SYSML_NS = "http://www.omg.org/spec/SysML/20181001"
PROFILE_HREF = SYSML_NS + "/SysML.xmi#SysML"
NSMAP = {"xmi": XW.XMI_NS, "uml": XW.UML_NS_DEFAULT, "sysml": SYSML_NS}

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}"
          + (f"  [{detail}]" if detail else ""))


# stereotype short-name -> gen.sysml class (for rehydration after reread)
STEREO_CLS = {c._STEREO.split("::")[-1]: c for c in vars(S).values()
              if isinstance(c, type) and getattr(c, "_STEREO", None)}

APPS = []


def apply_stereo(stereo, obj, tags=None):
    """Record a SysML v1 profile application: root-level element
    <sysml:<stereo> base_<Meta>=<obj's id>>, tags as 2.1 text children."""
    nm = getattr(obj, "name", None) or "anon"
    APPS.append(("sysml", stereo, obj, f"app-{stereo}-{nm}", None, tags))


# ---- build the v1 model (faithful file form: pure UML bases + apps) -------
V = U.Package(name="VehicleExample")

wheel = U.Class(name="Wheel");       apply_stereo("Block", wheel)
vehicle = U.Class(name="Vehicle");   apply_stereo("Block", vehicle)
car = U.Class(name="Car");           apply_stereo("Block", car)
axle = U.Class(name="Axle");         apply_stereo("Block", axle)

mass = U.DataType(name="Kilogram");  apply_stereo("ValueType", mass)
color = U.Enumeration(name="VehicleColor")
for lit in ("red", "green", "blue"):
    color.ownedLiteral.append(U.EnumerationLiteral(name=lit))

# parts / attributes on Vehicle
wheels = U.Property(name="wheels")
wheels.type = wheel
wheels.aggregation = U.AggregationKind.composite
uv = U.LiteralUnlimitedNatural()
uv.value = U.UnlimitedNatural("4")
wheels.upperValue = uv
vehicle.add("ownedAttribute", wheels)

mass_attr = U.Property(name="mass")
mass_attr.type = mass
vehicle.add("ownedAttribute", mass_attr)

paint = U.Property(name="paint")
paint.type = color
vehicle.add("ownedAttribute", paint)

# ports: InterfaceBlock + typed/untyped Ports
power_if = U.Class(name="PowerIf");  apply_stereo("InterfaceBlock", power_if)
pwr = U.Port(name="pwr")
pwr.type = power_if
vehicle.add("ownedAttribute", pwr)
free_port = U.Port(name="aux")
vehicle.add("ownedAttribute", free_port)

# connector between parts (normative: Connector -> ConnectionUsage)
p1 = U.Property(name="frontAxle")
p1.type = axle
p1.aggregation = U.AggregationKind.composite
p2 = U.Property(name="rearAxle")
p2.type = axle
p2.aggregation = U.AggregationKind.composite
vehicle.add("ownedAttribute", p1)
vehicle.add("ownedAttribute", p2)
conn = U.Connector(name="axleLink")
cend1 = U.ConnectorEnd(); cend1.role = p1
cend2 = U.ConnectorEnd(); cend2.role = p2
conn.add("end", cend1)
conn.add("end", cend2)
vehicle.add("ownedConnector", conn)

# binding connector (SysML stereotype of UML Connector)
raw_a = U.Property(name="rawA")
raw_a.type = mass
raw_b = U.Property(name="rawB")
raw_b.type = mass
vehicle.add("ownedAttribute", raw_a)
vehicle.add("ownedAttribute", raw_b)
binding = U.Connector(name="massBind")
apply_stereo("BindingConnector", binding)
bend1 = U.ConnectorEnd(); bend1.role = raw_a
bend2 = U.ConnectorEnd(); bend2.role = raw_b
binding.add("end", bend1)
binding.add("end", bend2)
vehicle.add("ownedConnector", binding)

# operation with parameters (normative: Operation -> PerformActionUsage)
op = U.Operation(name="totalMass")
par_in = U.Parameter(name="extra"); par_in.direction = U.ParameterDirectionKind.in_
par_in.type = mass
par_out = U.Parameter(name="result"); par_out.direction = U.ParameterDirectionKind.return_
op.add("ownedParameter", par_in)
op.add("ownedParameter", par_out)
vehicle.add("ownedOperation", op)

# association (normative: -> ConnectionDefinition with ends)
assoc = U.Association(name="WheelToAxle")
e1 = U.Property(name="wheelEnd"); e1.type = wheel
e2 = U.Property(name="axleEnd"); e2.type = axle
assoc.add("ownedEnd", e1)
assoc.add("ownedEnd", e2)
assoc.memberEnd = [e1, e2]

# actor (normative: Actor -> PartDefinition)
actor = U.Actor(name="Operator")

# signal + item-typed property (normative: Signal -> ItemDefinition)
cmd = U.Signal(name="MoveCommand")

# plain class + occurrence-typed property (OccurrenceDefinition/Usage)
legacy = U.Class(name="LegacyPart")
occ_ref = U.Property(name="legacy")
occ_ref.type = legacy
vehicle.add("ownedAttribute", occ_ref)

# state machine w/ 2 states, transition
sm = U.StateMachine(name="OpMode")
reg = U.Region(name="r1")
st_on = U.State(name="on")
st_off = U.State(name="off")
trans = U.Transition(name="t1")
reg.add("subvertex", st_on)
reg.add("subvertex", st_off)
trans.source = st_on
trans.target = st_off
reg.add("transition", trans)
sm.add("region", reg)

# activity (normative: Activity -> ActionDefinition w/ parameters)
act = U.Activity(name="Generate")
ap = U.Parameter(name="demand")
ap.direction = U.ParameterDirectionKind.in_
act.add("ownedParameter", ap)

# test case + verify (normative: TestCase -> verification def, Verify ->
# RequirementVerificationMembership inside its objective). TestCase is a
# stereotype of Behavior or Operation; uml:Activity is the concrete,
# packageable Behavior base a real tool would serialize.
tc = U.Activity(name="CheckMass");     apply_stereo("TestCase", tc)
req = U.Class(name="CarIsVehicle")
apply_stereo("Requirement", req,
             {"id": "R-1",
              "text": "A car shall be a specialization of vehicle."})
ver = U.Abstraction(name="verifyCar"); apply_stereo("Verify", ver)
ver.client = [tc]
ver.supplier = [req]

# derived requirement (normative: DeriveReqt -> Derivation connection)
derived_req = U.Class(name="DerivedReq")
apply_stereo("Requirement", derived_req)
dr = U.Abstraction(name="derives");    apply_stereo("DeriveReqt", dr)
dr.client = [derived_req]
dr.supplier = [req]

# refine (normative: Refine -> annotated Dependency)
refined = U.Dependency(name="refinesVeh")
refined.client = [vehicle]
refined.supplier = [req]
refine = U.Abstraction(name="refineTag"); apply_stereo("Refine", refine)
refine.client = [vehicle]
refine.supplier = [req]

# plain dependency
dep = U.Dependency(name="usesLegacy")
dep.client = [vehicle]
dep.supplier = [legacy]

# allocation between part usages (normative: AllocationUsage)
alloc_target = U.Property(name="spareWheel")
alloc_target.type = wheel
car.add("ownedAttribute", alloc_target)
alloc = U.Abstraction(name="allocWheel"); apply_stereo("Allocate", alloc)
alloc.client = [wheels]
alloc.supplier = [alloc_target]

# use case with include
uc_main = U.UseCase(name="OperateVehicle")
uc_sub = U.UseCase(name="StartEngine")
inc = U.Include()
inc.addition = uc_sub
uc_main.add("include", inc)

# package import (elided: target grammar has no import)
P_q = U.Package(name="Common")
pimport = U.PackageImport()
pimport.importedPackage = P_q
V.add("packageImport", pimport)

for el in (P_q, wheel, vehicle, axle, mass, color, power_if, legacy, cmd,
           actor, sm, act, uc_main, uc_sub, car, req, derived_req,
           assoc, tc, ver, dr, refine, refined, dep, alloc, pimport):
    V.add("packagedElement", el)

# ---- write the synthetic XMI ------------------------------------------------
print("== write synthetic SysML v1 XMI ==")
data = XW.write_xmi([V], apps=APPS, nsmap=NSMAP,
                    profile_applications=(PROFILE_HREF,))
data2 = XW.write_xmi([V], apps=APPS, nsmap=NSMAP,
                     profile_applications=(PROFILE_HREF,))
check("write is deterministic (byte-identical)", data == data2)
XMI_OUT.write_bytes(data)
check("vehicle_example.xmi written", XMI_OUT.exists() and len(data) > 1000,
      f"{len(data)} bytes")

# ---- R1: read it back --------------------------------------------------------
print("== R1: xmi21 read of vehicle_example.xmi ==")
m = xmi21.read_xmi21(XMI_OUT)
check("one uml:Package root (VehicleExample)",
      len(m.roots) == 1 and m.roots[0].name == "VehicleExample")
check("no unmapped metaclass tags", not m.unmapped, str(m.unmapped[:3]))
check("no unmapped features", not m.unmapped_features,
      str(m.unmapped_features[:3]))
check("no unresolved refs", not m.unresolved_refs,
      str(m.unresolved_refs[:3]))
check("14 stereotype applications read back",
      sum(len(v) for v in m.apps.values()) == 14,
      str(sum(len(v) for v in m.apps.values())))
check("profile application recorded", m.profiles == [PROFILE_HREF],
      str(m.profiles))
check("Requirement tagged values survived (id R-1 + text)",
      any(t.get("id") == "R-1" for t in m.app_tags.values()),
      str(m.app_tags))

# ---- rehydrate stereotypes (-> gen.sysml classes) + tagged values -----------
print("== rehydrate applied stereotypes ==")
retyped = 0
for i, o in m.objects.items():
    for profile, stereo, app_id in getattr(o, "_applied_stereotypes", []):
        cls = STEREO_CLS.get(stereo)
        if cls is None:
            continue
        o.__class__ = cls
        retyped += 1
        for k, v in (m.app_tags.get(app_id) or {}).items():
            o._vals[k] = v
    if hasattr(o, "_applied_stereotypes"):
        # rehydration consumes the annotation: the stereotype is now the
        # object's class, tagged values its features (otherwise emitters
        # echo it as a provenance comment and the output diverges from
        # the in-code-model artifact)
        del o._applied_stereotypes
check("14 objects rehydrated to gen.sysml classes", retyped == 14,
      str(retyped))
pkg_x = m.roots[0]

# ---- R3 -> R2: transform and compare with the in-code-model artifact --------
print("== R3: emit_v2 on the XMI-read model ==")
text = M.emit_v2(pkg_x)
FROM_XMI.write_text(text + "\n")
reference = REFERENCE.read_text().rstrip("\n")
check("emitted v2 == vehicle_example_v2.sysml (byte-identical)",
      text == reference,
      "" if text == reference else
      f"first diff at char {next((i for i, (a, b) in enumerate(zip(text, reference)) if a != b), min(len(text), len(reference)))}")

print("== R2: sysmlpy validation ==")
counts = M.validate_with_sysmlpy(text)
print("sysmlpy counts:", counts)
check("sysmlpy parses the XMI-derived v2",
      isinstance(counts, dict) and len(counts) >= 5)

print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
print(f"(wrote {XMI_OUT.name}, {FROM_XMI.name})")
