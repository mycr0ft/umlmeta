"""extent.py — the model scope OCL needs (O5a).

`allInstances()`, `selectByKind(T)` and `specializesFromLibrary(qname)` all
need something the bare-object evaluator never had: a resource. An `Extent`
is that resource — a set of roots plus the metaclass registry they came from.

Design notes that matter:

- The extent is passed explicitly (`eval_body(..., extent=...)`); the
  translator binds it for the duration of one evaluation call and restores
  the previous one, so two models in one process cannot see each other.
- Metaclass lookup is module-first: `uml25`/`sysml2`/`sysml` collide on 25
  names, so an element's own module wins.
- `specializesFromLibrary` answers from the model's *own* specialization
  graph. With no library model loaded, a user element that does not reference
  the library does not specialize it — which is exactly what the constraint
  asks, and it is returned, not assumed away.

Standard library only.
"""
from __future__ import annotations

import importlib

from . import derived as D

_MODULES = ("uml25", "sysml2", "sysml")
_REGISTRY = None


def _registry():
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = {}
        for name in _MODULES:
            mod = importlib.import_module("umlmeta." + name)
            classes = getattr(mod, "_CLASSES", None) or [
                v for v in vars(mod).values() if isinstance(v, type)]
            _REGISTRY[name] = {c.__name__: c for c in classes}
    return _REGISTRY


def module_of(cls):
    return (getattr(cls, "__module__", "") or "").rsplit(".", 1)[-1]


def metaclass(name, prefer=None):
    """The generated class called `name`, preferring `prefer`'s module."""
    reg = _registry()
    order = ([prefer] if prefer in reg else []) + [m for m in _MODULES
                                                  if m != prefer]
    for modname in order:
        cls = reg.get(modname, {}).get(name)
        if cls is not None:
            return cls
    return None


class Extent:
    """A model scope: roots + a metaclass registry + qualified-name lookup."""

    def __init__(self, *roots, prefer=None):
        self.roots = [r for r in roots if r is not None]
        self.prefer = prefer

    # -- contents -----------------------------------------------------------
    def elements(self):
        """Every element reachable by composite containment from the roots."""
        out, seen = [], set()

        def children(el):
            kids = list(D.union(el, "ownedElement"))
            # the SysML v2 AS keeps containment in ownedRelationship ->
            # (Owning)Membership.ownedRelatedElement; `ownedElement` is
            # derived there and may be empty on a freshly built model
            for rel in getattr(el, "ownedRelationship", None) or ():
                kids.append(rel)
                for sub in getattr(rel, "ownedRelatedElement", None) or ():
                    kids.append(sub)
            return kids

        def visit(el):
            if el is None or id(el) in seen:
                return
            seen.add(id(el))
            out.append(el)
            for child in children(el):
                visit(child)

        for root in self.roots:
            visit(root)
        return out

    def of_kind(self, name):
        """allInstances(T): elements of that metaclass (or a subtype)."""
        cls = metaclass(name, self.prefer)
        if cls is None:
            return []
        return [el for el in self.elements()
                if isinstance(el, cls) and id(el) not in ()]

    # -- names --------------------------------------------------------------
    def qualified(self, qname):
        for el in self.elements():
            if D.qualified_name(el) == qname:
                return el
        return None

    # -- specialization -----------------------------------------------------
    def specializes_from_library(self, el, qname):
        """Does `el` specialize the library element named `qname`?

        Walks the element's own specializations (the AS `specializes`
        chain, the v1 `general`, and the owning type) and compares qualified
        names. An element that IS the named library element counts.
        """
        if el is None:
            return False
        if D.qualified_name(el) == qname:
            return True
        seen = set()
        stack = [el]
        while stack:
            cur = stack.pop()
            if cur is None or id(cur) in seen:
                continue
            seen.add(id(cur))
            for attr in ("specializes", "general", "subtype", "generalization"):
                val = getattr(cur, attr, None)
                for target in _as_list(val):
                    if target is None:
                        continue
                    if D.qualified_name(target) == qname:
                        return True
                    stack.append(target)
            for attr in ("owningType", "owningClassifier", "owner"):
                target = getattr(cur, attr, None)
                if target is not None and id(target) not in seen:
                    stack.append(target)
        return False


def _as_list(value):
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return value
    return (value,)
