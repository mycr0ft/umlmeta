#!/usr/bin/env python
"""sync.py — diff and three-way merge for a linked v1 / v2 model pair.

Pathway: docs/v1-v2-linkage-pathway.md, milestone M3.

The problem this solves: a project re-transforms its v1 model while people
also edit the v2 model by hand. A blind re-transform destroys those v2 edits;
a blind "keep the v2 model" freezes the mapping. The merge here classifies
every element by *who changed it since the link snapshot*:

    v1 only      -> the freshly transformed element replaces the old one
    v2 only      -> the existing (edited) element is preserved verbatim
    both         -> CONFLICT: recorded, the v2 side wins (never a silent
                    overwrite, never a silent loss)
    v1 deleted   -> dropped, unless it was also edited v2-side (conflict)
    v2 native    -> kept (an element the mapping never produced)

Change detection is content-based on both sides (``signature``): scalar
features plus every reference resolved to ``target-kind:target-name``, so a
retargeted type counts as an edit. Identity comes from ``umlmeta.link``
elementIds, which are path-derived, so untouched elements keep their ids
across the re-transform (the L2 property M1 pins).

Refusals are outcomes, not exceptions: ``MergeResult.conflicts`` lists them.
"""
from __future__ import annotations

import hashlib

from . import link as L
from . import sysml2 as S2
from . import v1_to_v2_as as A


class Conflict(dict):
    """One refused merge step (``kind``, ``element_id``, ``path``, kinds)."""


class MergeResult:
    def __init__(self, root, conflicts, report):
        self.root = root            # the merged AS root
        self.conflicts = conflicts  # [Conflict]
        self.report = report        # {class: count}


def signature(el):
    """Content signature - ONE definition, shared with the provenance
    record (``umlmeta.link.signature``), so "changed" means the same thing
    on both sides of the merge."""
    return L.signature(el)


def _ids_of(root):
    return L.assign_element_ids(root, adopt=True)


_REL_SUFFIX = "Membership"


def _is_rel(el):
    """True for a relationship (membership / element end) not content."""
    tn = type(el).__name__
    return tn.endswith(_REL_SUFFIX) or tn in (
        "FeatureTyping", "Subsetting", "Redefinition", "FeatureValue",
        "Subclassification", "FeatureChaining", "ReferenceSubsetting",
        "Annotation", "Conjugation", "PortConjugation", "MultiplicityRange")


def _parents(root):
    """{id(child): (parent element, relationship kind)} for containment."""
    out = {}
    for el, _parts, eid in L._walk(root):
        for feat, child in L.contained(el):
            cid = child._vals.get("elementId")
            if cid and cid not in out:
                out[cid] = (eid, feat)
    return out


def diff_graph(old_root, new_root):
    """Element-level change set between two AS graphs, keyed by elementId.

    ``{"added": {id: kind}, "removed": {id: kind}, "changed": {id: kind}}``
    """
    old_ids = _ids_of(old_root)
    new_ids = _ids_of(new_root)
    old_sig = {i: signature(e) for i, e in old_ids.items()}
    new_sig = {i: signature(e) for i, e in new_ids.items()}
    added = {i: type(new_ids[i]).__name__ for i in new_ids.keys() - old_ids.keys()}
    removed = {i: type(old_ids[i]).__name__ for i in old_ids.keys() - new_ids.keys()}
    changed = {i: type(new_ids[i]).__name__ for i in new_ids.keys() & old_ids.keys()
               if old_sig[i] != new_sig[i]}
    return {"added": added, "removed": removed, "changed": changed}


