#!/usr/bin/env python
"""Gate for the generated OWL ontology (scripts/build_ontology.py).

The ontology is generated, so the gate has to prove the generator still says the right
things rather than that a file exists. Checks, in order:

1. the build runs and writes both artifacts;
2. the Turtle parses (needs rdflib: this suite SKIPS the parse when rdflib is absent, the
   same way the other suites skip an unavailable corpus, and says so);
3. the taxonomy holds: the relationship backbone and the profile stereotypes sit under
   their metaclasses;
4. typed ends carry both a domain and a range;
5. inverse pairs are symmetric - a one-sided opposite would assert an inverse the
   metamodel does not state;
6. every stereotype has a base metaclass axiom;
7. the normative OCL constraints travelled;
8. namespace collisions did not merge classes: ``uml:Element`` and ``sysml2:Element`` must
   both exist and be different subjects (the bug this gate was written after).

Run from the repo root:  .venv/bin/python check_owl_export.py
Exit 0 on pass, 1 on failure.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = "https://mycr0ft.github.io/umlmeta/ontology/uml-family-relationships"
NS = "https://mycr0ft.github.io/umlmeta/ns#"

checks: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    checks.append((label, bool(ok), detail))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [sys.executable, str(HERE / "scripts" / "build_ontology.py"), "--out", tmp],
            capture_output=True, text=True, cwd=HERE,
        )
        check("build runs", proc.returncode == 0, proc.stderr.strip()[-300:])
        ttl = Path(tmp) / "uml-family-relationships.ttl"
        js = Path(tmp) / "relationships.json"
        check("turtle written", ttl.exists(), str(ttl))
        check("json written", js.exists(), str(js))
        if not (ttl.exists() and js.exists()):
            return report()

        counts = json.loads(js.read_text())
        check("classes > 800", counts["counts"]["classes"] > 800,
              str(counts["counts"]["classes"]))
        check("properties > 1500", counts["counts"]["properties"] > 1500,
              str(counts["counts"]["properties"]))
        check("every stereotype counted", counts["counts"]["stereotypes"] > 300,
              str(counts["counts"]["stereotypes"]))

        try:
            from rdflib import RDF, Graph, OWL, RDFS, URIRef
        except ImportError:
            print("SKIP: rdflib not installed - the structural checks below need it")
            print("      (pip install rdflib, or run this suite from a venv that has it)")
            return report()

        g = Graph()
        try:
            g.parse(str(ttl), format="turtle")
            check("turtle parses", True, f"{len(g)} triples")
        except Exception as exc:                              # noqa: BLE001
            check("turtle parses", False, str(exc)[:200])
            return report()

        def cls(prefix: str, name: str) -> URIRef:
            return URIRef(f"{BASE}/{prefix}#{name}")

        def prop(owner_prefix: str, owner: str, name: str) -> URIRef:
            return URIRef(f"{BASE}/{owner_prefix}#{owner}__{name}")

        # 3. taxonomy.  Profile stereotypes may reach their metaclass through another
        # stereotype (SysML Discrete -> Rate -> ... -> Element), so the axiom is tested as
        # reachability: a direct-only test rejects correct inheritance.
        def subclasses(node, seen=None):
            seen = set() if seen is None else seen
            for parent in g.objects(node, RDFS.subClassOf):
                if parent not in seen:
                    seen.add(parent)
                    subclasses(parent, seen)
            return seen

        for child, prefix, parent in (
            ("Dependency", "uml", "DirectedRelationship"),
            ("Abstraction", "uml", "Dependency"),
            ("Realization", "uml", "Abstraction"),
            ("Association", "uml", "Relationship"),
            ("Generalization", "uml", "DirectedRelationship"),
            ("Connector", "uml", "Feature"),
            ("Satisfy", "sysml", "Dependency"),
            ("Verify", "sysml", "Dependency"),
            ("Allocate", "sysml", "Abstraction"),
            ("Refine", "sysml", "Abstraction"),
            ("Implements", "uaf", "Abstraction"),
            ("Continuous", "sysml", "Element"),
            ("InterfaceBlock", "sysml", "Class"),
        ):
            check(f"{prefix}:{child} reaches uml:{parent}",
                  cls("uml", parent) in subclasses(cls(prefix, child)))

        # 4. typed ends
        for owner_prefix, owner, feature, rng in (
            ("uml", "Dependency", "client", "NamedElement"),
            ("uml", "Dependency", "supplier", "NamedElement"),
            ("uml", "Generalization", "general", "Classifier"),
            ("uml", "Generalization", "specific", "Classifier"),
        ):
            p = prop(owner_prefix, owner, feature)
            check(f"{owner}.{feature} domain+range",
                  (p, RDFS.domain, cls("uml", owner)) in g
                  and (p, RDFS.range, cls("uml", rng)) in g)

        # 5. inverse symmetry
        inverses = list(g.triples((None, OWL.inverseOf, None)))
        symmetric = sum(1 for a, _, b in inverses if (b, OWL.inverseOf, a) in g)
        check(f"inverses symmetric ({symmetric}/{len(inverses)})",
              bool(inverses) and symmetric == len(inverses))

        # 6. stereotype base axioms
        stereotypes = set(g.subjects(URIRef(f"{NS}stereotypeUri"), None))
        defined = set(g.subjects(RDF.type, OWL.Class))
        with_parent = {s for s in stereotypes
                       if any(parent in defined for parent in g.objects(s, RDFS.subClassOf))}
        check(f"stereotypes with a stated parent ({len(with_parent)}/{len(stereotypes)})",
              bool(stereotypes) and with_parent == stereotypes)
        direct_uml = {s for s in stereotypes
                      for parent in g.objects(s, RDFS.subClassOf)
                      if str(parent).startswith(f"{BASE}/uml#")}
        # the remainder specialise another stereotype, which OWL resolves transitively
        check(f"stereotypes whose parent is a UML metaclass ({len(direct_uml)})",
              len(direct_uml) > 300,
              f"{len(stereotypes) - len(direct_uml)} specialise another stereotype")

        # 7. constraints travelled
        n_constraints = len(list(g.triples((None, URIRef(f"{NS}oclConstraint"), None))))
        check(f"OCL constraints attached ({n_constraints})", n_constraints > 1000)

        # 8. no namespace collisions: the bug this gate exists for
        uml_element = cls("uml", "Element")
        sysml2_element = cls("sysml2", "Element")
        check("uml:Element and sysml2:Element are distinct classes",
              uml_element != sysml2_element
              and (uml_element, RDF.type, OWL.Class) in g
              and (sysml2_element, RDF.type, OWL.Class) in g)

    return report()


def report() -> int:
    failed = [c for c in checks if not c[1]]
    for label, ok, detail in checks:
        print(f"[{'ok' if ok else 'FAIL'}] {label}" + (f"  -- {detail}" if detail and not ok else ""))
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
