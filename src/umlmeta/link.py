#!/usr/bin/env python
"""link.py — the v1 ↔ v2 linkage layer: stable identities, provenance, hashes.

Pathway: docs/v1-v2-linkage-pathway.md (milestone M1).

The transformation is a one-shot mapping; a project that keeps a SysML v1
model and a SysML v2 model side by side for a long transition needs three
things the mapping itself does not provide:

  identity   a SysML v2 ``elementId`` that is stable across re-transforms,
             re-saves and unrelated edits (L1/L2 in the pathway's levels);
  provenance which v1 element each v2 element came from, with the v1 xmi id
             as a per-snapshot cache and a content signature as the repair
             key when a name changes;
  a hash    a semantic content hash over the AS graph, so "did the v2 side
             change?" is answerable without diffing serializations.

Identity scheme (adopted from sysmlpy's stable-identities work — see
sysmlpy ``docs/stable-identities.md`` and ``interchange.py``'s
``STABLE_NAMESPACE`` / ``_StableIdAssigner``):

  key = the element's declared qualified-name path joined with ``|``,
        plus its SysML v2 metaclass name; a same-name sibling group takes
        an occurrence index appended as ``|#<n>``;
  id  = ``v1v2:`` + uuid5(LINK_NAMESPACE, key).

Unnamed elements (memberships, expressions, pins, the anonymous pieces the
rules build) hash their nearest declared ancestor's id plus the structural
role they ride (containment relationship kind + index) and their metaclass,
so they move only when the structure between them and that ancestor changes.

Why not the v1 ``xmi:id``: Cameo delta-snapshots and TeamworkCloud
check-ins re-mint ids on save (see docs/semantic-content-hash.md — 47 id
eras in one corpus file). Identity must follow the model, not the
serialization. The xmi id is carried in the provenance record only.

``adopt=True`` is the L3 hook: an id already present on an element (from a
prior export / a link sidecar, or one a v2 tool assigned) is kept verbatim
instead of re-derived — the same contract as sysmlpy's
``--reconcile-with`` fixed point.
"""
from __future__ import annotations

import hashlib
import uuid

LINK_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://github.com/mycr0ft/umlmeta/v1v2-link/stable-ids")
LINK_PREFIX = "v1v2:"
SIDECAR_FORMAT = "umlmeta.v1v2link/1"
PATH_SEP = "::"


def _relationships(el):
    return [r for r in (getattr(el, "ownedRelationship", None) or ())
            if hasattr(r, "_props")]


def contained(el):
    """Composite children in descriptor order: (feature name, child) pairs.

    Composite ownership in the generated runtime is NOT confined to
    ``ownedRelationship``: derived subsets such as ``ownedTyping`` and
    ``ownedSpecialization`` have their own storage, and a walk that only
    follows ``ownedRelationship`` misses every FeatureTyping (an identity and
    serialization bug, not a style choice).
    """
    out = []
    for name in sorted(getattr(el, "_props", {})):
        d = el._props[name]
        if d.derived or d.union or not d.composite:
            continue
        v = el._vals.get(name)
        if v is None:
            continue
        items = v if isinstance(v, (list, tuple)) else [v]
        out.extend((name, x) for x in items if hasattr(x, "_props"))
    return out


def _walk(root):
    """DFS over AS containment: yields (element, path_parts, element_id).

    ``path_parts`` is the chain of declared names from the root; unnamed
    elements inherit their parent's path (their identity is parent-anchored,
    see the module docstring).
    """
    seen = set()
    stack: list = [(root, ())]
    while stack:
        el, parts = stack.pop()
        if id(el) in seen:
            continue
        seen.add(id(el))
        name = el._vals.get("declaredName")
        if isinstance(name, str) and name:
            parts = parts + (name,)
        yield el, parts, el._vals.get("elementId")
        for _feat, ch in reversed(contained(el)):
            stack.append((ch, parts))


def _scalar_signature(el):
    """A short hash over an element's scalar features (the repair key)."""
    items = []
    for name in sorted(getattr(el, "_props", {})):
        d = el._props[name]
        if d.derived or d.union or name == "elementId":
            continue
        v = el._vals.get(name)
        if v is None or hasattr(v, "_props"):
            continue
        if isinstance(v, (list, tuple)):
            vals = [str(x) for x in v if not hasattr(x, "_props") and x is not None]
            if vals:
                items.append(name + "=[" + ",".join(sorted(vals)) + "]")
        else:
            items.append(name + "=" + str(v))
    blob = "\n".join(items)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def assign_element_ids(root, adopt=False):
    """Derive a deterministic SysML v2 ``elementId`` for every AS element.

    Returns ``{elementId: element}``. With ``adopt=True`` an existing
    elementId is kept as-is (the L3 / reconcile hook); otherwise ids are
    re-derived from the identity key, which never depends on prior ids.
    """
    ids = {}
    seen = set()
    occurrence = {}

    def visit(el, parts, parent_id, role, ordinal):
        if id(el) in seen:
            return
        seen.add(id(el))
        name = el._vals.get("declaredName")
        tname = type(el).__name__
        if isinstance(name, str) and name:
            full = parts + (name,)
            key = "|".join(full) + "|" + tname
        else:
            full = parts
            key = f"{parent_id or 'root'}|{role}:{ordinal}|{tname}"
        n = occurrence.get(key, 0)
        occurrence[key] = n + 1
        if n:
            key = f"{key}|#{n}"
        existing = el._vals.get("elementId")
        if adopt and isinstance(existing, str) and existing:
            eid = existing
        else:
            eid = LINK_PREFIX + str(uuid.uuid5(LINK_NAMESPACE, key))
            el._vals["elementId"] = eid
        ids[eid] = el
        seen_feat = {}
        for feat, ch in contained(el):
            n = seen_feat.get(feat, 0)
            seen_feat[feat] = n + 1
            visit(ch, full, eid, feat, n)

    visit(root, (), None, "root", 0)
    return ids


