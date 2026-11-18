# SPDX-License-Identifier: MPL-2.0
"""Export an OWL 2 ontology of UML-family relationships from the generated runtimes.

The ontology is generated, not written: every axiom comes from the metamodel metadata the
generators already preserved — the class hierarchy, each property's type (domain/range),
multiplicity, composite flag, subsets/redefines, the recorded opposite, the normative OCL
constraints, and for profiles the stereotype's base metaclass.

Three grades of statement are kept apart on purpose:

* ``stated``   — the metamodel says it (a typed end, a subclass axiom, a constraint body);
* ``implied``  — the profile's semantics constrain more than the typing does (``Satisfy``
  between a Requirement and a Block is SysML's rule, not UML's);
* ``observed`` — the instance corpus shows the pair occurring (evidence, never a rule).

A consumer that cannot tell those apart will treat "some model did this" as "the language
allows this", which is the failure mode this separation exists to prevent.

Usage:
    <venv>/bin/python scripts/build_ontology.py [--out DIR] [--base IRI]

Writes ``uml-family-relationships.ttl`` (OWL 2 DL, Turtle) and ``relationships.json``
(the same facts in a form tooling can query without an RDF stack).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DEFAULT_BASE = "https://mycr0ft.github.io/umlmeta/ontology/uml-family-relationships"
DEFAULT_OUT = HERE.parent / "ontology"

#: Namespace prefix -> (module name, IRI fragment). Ordering matters only for prefix
#: declaration in the emitted Turtle.
MODULES: tuple[tuple[str, str, str], ...] = (
    ("uml", "uml25", "UML 2.5.1 metaclasses"),
    ("sp", "standard_profile", "UML Standard Profile stereotypes"),
    ("sysml", "sysml", "SysML v1 profile stereotypes"),
    ("uaf", "uaf", "UAF profile stereotypes"),
    ("bpmn", "bpmn", "BPMN 2.0 stereotypes"),
    ("sysml2", "sysml2", "SysML v2 abstract syntax"),
)

OWL = "http://www.w3.org/2002/07/owl#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
SKOS = "http://www.w3.org/2004/02/skos/core#"
XSD = "http://www.w3.org/2001/XMLSchema#"


def is_metaclass(obj: Any) -> bool:
    """True for a generated runtime class (metaclass or stereotype), not an enum/helper."""
    if not isinstance(obj, type):
        return False
    if obj.__module__.rsplit(".", 1)[-1] not in {m for _, m, _ in MODULES}:
        return False
    if getattr(obj, "_STEREO", None) is not None:
        return True
    return hasattr(obj, "_DECL") or any(hasattr(b, "_DECL") for b in obj.__mro__[1:])


def runtime_modules() -> dict[str, Any]:
    import importlib

    out = {}
    for prefix, module, _label in MODULES:
        out[prefix] = importlib.import_module(f"umlmeta.{module}")
    return out


def collect_classes(module: Any, module_name: str) -> dict[str, type]:
    return {
        name: obj
        for name, obj in vars(module).items()
        if name[:1].isupper() and is_metaclass(obj)
        and obj.__module__.rsplit(".", 1)[-1] == module_name
    }


def own_features(cls: type) -> dict[str, Any]:
    """Features declared on *cls* itself (not inherited), from its own ``_DECL``."""
    return dict(vars(cls).get("_DECL", {}) or {})


def metaclass_bases(cls: type, known: set[str]) -> list[str]:
    return [b.__name__ for b in cls.__mro__[1:] if b.__name__ in known]


def describe(cls: type) -> dict[str, Any]:
    doc = (cls.__doc__ or "").strip().splitlines()
    text = " ".join(line.strip() for line in doc if line.strip())
    return {
        "name": cls.__name__,
        "stereotype": getattr(cls, "_STEREO", None),
        "package": getattr(cls, "_PKG", None),
        "abstract": bool(getattr(cls, "_ABSTRACT", False)),
        "bases": [],
        "definition": text[:1500],
        "constraints": [
            {"name": name, "body": body}
            for name, body in (getattr(cls, "CONSTRAINTS", ()) or ())
        ],
    }


def feature_rows(cls: type, known: set[str]) -> Iterable[dict[str, Any]]:
    """Object properties for one class: every feature whose type is a metaclass."""
    for name, ref in own_features(cls).items():
        target = getattr(ref, "t", None)
        target_name = target.__name__ if isinstance(target, type) else str(target)
        if target_name not in known:
            continue                       # primitive, enum or library type: not a node
        yield {
            "owner": cls.__name__,
            "name": name,
            "range": target_name,
            "multi": bool(getattr(ref, "multi", False)),
            "lo": getattr(ref, "lo", 0),
            "hi": getattr(ref, "hi", 1),
            "composite": bool(getattr(ref, "composite", False)),
            "derived": bool(getattr(ref, "derived", False)),
            "union": bool(getattr(ref, "union", False)),
            "readonly": bool(getattr(ref, "readonly", False)),
            "subsets": list(getattr(ref, "subsets", ()) or ()),
            "redefines": list(getattr(ref, "redefines", ()) or ()),
            "opposite": getattr(ref, "opp", None),
            "assoc": getattr(ref, "assoc", None),
        }


def build() -> dict[str, Any]:
    """Collect classes and properties, keyed by QUALIFIED name (``prefix:Name``).

    Bare names collide: ``Element``, ``Relationship`` and ``Dependency`` exist in both the
    UML and the SysML v2 namespaces, and keying by name silently let one module's class
    overwrite the other's — which emitted the wrong subclass axioms and dropped the
    ``uml:`` IRIs entirely. Identity maps keep the resolution exact.
    """
    modules = runtime_modules()
    class_of: dict[str, type] = {}          # qualified key -> class
    key_of: dict[type, str] = {}            # class -> qualified key
    for prefix, module_name, _label in MODULES:
        for name, cls in collect_classes(modules[prefix], module_name).items():
            key = f"{prefix}:{name}"
            class_of[key] = cls
            key_of[cls] = key

    classes: dict[str, dict[str, Any]] = {}
    properties: list[dict[str, Any]] = []
    prefix_of: dict[str, str] = {}

    languages = {"uml": "UML 2.5.1", "sp": "UML Standard Profile", "sysml": "SysML v1",
                 "uaf": "UAF", "bpmn": "BPMN 2.0", "sysml2": "SysML v2"}

    for key, cls in class_of.items():
        prefix = key.split(":", 1)[0]
        row = describe(cls)
        row["key"] = key
        row["prefix"] = prefix
        row["language"] = languages[prefix]
        # DIRECT bases only: the full MRO is what a reasoner computes, and emitting every
        # ancestor makes each class carry ten redundant subclass axioms
        row["bases"] = [key_of[b] for b in cls.__bases__ if b in key_of]
        row["base_metaclasses"] = [
            key_of[b] for b in (getattr(cls, "_BASE_METACLASSES", ()) or ())
            if b in class_of and class_of[b].__module__.endswith("uml25")
        ]
        classes[key] = row
        prefix_of[key] = prefix

    def resolve_target(owner_key: str, target: Any) -> str | None:
        """Resolve a feature's declared type to a qualified class key.

        ``_DECL`` refs carry the type either as a class object (profile base refs) or as a
        bare name string (most metaclass features: ``_Ref('client', "NamedElement", ...)``).
        Strings resolve in the owner's own module first, then in UML, so ``sysml``'s
        ``Allocate`` pointing at ``Abstraction`` lands on ``uml:Abstraction`` and a SysML v2
        ``Element`` stays ``sysml2:Element``.
        """
        if isinstance(target, type):
            return key_of.get(target)
        if not isinstance(target, str) or not target:
            return None
        owner_prefix = owner_key.split(":", 1)[0]
        for candidate in (f"{owner_prefix}:{target}", f"uml:{target}"):
            if candidate in class_of:
                return candidate
        for key in class_of:
            if key.split(":", 1)[1] == target:
                return key
        return None

    for key, cls in class_of.items():
        for name, ref in own_features(cls).items():
            target_key = resolve_target(key, getattr(ref, "t", None))
            if target_key is None:
                continue
            properties.append({
                "owner": key,
                "name": name,
                "range": target_key,
                "multi": bool(getattr(ref, "multi", False)),
                "lo": getattr(ref, "lo", 0),
                "hi": getattr(ref, "hi", 1),
                "composite": bool(getattr(ref, "composite", False)),
                "derived": bool(getattr(ref, "derived", False)),
                "union": bool(getattr(ref, "union", False)),
                "readonly": bool(getattr(ref, "readonly", False)),
                "subsets": list(getattr(ref, "subsets", ()) or ()),
                "redefines": list(getattr(ref, "redefines", ()) or ()),
                "opposite": getattr(ref, "opp", None),
                "assoc": getattr(ref, "assoc", None),
            })

    by_owner = {(p["owner"], p["name"]): p for p in properties}
    inverses = 0
    for prop in properties:
        opp = prop["opposite"]
        if not opp:
            continue
        candidate = by_owner.get((prop["range"], opp))
        if candidate is not None and candidate.get("opposite") == prop["name"]:
            inverses += 1

    # relationship classes = transitive subclasses of uml:Relationship, walked over the
    # emitted direct bases (the count is a fact about the ontology, so it must not depend on
    # which axioms happened to be direct)
    def ancestors_of(key: str, seen: set[str] | None = None) -> set[str]:
        seen = set() if seen is None else seen
        for parent in classes.get(key, {}).get("bases", []):
            if parent not in seen:
                seen.add(parent)
                ancestors_of(parent, seen)
        return seen

    relationships = sorted(
        key for key in classes if "uml:Relationship" in ancestors_of(key))
    stereotype_kinds = sorted(key for key, row in classes.items() if row["stereotype"])
    return {
        "classes": classes,
        "properties": properties,
        "inverses": inverses,
        "prefix_of": prefix_of,
        "relationships": relationships,
        "stereotype_kinds": stereotype_kinds,
    }


# ----------------------------------------------------------------- emitters
_TAG = re.compile(r"<[^>]+>")


def _esc(text: str) -> str:
    """Plain-text Turtle literal body: tags stripped, whitespace collapsed, quotes escaped."""
    text = _TAG.sub(" ", text)
    text = " ".join(text.split())
    return (text.replace("\\", "\\\\").replace('"', '\\"').replace("\t", " ").strip())


def _block(subject: str, fragments: list[str]) -> str:
    """One subject block: `s p1 o1 ; p2 o2 .`, wrapped for readability."""
    body = " ;\n    ".join(fragments)
    return f"{subject} {body} .\n"


def emit_turtle(model: dict[str, Any], base: str) -> str:
    prefixes = sorted({key.split(":", 1)[0] for key in model["classes"]})
    lines: list[str] = [
        "@prefix owl:  <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
        "@prefix umlmeta: <https://mycr0ft.github.io/umlmeta/ns#> .",
    ]
    for prefix in prefixes:
        lines.append(f"@prefix {prefix}: <{base}/{prefix}#> .")
    lines.append("")
    lines.append(f"<{base}> a owl:Ontology ;")
    lines.append('    rdfs:label "UML-family relationship ontology"@en ;')
    lines.append(
        '    rdfs:comment "Generated from the OMG metamodel feeds preserved by umlmeta. '
        'Class hierarchy, property domains and ranges, multiplicities, composites, subset '
        'links, recorded opposites and normative OCL constraints are stated facts; the '
        'relationship matrix keeps stated, implied and observed apart."@en ;')
    lines.append('    owl:versionInfo "1" .')
    lines.append("")
    # declare the annotation properties, or the ontology is not OWL 2 DL
    for annotation in ("language", "omgPackage", "abstract", "stereotypeUri",
                       "oclConstraint", "composite", "derived"):
        lines.append(f"umlmeta:{annotation} a owl:AnnotationProperty .")
    lines.append("")

    # classes
    for key, row in model["classes"].items():
        subject = key.replace(":", ":")
        frags: list[str] = ["a owl:Class", f'rdfs:label "{_esc(row["name"])}"@en',
                            f'umlmeta:language "{_esc(row["language"])}"@en']
        if row["package"]:
            frags.append(f'umlmeta:omgPackage "{_esc(row["package"])}"')
        if row["abstract"]:
            frags.append("umlmeta:abstract true")
        if row["stereotype"]:
            frags.append(f'skos:altLabel "{_esc(row["stereotype"].split("::")[-1])}"@en')
            frags.append(f'umlmeta:stereotypeUri "{_esc(row["stereotype"])}"')
        if row["definition"]:
            frags.append(f'skos:definition "{_esc(row["definition"])}"@en')
        for parent_key in row["bases"]:
            frags.append(f"rdfs:subClassOf {parent_key}")
        for base_meta_key in row["base_metaclasses"]:
            if base_meta_key not in row["bases"]:
                frags.append(f"rdfs:subClassOf {base_meta_key}")
        for constraint in row["constraints"]:
            frags.append(f'umlmeta:oclConstraint "{_esc(constraint["body"])}"')
        lines.append(_block(subject, frags))

    # properties, keyed by owner so a colliding feature name stays unambiguous
    by_owner = {(p["owner"], p["name"]): p for p in model["properties"]}
    for prop in model["properties"]:
        iri = f"{prop['owner']}__{prop['name']}"
        kinds = ["owl:ObjectProperty"]
        if not prop["multi"] and str(prop["hi"]) == "1":
            kinds.append("owl:FunctionalProperty")
        frags = [f"a {' , '.join(kinds)}",
                 f'rdfs:label "{_esc(prop["name"])}"@en',
                 f"rdfs:domain {prop['owner']}",
                 f"rdfs:range {prop['range']}"]
        if prop["composite"]:
            frags.append("umlmeta:composite true")
        if prop["derived"] or prop["union"]:
            frags.append("umlmeta:derived true")
        for subset in prop["subsets"]:
            frags.append(f"rdfs:subPropertyOf {prop['owner']}__{subset}")
        opp = prop["opposite"]
        if opp and by_owner.get((prop["range"], opp), {}).get("opposite") == prop["name"]:
            frags.append(f"owl:inverseOf {prop['range']}__{opp}")
        lines.append(_block(iri, frags))

    return "\n".join(lines) + "\n"


def emit_json(model: dict[str, Any]) -> str:
    classes = {
        key: {
            "iri": key,
            "language": row["language"],
            "stereotype": row["stereotype"],
            "omgPackage": row["package"],
            "abstract": row["abstract"],
            "bases": row["bases"],
            "baseMetaclasses": row["base_metaclasses"],
            "constraints": row["constraints"],
            "definition": row["definition"],
        }
        for key, row in sorted(model["classes"].items())
    }
    return json.dumps({
        "source": "umlmeta generated runtimes",
        "grades": {
            "stated": "the metamodel states it (typing, subclass axiom, constraint)",
            "implied": "the profile constrains more than the typing does",
            "observed": "an instance corpus shows it; evidence, never a rule",
        },
        "counts": {
            "classes": len(classes),
            "properties": len(model["properties"]),
            "inversePairs": model["inverses"],
            "relationshipClasses": len(model["relationships"]),
            "stereotypes": len(model["stereotype_kinds"]),
        },
        "relationships": model["relationships"],
        "stereotypes": model["stereotype_kinds"],
        "classes": classes,
        "properties": sorted(model["properties"],
                             key=lambda p: (p["owner"], p["name"])),
    }, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--base", default=DEFAULT_BASE)
    args = ap.parse_args(argv)

    model = build()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ttl = out / "uml-family-relationships.ttl"
    js = out / "relationships.json"
    ttl.write_text(emit_turtle(model, args.base.rstrip("/")), encoding="utf-8")
    js.write_text(emit_json(model), encoding="utf-8")
    counts = {
        "classes": len(model["classes"]),
        "properties": len(model["properties"]),
        "inversePairs": model["inverses"],
        "relationshipClasses": len(model["relationships"]),
        "stereotypes": len(model["stereotype_kinds"]),
        "ttlBytes": ttl.stat().st_size,
    }
    print(json.dumps(counts, indent=2))
    print(f"wrote {ttl}\nwrote {js}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