def diff_v1(old_root, new_root):
    """Change set between two v1 snapshots, keyed by qualified path."""
    def inventory(root):
        out = {}
        stack = [root]
        seen = set()
        while stack:
            el = stack.pop()
            if id(el) in seen:
                continue
            seen.add(id(el))
            path = _v1_path(el)
            if path:
                out[path] = (type(el).__name__, L._scalar_signature(el))
            for _feat, ch in L.contained(el):
                stack.append(ch)
        return out

    old, new = inventory(old_root), inventory(new_root)
    added = {p: new[p][0] for p in new.keys() - old.keys()}
    removed = {p: old[p][0] for p in old.keys() - new.keys()}
    changed = {p: old[p][0] for p in new.keys() & old.keys()
               if old[p][1] != new[p][1]}
    return {"added": added, "removed": removed, "changed": changed}


def _v1_path(el):
    parts = []
    cur = el
    while cur is not None:
        nm = getattr(cur, "name", None)
        if isinstance(nm, str) and nm:
            parts.append(nm)
        cur = getattr(cur, "_owner", None)
    return "::".join(reversed(parts)) or None


def merge(v1_new, sidecar_doc, existing_root):
    """Three-way merge: new v1 snapshot + link sidecar + the existing v2 model.

    Returns a :class:`MergeResult` whose ``root`` is the merged AS graph.
    """
    new_root = A.transform_package(v1_new)
    new_ids = _ids_of(new_root)
    old_ids = _ids_of(existing_root)
    recs = L.records_by_id(sidecar_doc) if sidecar_doc else {}

    # current v1 signatures per v2 identity (from the fresh transform)
    cur_v1 = {r["v2_element_id"]: r["v1_hash"]
              for r in L.provenance(new_root, ids=new_ids)}

    chose_new, conflicts = set(), []
    report = {"v1-only": 0, "v2-only": 0, "unchanged": 0, "conflict": 0,
              "v1-added": 0, "v1-removed": 0, "v2-native": 0}

    def conflict(kind, eid, el):
        rec = recs.get(eid) or {}
        conflicts.append(Conflict(
            kind=kind, element_id=eid,
            path=rec.get("v1_path"),
            v1_kind=rec.get("v1_kind"),
            v2_kind=type(el).__name__))

    for eid in new_ids.keys() | old_ids.keys():
        in_new, in_old = eid in new_ids, eid in old_ids
        rec = recs.get(eid)
        if in_new and in_old:
            old_sig = signature(old_ids[eid])
            if rec is None:                       # no snapshot: v2-native
                if not _is_rel(old_ids[eid]):
                    report["v2-native"] += 1
                continue
            v1_changed = cur_v1.get(eid) != rec.get("v1_hash")
            v2_changed = old_sig != rec.get("v2_hash")
            if v1_changed and v2_changed:
                conflict("both-changed", eid, old_ids[eid])
                report["conflict"] += 1
            elif v1_changed:
                chose_new.add(eid)
                report["v1-only"] += 1
            elif v2_changed:
                report["v2-only"] += 1
            else:
                report["unchanged"] += 1
        elif in_new:
            if rec is not None:                   # element re-appeared
                chose_new.add(eid)
            report["v1-added"] += 1
        else:
            if rec is None:
                if not _is_rel(old_ids[eid]):     # keep: not from v1
                    report["v2-native"] += 1
                continue
            if signature(old_ids[eid]) != rec.get("v2_hash"):
                conflict("deleted-in-v1-edited-in-v2", eid, old_ids[eid])
                report["conflict"] += 1
            else:
                report["v1-removed"] += 1

    # ---- ancestor propagation: a re-mapped child cannot live in a preserved
    # (old-object) parent, so every ancestor of a chosen-new element is rebuilt
    # from the fresh transform too - unless that ancestor was itself edited
    # v2-side, in which case the child's change is refused and recorded.
    new_parents = _parents(new_root)
    new_by_id = {eid: el for el, _p, eid in L._walk(new_root)}

    def _content_ancestor(eid):
        """Nearest CONTENT ancestor in the fresh graph (membership levels are
        scaffolding: Engine -> FeatureMembership -> power)."""
        seen = set()
        while eid in new_parents and eid not in seen:
            seen.add(eid)
            pid = new_parents[eid][0]
            pel = new_by_id.get(pid)
            if pel is None:
                return None
            if not _is_rel(pel):
                return pid
            eid = pid
        return None

    stack = list(chose_new)
    blocked = set()
    while stack:
        eid = stack.pop()
        pid = _content_ancestor(eid)
        if pid is None or pid not in new_ids or pid not in old_ids \
                or pid in chose_new:
            continue
        rec_p = recs.get(pid)
        if rec_p is None:
            continue
        if signature(old_ids[pid]) != rec_p.get("v2_hash"):
            # container edited on the v2 side: v2 wins, the descendant's v1
            # change is refused rather than smuggled into an old subtree
            if eid not in blocked:
                blocked.add(eid)
                conflict("blocked-by-edited-container", eid, new_ids[eid])
                report["conflict"] += 1
            continue
        chose_new.add(pid)
        stack.append(pid)

    # ---- apply: the fresh transform is the skeleton; v1-only edits take the
    # fresh object, everything else keeps the existing (edited) object.
    merged = new_root
    _substitute(merged, new_ids, old_ids, chose_new, recs)
    # old-only elements that survive: v2-native content, and v1-deleted
    # elements that were edited v2-side (the conflict case). Plain v1
    # deletions need no work - the skeleton never contained them.
    keep = set()
    for eid in old_ids.keys() - new_ids.keys():
        el = old_ids[eid]
        if _is_rel(el):
            # memberships travel with their content; keeping them would drag
            # a deleted element back into the merged model
            continue
        rec = recs.get(eid)
        if rec is None or signature(el) != rec.get("v2_hash"):
            keep.add(eid)
    if keep:
        _transplant(merged, existing_root, keep, new_ids)
    L.assign_element_ids(merged, adopt=True)
    return MergeResult(merged, conflicts, report)


