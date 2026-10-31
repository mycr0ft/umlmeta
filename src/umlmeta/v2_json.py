#!/usr/bin/env python
"""v2_json.py — serialize the AS graph to JSON and read it back.

Pathway: docs/v1-v2-linkage-pathway.md, milestone M2b (persistence of the v2
side). The document is **metaclass-shaped**: every node's ``@type`` is the
SysML v2 / KerML metaclass the AS object actually is (``PartDefinition``,
``FeatureMembership``, ``AttributeUsage`` ...), every node's ``@id`` is the
link element identity (``umlmeta.link``), and containment rides
``ownedRelationship`` exactly as the AS holds it. That is deliberately not a
parse-tree mirror: the model survives a write/read cycle without a reparse,
and the identities a v1↔v2 link depends on survive with it.

Format ``umlmeta.v2json/1``::

    {"format": "umlmeta.v2json/1",
     "@context": {"@version": 1.1, "@vocab": ".../v2json#"},
     "@id": "<root elementId>",
     "@graph": [{"@type": "Package", "@id": "v1v2:…",
                 "declaredName": "Vehicle",
                 "ownedRelationship": [{"@id": "v1v2:…"}]},
                ...]}

Interoperability notes (pinned, not assumed):

- sysmlpy's interchange document is a *visitor parse-tree* mirror
  (``@type`` values are ``PackageDeclaration`` / ``DefinitionDeclaration`` /
  ``Identification`` / ``OwnedFeatureTyping`` wrappers), so it cannot load a
  metaclass-shaped document directly; the crossing is a small adapter over
  ``@type`` names, or the text notation (``umlmeta.v2_text``), which sysmlpy
  parses today and the M2a gate pins.
- opensysml (Open-MBEE) works on metaclass/KerML-shaped models, which is the
  shape chosen here.

Round-trip contract: ``from_json(to_json(x))`` yields an AS graph whose
identities, member order and scalar features are identical, so
``to_json`` of the result is byte-identical (the M2b gate).
"""
from __future__ import annotations

import enum as _enum
import json
import re

from . import sysml2 as S2

FORMAT = "umlmeta.v2json/1"
CONTEXT = {"@version": 1.1,
           "@vocab": "https://github.com/mycr0ft/umlmeta/v2json#"}

_ENUM_TEXT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$")


class JsonError(Exception):
    """The document is not a umlmeta.v2json/1 graph this module can load."""


def _ser_scalar(v):
    if isinstance(v, _enum.Enum):
        return str(v)                     # 'VisibilityKind.private'
    return v


def _ser(v):
    if hasattr(v, "_props"):
        return {"@id": v._vals.get("elementId")}
    if isinstance(v, (list, tuple)):
        return [_ser(x) for x in v]
    return _ser_scalar(v)


def _node(el):
    eid = el._vals.get("elementId")
    if not eid:
        raise JsonError(f"{type(el).__name__} has no elementId "
                        "(run umlmeta.link.assign_element_ids first)")
    out = {"@type": type(el).__name__, "@id": eid}
    for name, d in el._props.items():
        if d.derived or d.union or name in ("elementId",):
            continue
        v = el._vals.get(name)
        if v is None:
            continue
        out[name] = _ser(v)
    return out


def to_json(root, ids=None):
    """Serialize the AS graph rooted at ``root`` as a format-1 document."""
    if ids:
        for eid, el in ids.items():
            if not el._vals.get("elementId"):
                el._vals["elementId"] = eid
    from .link import contained       # ONE definition of composite
    #                                   ownership (ownedTyping et al. have
    #                                   their own storage)
    graph = []
    seen = set()
    stack = [root]
    while stack:
        el = stack.pop()
        if id(el) in seen:
            continue
        seen.add(id(el))
        graph.append(_node(el))
        for _feat, ch in reversed(contained(el)):
            stack.append(ch)
    return {"format": FORMAT, "@context": dict(CONTEXT),
            "@id": root._vals.get("elementId"), "@graph": graph}


def to_json_text(root, ids=None, indent=2):
    return json.dumps(to_json(root, ids), indent=indent,
                      ensure_ascii=False, sort_keys=False)


def _de_scalar(v):
    if isinstance(v, str):
        m = _ENUM_TEXT.match(v)
        if m:
            cls = getattr(S2, m.group(1), None)
            if isinstance(cls, type) and issubclass(cls, _enum.Enum):
                try:
                    return cls[m.group(2)]
                except KeyError:
                    pass
    return v


def from_json(doc):
    """Rebuild the AS graph from a format-1 document; returns the root."""
    if isinstance(doc, str):
        doc = json.loads(doc)
    if not isinstance(doc, dict):
        raise JsonError("document must be a dict")
    if doc.get("format") != FORMAT:
        raise JsonError(f"unsupported format {doc.get('format')!r} "
                        f"(expected {FORMAT!r})")
    graph = doc.get("@graph")
    root_id = doc.get("@id")
    if not isinstance(graph, list) or not root_id:
        raise JsonError("document needs '@id' and a '@graph' array")
    objs = {}
    for node in graph:
        tn = node.get("@type")
        eid = node.get("@id")
        if not tn or not eid:
            raise JsonError("every @graph element needs '@type' and '@id'")
        try:
            cls = S2.metaclass(tn)
        except Exception:                  # metaclass() raises on a miss
            cls = None
        if cls is None:
            raise JsonError(f"unknown metaclass {tn!r}")
        obj = cls()
        obj._vals["elementId"] = eid
        objs[eid] = obj
    for node in graph:
        obj = objs[node["@id"]]
        for name, v in node.items():
            if name in ("@type", "@id"):
                continue
            if name not in obj._props:
                raise JsonError(f"{node['@type']} has no feature {name!r}")
            obj._vals[name] = _de(v, objs)
    root = objs.get(root_id)
    if root is None:
        raise JsonError(f"root @id {root_id!r} not in @graph")
    return root


def _de(v, objs):
    if isinstance(v, dict):
        if "@id" not in v:
            raise JsonError(f"reference without @id: {v!r}")
        target = objs.get(v["@id"])
        if target is None:
            raise JsonError(f"dangling @id {v['@id']!r}")
        return target
    if isinstance(v, list):
        return [_de(x, objs) for x in v]
    return _de_scalar(v)


def from_json_text(text):
    return from_json(text)
