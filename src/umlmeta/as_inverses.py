"""as_inverses.py — maintain the inverse links the SysML v2 AS derives from.

The generated runtime stores one direction of every relationship. Everything
else is a derivation: `Feature.owningMembership` is the inverse of
`Membership.ownedMember`, `Feature.isEnd` is `owningMembership.oclIsKindOf(
EndFeatureMembership)`, `Connector.relatedFeature` reads the end features. A
model built by the transform sets only the forward direction, so every one of
those derivations reads null — which is why adding structure to the model did
not change a single derived property.

This module walks a model once and sets the inverses. It is deliberately a
pass over the finished model rather than code inside each helper: the helpers
build structure, this repairs the graph, and the two can be reasoned about
separately.

Standard library only.
"""
from __future__ import annotations


def _rel_kind(rel):
    return type(rel).__name__


def _set(el, prop, value):
    """Set a property if the runtime carries one; ignore if it does not."""
    props = getattr(type(el), "_props", None)
    if props is not None and prop in props:
        try:
            setattr(el, prop, value)
            return True
        except Exception:                          # noqa: BLE001
            return False
    return False


def repair(*roots):
    """Set owningRelationship / owningMembership / owningNamespace / owningType
    on every element reachable from the roots.

    Returns counts, so a caller can tell whether it did anything.
    """
    counts = {"relationship": 0, "membership": 0, "namespace": 0,
              "type": 0, "elements": 0}
    seen = set()

    def visit(el):
        if el is None or id(el) in seen:
            return
        seen.add(id(el))
        counts["elements"] += 1
        for rel in list(getattr(el, "ownedRelationship", None) or ()):
            members = list(getattr(rel, "ownedRelatedElement", None) or ())
            kind = _rel_kind(rel)
            is_membership = kind.endswith("Membership")
            is_owning = kind.startswith(("Owning", "Feature", "Parameter",
                                         "Return", "End", "StateSubaction",
                                         "Subject", "Objective", "Actor",
                                         "Requirement", "Variant", "View",
                                         "Framed", "Stakeholder"))
            for member in members:
                if _set(member, "owningRelationship", rel):
                    counts["relationship"] += 1
                if is_membership and _set(member, "owningMembership", rel):
                    counts["membership"] += 1
                if is_owning:
                    if _set(member, "owningNamespace", el):
                        counts["namespace"] += 1
                    if _set(member, "owningType", el):
                        counts["type"] += 1
                visit(member)
            # a relationship is itself an element in the graph
            visit(rel)

    for root in roots:
        visit(root)
    return counts
