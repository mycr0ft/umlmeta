#!/usr/bin/env python
"""checks: umlmeta boxes_view — UML 2.5.1 deployment diagrams (ch19).

As_deployment_boxes maps in-memory gen/uml25 deployment models
(Instances of Node, Artifact, Deployment, CommunicationPath,
Manifestation) to diagramboxes' ch19 notation:

- Node / instance = the perspective cube (:name instance labels)
- Artifact = Class rectangle with the keyword artifact
- Deployment = dashed dependency with the deploy keyword OR containment
- Manifestation = dashed line with the manifest keyword
- CommunicationPath = a plain association link

Run under the umlmeta venv:
    .venv/bin/python check_deployment_boxes.py
Oracles quoted from formal/2017-12-05 sections 19.2.4, 19.3.4, 19.4.4.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from umlmeta import uml25 as U           # noqa: E402
from umlmeta import boxes_view as BV         # noqa: E402
import diagramboxes as db       # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" +
          (f"  [{detail}]" if detail else ""))


def build_deployment():
    model = U.Model()

    server_type = U.Node(); server_type.name = 'App Server'
    model.packagedElement.append(server_type)

    app1 = U.InstanceSpecification(); app1.name = ':app-server1'
    app2 = U.InstanceSpecification(); app2.name = ':app-server2'
    model.packagedElement.append(app1)
    model.packagedElement.append(app2)

    war = U.Artifact(); war.name = 'order-handler.war'
    model.packagedElement.append(war)

    comp = U.Component(); comp.name = 'Order Entry Handler'
    model.packagedElement.append(comp)
    man = U.Manifestation(); man.name = ''
    man.utilizedElement = comp if hasattr(man, 'utilizedElement') else None
    try:
        war.manifestation.append(man)
        print('manifestation attached')
    except Exception as e:
        print('manifest attach err:', e)

    dep1 = U.Deployment(); dep1.deployedArtifact.append(war)
    dep2 = U.Deployment(); dep2.deployedArtifact.append(war)
    app1.deployment.append(dep1)
    app2.deployment.append(dep2)

    cp = U.CommunicationPath()      # between the server instances?
    # type-level: server_type -- cp -- a client device
    dev = U.Node(); dev.name = 'Client Device'
    model.packagedElement.append(dev)
    return model


def main():
    model = build_deployment()
    d = BV.as_deployment_boxes(model,
                               frame_kind='deployment',
                               element_kind='', element_name='')
    names = [n.name for n in d.nodes]
    check('nodes + artifact all drawn',
          set([':app-server1', ':app-server2', 'order-handler.war',
               'Client Device']) <= set(names), str(names))
    cubes = [n for n in d.nodes if getattr(n, 'cube', False)]
    check('instance nodes are cubes', len(cubes) >= 2, str(len(cubes)))
    war_n = next(n for n in d.nodes if n.name == 'order-handler.war')
    check('artifact keyword row',
          any('artifact' in s for s in war_n.stereotypes),
          str(war_n.stereotypes))
    dashed = [e for e in d.edges if e.line_style == db.DASHED]
    dep_edges = [e for e in dashed if 'deploy' in (e.label or '')]
    check('deploy edges dashed with the keyword',
          len(dep_edges) == 2, str([e.label for e in dashed]))

    txt = d.render()
    svg = d.render_svg()
    check('braille render has node + artifact',
          ':app-server1' in txt and 'order-handler.war' in txt)
    check('svg has cube facets',
          'nodecube' in svg)

    out = Path('/home/jfox/proj/sysml-distilled/reproduced')
    (out / 'figUML_deployment.txt').write_text(txt)
    (out / 'figUML_deployment.svg').write_text(svg)
    print(f"render -> {out}/figUML_deployment.{{txt,svg}}")

    print(f"\\nRESULT: {len(PASS)} pass, {len(FAIL)} fail")
    return 0 if not FAIL else 1




if __name__ == '__main__':
    sys.exit(main())