def _v1_children(el):
    """v1 composite containment in descriptor order (the index is keyed on
    id(v1 element), so the v1 tree is walked for the record set)."""
    out = []
    for name in sorted(getattr(el, "_props", {})):
        if not el._props[name].composite:
            continue
        v = el._vals.get(name)
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            out.extend(x for x in v if hasattr(x, "_props"))
        elif hasattr(v, "_props"):
            out.append(v)
    return out


def provenance(root, ids=None):
    """The v1 -> v2 record set for one transformed model.

    Each record carries ``v1_kind``/``v1_name``/``v1_path``/``v1_xmi_id``/
    ``v1_hash`` (a v1 content signature, the repair key when a path
    changes) and ``v2_kind``/``v2_element_id``. ``mapping`` is reserved for
    the mapping-class name (M2). Records come in v1 containment order; an
    element the mapping elides simply has no record (that is the elision
    ledger's job, M4).
    """
    ids = ids or assign_element_ids(root, adopt=True)
    v2_info = {}
    for el, parts, eid in _walk(root):
        if eid is None:
            eid = next((k for k, v in ids.items() if v is el), None)
        v2_info[id(el)] = (PATH_SEP.join(parts), eid)
    v1_root = getattr(root, "_v1_root", None)
    if v1_root is None:
        return []
    index = getattr(root, "_v1_index", None) or {}
    records = []
    seen = set()
    stack = [v1_root]
    while stack:
        v1 = stack.pop()
        if id(v1) in seen:
            continue
        seen.add(id(v1))
        v2 = root if v1 is v1_root else index.get(id(v1))
        info = v2_info.get(id(v2)) if v2 is not None else None
        if info is not None and info[1] is not None:
            records.append({
                "v1_kind": type(v1).__name__,
                "v1_name": getattr(v1, "name", None),
                "v1_path": info[0],
                "v1_xmi_id": getattr(v1, "_xmi_id", None),
                "v1_hash": _scalar_signature(v1),
                "v2_kind": type(v2).__name__,
                "v2_element_id": info[1],
                "mapping": None,
            })
        stack.extend(reversed(_v1_children(v1)))
    return records


def graph_hash(root, ids=None):
    """A semantic content hash over the AS graph (hex sha256).

    Element identity, metaclass, declared name, every non-derived scalar
    feature, and every reference resolved to the target's elementId —
    multi-valued features are compared as sorted sets, so tool-internal
    ordering does not change the hash (the same philosophy as
    mdzip_diff.model_hash). Call ``assign_element_ids`` first, or pass
    ``ids``.
    """
    ids = ids or assign_element_ids(root, adopt=True)
    by_el = {}
    for eid, el in ids.items():
        by_el[id(el)] = eid

    def ref_sig(v):
        if hasattr(v, "_props"):
            return "#" + (by_el.get(id(v))
                          or v._vals.get("elementId")
                          or (type(v).__name__ + ":" + str(v._vals.get("declaredName"))))
        return str(v)

    lines = []
    for el, parts, eid in _walk(root):
        eid = eid or by_el.get(id(el)) or "-"
        scal = []
        refs = []
        for name in sorted(getattr(el, "_props", {})):
            d = el._props[name]
            if d.derived or d.union or name == "elementId":
                continue
            v = el._vals.get(name)
            if v is None or name == "declaredName":
                continue
            if d.multi:
                vals = [ref_sig(x) for x in (v if isinstance(v, (list, tuple)) else [v])
                        if x is not None]
                if not vals:
                    continue
                line = name + "=[" + ",".join(sorted(vals)) + "]"
                (refs if any(x.startswith("#") for x in vals) else scal).append(line)
            else:
                line = name + "=" + ref_sig(v)
                (refs if hasattr(v, "_props") else scal).append(line)
        lines.append("|".join([type(el).__name__,
                               str(eid),
                               str(el._vals.get("declaredName")),
                               ";".join(sorted(scal)),
                               ";".join(sorted(refs))]))
    blob = "\n".join(lines)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
