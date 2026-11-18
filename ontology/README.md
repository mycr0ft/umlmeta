# UML-family relationship ontology

An OWL 2 ontology of the relationship vocabulary of UML and the UML-based languages this
repo already generates: UML 2.5.1, the UML Standard Profile, SysML v1, UAF, BPMN 2.0 and the
SysML v2 abstract syntax.

**Generated, not written.** Every axiom comes from the metamodel metadata the generators
preserved — the class hierarchy, each property's declared type (domain and range),
multiplicity, the composite flag, subset and redefinition links, the recorded opposite, the
normative OCL constraint bodies, and for profiles the stereotype's base metaclass. Rebuild
with:

    .venv/bin/python scripts/build_ontology.py

and gate it with:

    PYTHONPATH=~/proj/pyoslc/.venv/lib/python3.13/site-packages .venv/bin/python check_owl_export.py

## What is in it

| | |
|---|---|
| `uml-family-relationships.ttl` | OWL 2 DL, Turtle. Classes, `rdfs:subClassOf`, `owl:ObjectProperty` with domain/range, `owl:FunctionalProperty` for single-valued ends, `owl:inverseOf` where the metamodel records both ends, `rdfs:subPropertyOf` for subsetting, stereotype names as `skos:altLabel` |
| `relationships.json` | the same facts without an RDF stack: classes, properties and their metadata in one document |
| counts | 898 classes · 1,640 object properties · 586 inverse pairs · 162 relationship classes · 344 stereotypes · 2,207 OCL constraints · ~24k triples |

Namespaces are per language, all under the ontology base:

    uml:     UML 2.5.1 metaclasses          sysml:   SysML v1 profile stereotypes
    sp:      UML Standard Profile           uaf:     UAF profile stereotypes
    bpmn:    BPMN 2.0 stereotypes           sysml2:  SysML v2 abstract syntax

Property IRIs are `prefix:Owner__feature` (for example `uml:Dependency__client`) so a
feature name never collides with a class name and the ontology stays inside OWL 2 DL without
punning.

## Three grades, deliberately kept apart

* **stated** — the metamodel says it: a typed end, a subclass axiom, a constraint body.
* **implied** — the profile constrains more than the typing does. `Dependency.client` is
  typed `NamedElement`, so UML itself permits almost any pair; a rule like "«satisfy» runs
  from a Requirement to a Block" is SysML semantics, not UML typing.
* **observed** — an instance corpus shows the pair occurring. Evidence, never a rule.

Nothing in the generated axioms claims the second or third grade. A consumer that needs them
should say so explicitly rather than discovering a constraint that was never stated.

## Known limits

* `Dependency`, `Abstraction` and their subtypes have untyped or `Element`-typed ends, so the
  ontology does **not** narrow what a dependency may connect. Constraining that needs the
  profile's rules (grade *implied*) and is a separate artifact.
* Enumeration-typed and primitive features are not object properties: `aggregation`,
  `visibility` and friends are intentionally absent as properties.
* OCL constraint bodies are carried as annotations in OCL source form; they are not
  translated into OWL axioms. A SHACL shapes file generated from the same source is the
  natural next artifact, since SHACL can express the cardinalities and class constraints that
  OWL cannot state without punning.
* The SysML v2 namespace is the abstract syntax (`sysml2:`), because that is what `umlmeta`
  generates. Cross-language alignment (`sysml:Allocate` ↔ the v2 `AllocationUsage`) follows
  the mapping tables in `v1_to_v2_as.py` and is not yet emitted as `owl:equivalentClass` or
  `skos:closeMatch`.

## Provenance

The class hierarchy and feature typing originate in the OMG-published metamodel XMI that
`generate*.py` consumed; the OCL bodies are the normative constraints from those same
documents. The profile packages are the SysML v1, UML Standard Profile, UAF and BPMN
metamodel serialisations this repo already generates runtimes from. Nothing here is
hand-entered, and `check_owl_export.py` fails if the generator stops saying the things listed
above — including one regression the gate exists for: name collisions across namespaces, where
keying by bare name made `sysml2:Element` overwrite `uml:Element` and silently dropped the
UML subclass axioms.
