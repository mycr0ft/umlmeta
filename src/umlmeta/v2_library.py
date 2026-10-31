#!/usr/bin/env python
"""v2_library.py — resolve the SysMLv1Library references the transform carries.

Pathway: docs/v1-v2-linkage-pathway.md, milestone M5 ("library
resolvability"). The transformation maps probability/rate, the edge-weight
metadata, the port/refine/trace metadata and the allocation/variable-action
library types as NAME-ONLY carries (`SysMLv1Library::RateData`,
`SysMLv1Library::ActivityEdgeData::weight`, ...) because the library is not
input to the transformation. A v2 tool that loads the result then sees
references it cannot resolve.

This module closes that: :func:`stub_package` collects every
``SysMLv1Library::`` reference reachable from the graph (contained or merely
referenced), builds one ``SysMLv1Library`` package holding a definition per
first segment and a feature per nested name, and :func:`resolve` types the
metadata usages against those definitions. After it runs, a library-named
reference resolves inside the model - the stub is a *carry*, not an
invention: names and shapes come from the transformer's own carries.
"""
from __future__ import annotations

from . import link as L
from . import sysml2 as S2

PREFIX = "SysMLv1Library::"


def _named(el):
    n = el._vals.get("declaredName")
    return n if isinstance(n, str) and n else None


def _referenced(el):
    """Elements referenced by an element (typing, subsetting, redefinition)."""
    out = []
    for name, d in el._props.items():
        v = el._vals.get(name)
        if v is None:
            continue
        items = v if isinstance(v, (list, tuple)) else [v]
        out.extend(x for x in items if hasattr(x, "_props"))
    return out


def library_elements(roots):
    """Every element carrying a ``SysMLv1Library::`` name, in graph order.

    Walks containment AND references: the transformer creates library carriers
    standalone (a MetadataDefinition built by `_library_ref` is referenced by a
    FeatureTyping, never owned), so a containment-only walk finds nothing.
    """
    if not isinstance(roots, (list, tuple)):
        roots = [roots]
    found, seen = [], set()
    stack = list(roots)
    while stack:
        el = stack.pop()
        if id(el) in seen:
            continue
        seen.add(id(el))
        if (_named(el) or "").startswith(PREFIX):
            found.append(el)
        stack.extend(child for _feat, child in L.contained(el))
        stack.extend(_referenced(el))
    return found


def _segment(name, depth):
    segs = name.split("::")
    return "::".join(segs[:depth])


def stub_package(roots, declared_name="SysMLv1Library"):
    """Build the resolvable library package for the graph's carries.

    The elements it names are recorded on the package (``_library_elems``):
    this function RENAMES them (a usage carrying
    ``SysMLv1Library::RateData`` becomes ``RateData``), so a later
    prefix-scan for them would find nothing.
    """
    if not isinstance(roots, (list, tuple)):
        roots = [roots]
    stub = S2.Package(declaredName=declared_name)
    defs = {}

    def definition(short):
        d = defs.get(short)
        if d is None:
            d = S2.MetadataDefinition(declaredName=short)
            L_own(stub, d)
            defs[short] = d
        return d

    elems = library_elements(roots)
    stub._library_elems = elems
    for el in elems:
        name = _named(el)
        segs = name.split("::")
        if len(segs) >= 2:
            definition(segs[1])
        if len(segs) >= 3:
            parent = definition(segs[1])
            el._vals["declaredName"] = segs[2]
            L_own(parent, el)
        elif type(el).__name__ in ("MetadataDefinition", "Package"):
            continue            # the definition itself (or a nested package)
        else:
            # a usage carrying the qualified name: give it the short name so
            # the typing (added by resolve) is what identifies it
            el._vals["declaredName"] = segs[1]
    return stub


def L_own(owner, el):        # local alias keeps the import list short
    from .v1_to_v2_as import _own_membership
    return _own_membership(owner, el)


def resolve(roots, stub=None):
    """Type every library metadata usage against the stub definitions.

    Returns the stub package (built when not supplied). A usage whose declared
    name was ``SysMLv1Library::RateData`` ends up typed by the stub's
    ``RateData`` definition, so the v2 model resolves it without the source
    library.
    """
    if not isinstance(roots, (list, tuple)):
        roots = [roots]
    stub = stub or stub_package(roots)
    defs = {d._vals.get("declaredName"): d
            for d in _stub_defs(stub)}
    elems = getattr(stub, "_library_elems", None) or library_elements(roots)
    for el in elems:
        tn = type(el).__name__
        if tn not in ("MetadataUsage", "ActionUsage", "AttributeUsage"):
            continue
        name = _named(el) or ""
        if "::" in name:
            continue            # still carries the qualified name: unresolved
        target = defs.get(name)
        if target is None:
            continue            # an attribute of a definition: owned already
        if not getattr(el, "ownedTyping", None):
            ft = S2.FeatureTyping()
            ft.type = target
            el.ownedTyping.append(ft)
    return stub


def _stub_defs(stub):
    out = []
    for _rel, ch in [(r, c) for r in getattr(stub, "ownedRelationship", ())
                     for c in getattr(r, "ownedRelatedElement", ())]:
        if type(ch).__name__ in ("MetadataDefinition", "ItemDefinition"):
            out.append(ch)
    return out


def unresolved(roots, stub=None):
    """Library names still not resolvable inside the model (the M5 gate)."""
    if not isinstance(roots, (list, tuple)):
        roots = [roots]
    stub = stub or stub_package(roots)
    resolve(roots, stub)
    defs = {d._vals.get("declaredName") for d in _stub_defs(stub)}
    missing = set()
    elems = getattr(stub, "_library_elems", None) or library_elements(roots)
    for el in elems:
        name = _named(el) or ""
        if "::" in name:
            missing.add(name)
            continue
        if type(el).__name__ in ("MetadataUsage", "ActionUsage",
                                 "AttributeUsage"):
            typed = [ft for ft in (getattr(el, "ownedTyping", None) or ())]
            if not typed and name in defs:
                continue
            if name not in defs:
                missing.add(name)
    return sorted(missing)
