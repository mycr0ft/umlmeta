"""stereotype.py — materialize stereotype applications as objects (S1).

The XMI reader records applications as metadata: `model.apps` maps a base
xmi:id to `(profile, stereotype, app_id)` triples, `app_metas` names the
`base_<Metaclass>` end, and `app_tags` carries the tagged values. That is
enough to *type* a stereotype constraint (the profile generator now emits the
extension ends) but not to *evaluate* one: there is no object to be `self`.

This module builds those objects. For every application it instantiates the
generated stereotype class, sets the `base_<Metaclass>` property to the
stereotyped element and applies the tagged values with the declared types, so
a stereotype constraint can be checked with `self` bound to the stereotype —
which is how SysML v1 says a stereotype constraint is read.

What is deliberately NOT done here:

- no synthesis of a stereotype object when the profile is unknown to the
  tree (`updm` stereotypes in a UAF-era file resolve only if the generated
  modules carry them) — those are reported, never guessed;
- no mutation of the base element's own properties; the instance lives
  beside it (`_stereotype_instances`), exactly like the applications the
  reader already recorded.

Standard library only.
"""
from __future__ import annotations

import importlib

INSTANCES = "_stereotype_instances"

_PROFILE_MODULES = ("sysml", "standard_profile", "uaf", "uaf13")


# --------------------------------------------------------------------------
# profile class lookup
# --------------------------------------------------------------------------

def load_profiles(modules=_PROFILE_MODULES):
    """{stereotype name: [(module name, class, _STEREO), ...]}"""
    index = {}
    for name in modules:
        try:
            mod = importlib.import_module("umlmeta." + name)
        except ImportError:                      # pragma: no cover
            continue
        for cls in getattr(mod, "_STEREOTYPES", ()) or ():
            stereo = getattr(cls, "_STEREO", "")
            if not stereo:
                continue
            index.setdefault(stereo.rsplit("::", 1)[-1], []).append(
                (name, cls, stereo))
    return index


def find_class(index, stereo, profile=None):
    """The generated class for an application's (profile, stereotype)."""
    candidates = index.get(stereo) or []
    if not candidates:
        return None
    if profile:
        want = profile.lower()
        for entry in candidates:
            first = entry[2].split("::", 1)[0].lower()
            if first == want or want.endswith(first):
                return entry
    return candidates[0]


# --------------------------------------------------------------------------
# tagged values
# --------------------------------------------------------------------------

def _coerce(prop, text):
    """Tagged value text -> the property's declared Python type.

    The generated descriptors carry the target as a Python type (`bool`,
    `int`, `float`, `str`) in `_Ref.t`, so the coercion is by that type.
    """
    if prop is None:
        return text
    t = getattr(prop, "t", None)
    raw = str(text).strip()
    if t is bool:
        return raw.lower() in ("true", "1")
    if t is int:
        try:
            return int(raw)
        except ValueError:
            return text
    if t is float:
        try:
            return float(raw)
        except ValueError:
            return text
    return text


# --------------------------------------------------------------------------
# materialization
# --------------------------------------------------------------------------

class Instance:
    """One applied stereotype: the generated object plus its provenance."""

    __slots__ = ("base", "stereotype", "profile", "app_id", "obj", "module")

    def __init__(self, base, stereotype, profile, app_id, obj, module):
        self.base = base
        self.stereotype = stereotype
        self.profile = profile
        self.app_id = app_id
        self.obj = obj
        self.module = module

    def __repr__(self):
        name = getattr(self.base, "name", None)
        return (f"<Instance {self.profile}::{self.stereotype} "
                f"on {type(self.base).__name__} {name!r}>")


def materialize(model, index=None):
    """Build an Instance per application; returns a report dict.

    `report["instances"]` — the built objects, in application order.
    `report["unresolved"]` — (profile, stereotype, app_id, base) triples whose
    stereotype class is not in the tree.
    `report["untagged"]` — (instance, tag) pairs whose tag has no property.
    """
    index = index if index is not None else load_profiles()
    instances, unresolved, untagged = [], [], []
    for base_id, triples in (getattr(model, "apps", None) or {}).items():
        base = model.objects.get(base_id)
        if base is None:
            continue
        for profile, stereo, app_id in triples:
            entry = find_class(index, stereo, profile)
            if entry is None:
                unresolved.append((profile, stereo, app_id, base))
                continue
            modname, cls, _label = entry
            try:
                obj = cls()
            except Exception:                    # pragma: no cover
                unresolved.append((profile, stereo, app_id, base))
                continue
            feature = (getattr(model, "app_metas", None) or {}).get(app_id)
            if feature:
                try:
                    setattr(obj, feature, base)
                except Exception:                # pragma: no cover
                    pass
            props = getattr(cls, "_props", {}) or {}
            for tag, value in ((getattr(model, "app_tags", None) or {})
                               .get(app_id) or {}).items():
                prop = props.get(tag)
                if prop is None:
                    untagged.append(((profile, stereo, app_id), tag))
                    continue
                try:
                    setattr(obj, tag, _coerce(prop, value))
                except Exception as ex:          # noqa: BLE001
                    untagged.append(((profile, stereo, app_id), tag, str(ex)))
            inst = Instance(base, stereo, profile, app_id, obj, modname)
            instances.append(inst)
            bucket = getattr(base, INSTANCES, None)
            if bucket is None:
                bucket = []
                try:
                    setattr(base, INSTANCES, bucket)
                except Exception:                # pragma: no cover
                    continue
            bucket.append(inst)
    return {"instances": instances, "unresolved": unresolved,
            "untagged": untagged}


def instances_of(element):
    """The stereotype instances applied to one element."""
    return list(getattr(element, INSTANCES, ()) or ())


def check(model, derived=None, index=None):
    """Evaluate every materialized instance's constraints.

    Returns (ok, results, skipped, report) where results are
    (instance, class name, constraint name, value) and skipped are
    (instance, constraint name, reason).
    """
    from . import derived as derived_mod
    from . import ocl_translator as T

    derived = derived or derived_mod
    report = materialize(model, index)
    results, skipped = [], []
    for inst in report["instances"]:
        ok, res, skip = T.check_constraints(inst.obj, derived)
        for cls_name, cname, body, value in res:
            results.append((inst, cls_name, cname, value))
        for cname, body, reason in skip:
            skipped.append((inst, cname, reason))
    return (all(v for _, _, _, v in results), results, skipped, report)