def _substitute(root, new_ids, old_ids, chose_new, recs):
    """Replace the fresh object with the existing one wherever v2 won."""
    for el, _parts, _eid in list(L._walk(root)):
        for rel in list(getattr(el, "ownedRelationship", None) or ()):
            lst = getattr(rel, "ownedRelatedElement", None)
            if not lst:
                continue
            for i, child in enumerate(list(lst)):
                cid = child._vals.get("elementId")
                if cid in old_ids and cid not in chose_new and cid in recs:
                    lst[i] = old_ids[cid]


def _transplant(merged, existing_root, keep_ids, new_ids):
    """Carry surviving old-only elements into the merged graph.

    The element is attached by reference: it is already a complete AS object
    with its own subtree, and a "clone this subtree" JSON round-trip would
    drag every outgoing reference (types, targets) with it and fail on the
    first one that lives outside the subtree. Its owner is looked up in the
    EXISTING graph (where it lives) and re-located in the merged skeleton by
    elementId; an element whose owner did not survive is reported by the
    merge rather than silently dropped.
    """
    from . import sysml2 as _S2

    old_parents = _parents(existing_root)
    by_id = {eid: el for el, _p, eid in L._walk(merged)}
    old_by_id = {eid: el for el, _p, eid in L._walk(existing_root)}

    def content_owner(eid):
        """Nearest ancestor that is content (memberships are scaffolding)."""
        seen = set()
        while eid in old_parents and eid not in seen:
            seen.add(eid)
            parent_id = old_parents[eid][0]
            parent = old_by_id.get(parent_id)
            if parent is None:
                return None
            if not _is_rel(parent):
                return parent_id
            eid = parent_id
        return None

    for eid in sorted(keep_ids):
        parent_id = content_owner(eid)
        parent = by_id.get(parent_id) if parent_id else None
        el = old_by_id.get(eid)
        if parent is None or el is None:
            continue
        rel = _S2.OwningMembership()
        rel.ownedRelatedElement.append(el)
        parent.ownedRelationship.append(rel)
