#!/usr/bin/env python
"""checks: umlmeta boxes_view — Block Definition Diagrams from v1 data.

Builds an in-memory vehicle model (blocks, parts, ports, a reference,
values, a generalization, sub-packages) via gen/uml25, renders through
boxes_view.as_bdd_boxes, and checks the content model + both renderers.
Run under the umlmeta venv (lxml + drawille) as plain python3:
    .venv/bin/python check_bdd_boxes.py
Oracles follow Delligatti's Chapter 3/4/10 notation contract.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from umlmeta import uml25 as U           # noqa: E402
from umlmeta import boxes_view as BV         # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" +
          (f"  [{detail}]" if detail else ""))


def build_vehicle():
    pkg = U.Package(); pkg.name = 'Vehicle Domain Library'

    veh = U.Class(); veh.name = 'Vehicle'
    veh._applied_stereotypes = [('SysML', 'Block', 'b1')]

    eng = U.Class(); eng.name = 'Engine'
    eng._applied_stereotypes = [('SysML', 'Block', 'b2')]
    tank = U.Class(); tank.name = 'FuelTank'
    tank._applied_stereotypes = [('SysML', 'Block', 'b3')]

    veh_eng = U.Property(); veh_eng.name = 'engine'; veh_eng.type = eng
    veh_eng.aggregation = 'composite'
    veh.ownedAttribute.append(veh_eng)
    veh_tank = U.Property(); veh_tank.name = 'fuelTank'; veh_tank.type = tank
    veh_tank.aggregation = 'composite'
    veh.ownedAttribute.append(veh_tank)

    real = U.PrimitiveType(); real.name = 'Real'
    pkg.packagedElement.append(real)
    veh_mass = U.Property(); veh_mass.name = 'mass'; veh_mass.type = real
    veh_mass._applied_stereotypes = [('SysML', 'ValueProperty', 'b4')]
    veh.ownedAttribute.append(veh_mass)

    veh_fuel = U.Property(); veh_fuel.name = 'fuel'; veh_fuel.type = tank
    veh_fuel._applied_stereotypes = [('SysML', 'ReferenceProperty', 'b5')]
    veh.ownedAttribute.append(veh_fuel)

    shaft = U.Port(); shaft.name = 'shaft'
    veh.ownedAttribute.append(shaft)

    gen = U.Generalization(); gen.general = eng
    veh.generalization.append(gen)

    sub = U.Package(); sub.name = 'Subsystems'
    pkg.packagedElement.append(sub)
    for k in (veh, eng, tank):
        pkg.packagedElement.append(k)
    return pkg


def main():
    pkg = build_vehicle()
    d = BV.as_bdd_boxes(
        pkg, frame_kind='bdd', element_kind='modelLibrary',
        element_name='Vehicle Domain Library')

    names = [n.name for n in d.nodes] + [v.name for v in d.views]
    check('all three blocks + the package drawn',
          set(names) == {'Vehicle Domain Library', 'Vehicle', 'Engine',
                         'FuelTank'}, str(names))
    veh = next(n for n in d.nodes if n.name == 'Vehicle')
    parts_rows = next((lines for t, lines in veh.compartments
                       if t == 'parts'), [])
    check('parts compartment carries the composite ends',
          parts_rows == ['engine : Engine', 'fuelTank : FuelTank'],
          str(parts_rows))
    check('values compartment carries the value property',
          ('values', ['mass : Real']) in veh.compartments, str(veh.compartments))
    check('references compartment carries the reference property',
          ('references', ['fuel : FuelTank']) in veh.compartments,
          str(veh.compartments))
    check('port on the boundary',
          len(veh.ports) == 1 and veh.ports[0].label == 'shaft',
          str([p.label for p in veh.ports]))
    check('generalization edge to Engine with a triangle',
          any(e.target.name == 'Engine' and e.target_style == 'triangle'
              for e in d.edges if e.source is veh),
          str(len(d.edges)))
    check('package view is a folder-tab view',
          d.views[0].name == 'Vehicle Domain Library'
          and any('package' in (v.stereotypes or []) for v in d.views))
    check('children nested in the package view',
          veh.parent is not None or any(veh in v.children for v in d.views),
          str(len(d.views)))

    # both renderers
    txt = d.render()
    svg = d.render_svg()
    check('braille render', 'Vehicle' in txt)
    check('svg render', all(k in svg for k in
                            ('Vehicle', 'engine : Engine', '<polygon')))

    out = Path('/home/jfox/proj/sysml-distilled/reproduced')
    out.mkdir(parents=True, exist_ok=True)
    (out / 'figBDD_blocks.txt').write_text(txt)
    (out / 'figBDD_blocks.svg').write_text(svg)
    print(f"render -> {out}/figBDD_blocks.{{txt,svg}}")

    print(f"\nRESULT: {len(PASS)} pass, {len(FAIL)} fail")
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())