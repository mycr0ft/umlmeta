"""kerml_lib.py — parse the KerML/SysML model library and materialize real
library structure.

The v1->v2 transform references library elements by qualified name through
name-only stubs (_LIBRARY_DEFS). That satisfied the specializesFromLibrary
rules but left every rule that READS library structure (supertype.owned
Feature parameters, Feature::isUnique defaults, the multiplicity domain)
reading an empty shell.

This module parses the declarative surface of the .kerml and .sysml files
in the SysML-v2-Release sysml.library (packages, classifier/definition and
usage declarations, member features with modifiers/directions/types/
multiplicities, :> specializations, subsets/redefines clauses) and
materializes them into the generated sysml2 runtime classes, wired the way
the transform wires model structure:

- definition/usage members ride FeatureMembership subtypes (Subject /
  Objective / Actor / ReturnParameter / Parameter / plain Feature);
- `: Type[lo..hi]` becomes a FeatureTyping plus bound-literal memberships
  (the same shape _attach_multiplicity emits);
- `:> A, B` and `specializes A` become ownedSpecialization Subclassifications;
- modifiers with a direction (in/out/inout/return/subject/objective/actor)
  set the member direction.

Everything is cached in one IR (parsed once, cheap: the library files are
65-300 lines each) and materialized subgraphs are cached per qname in
LIBRARY_ELEMENTS. `library_element(qname)` returns the real object for any
qname the files cover, materializing its specialization ancestors; callers
fall back to name-only stubs for names outside the parsed set.

Standard library only.
"""
from __future__ import annotations

import re
from pathlib import Path


# ---------------------------------------------------------------------------
# declaration kinds -> generated runtime classes
# ---------------------------------------------------------------------------

def _cls(name):
    from . import sysml2 as _S2
    return getattr(_S2, name)


DEF_KINDS = {
    "case": "CaseDefinition", "calc": "CalculationDefinition",
    "calculation": "CalculationDefinition", "part": "PartDefinition",
    "item": "ItemDefinition", "port": "PortDefinition",
    "connection": "ConnectionDefinition", "action": "ActionDefinition",
    "state": "StateDefinition", "metadata": "MetadataDefinition",
    "view": "ViewDefinition", "viewpoint": "ViewpointDefinition",
    "rendering": "ViewRendering", "requirement": "RequirementDefinition",
    "concern": "ConcernDefinition",
    "verification case": "VerificationCaseDefinition",
    "analysis case": "AnalysisCaseDefinition",
    "use case": "UseCaseDefinition", "interface": "InterfaceDefinition",
    "allocation": "AllocationDefinition", "flow": "FlowDefinition",
    "attribute": "AttributeDefinition", "enum": "EnumerationDefinition",
    "enumeration": "EnumerationDefinition",
}

USAGE_KINDS = {
    "case": "CaseUsage", "calc": "CalculationUsage",
    "calculation": "CalculationUsage", "part": "PartUsage",
    "item": "ItemUsage", "port": "PortUsage",
    "connection": "ConnectionUsage", "action": "ActionUsage",
    "state": "StateUsage", "metadata": "MetadataUsage",
    "view": "ViewUsage", "viewpoint": "ViewpointUsage",
    "rendering": "ViewRenderingUsage", "requirement": "RequirementUsage",
    "concern": "ConcernUsage",
    "verification case": "VerificationCaseUsage",
    "analysis case": "AnalysisCaseUsage", "use case": "UseCaseUsage",
    "interface": "InterfaceUsage", "allocation": "AllocationUsage",
    "flow": "FlowUsage", "attribute": "AttributeUsage",
    "reference": "ReferenceUsage", "ref": "ReferenceUsage",
    "enumeration": "EnumerationUsage", "succession": "Succession",
    "binding": "BindingConnector", "occurrence": "ReferenceUsage",
}

# members whose membership subtype carries semantics the corpus rules read
MEMBERSHIP_KINDS = {
    "subject": "SubjectMembership", "objective": "ObjectiveMembership",
    "actor": "ActorMembership", "return": "ReturnParameterMembership",
    "in": "ParameterMembership", "out": "ParameterMembership",
    "inout": "ParameterMembership",
    "metadata": "MetadataMembership", "renderer": "ViewRenderingMembership",
    "stakeholder": "StakeholderMembership",
    "variant": "VariantMembership",
}

CONTAINER_KINDS = {"package"}

_SKIP_HEADS = {"doc", "import", "alias", "comment"}

_MODIFIERS = {"abstract", "derived", "var", "composite", "readonly",
              "nonunique", "ordered", "private", "public", "protected",
              "standard", "library", "end", "ref", "constant", "default",
              "members", "distinct", "in", "out", "inout",
              "static", "eventual", "varying", "snapshot"}

_DIRECTION_MODS = {"in": "in", "out": "out", "inout": "inout",
                   "return": "return"}


# ---------------------------------------------------------------------------
# tokenizer / declaration reader
# ---------------------------------------------------------------------------

def _strip_comments(text):
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
        elif ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


_MULT = re.compile(r"\[\s*(-?\d+|\*)\s*(\.\.\s*(-?\d+|\*))?\s*\]")


_REF_PAIR = re.compile(r"\b(in|out|inout|return)\s+ref\s+")
_IMPORT_RE = re.compile(r"\bimport\s+([A-Za-z0-9_:.*]+)\s*;?")


def _parse_decl_head(head):
    """head text (before '{' or the whole statement) -> IR fields."""
    head = _REF_PAIR.sub(r"\1 ", head)
    toks = head.replace(";", " ").split()
    if not toks:
        return None
    # peel modifiers
    i = 0
    mods = []
    while i < len(toks) and toks[i] in _MODIFIERS:
        mods.append(toks[i])
        i += 1
    if i >= len(toks):
        return None
    kind_words = []
    TWO_WORD_KINDS = {"use case", "verification case", "analysis case"}
    STATE_SUBACTION_KINDS = {"entry", "do", "exit"}
    subaction = None
    if i < len(toks) and toks[i] in STATE_SUBACTION_KINDS \
            and i + 1 < len(toks) and toks[i + 1] not in _MODIFIERS:
        # `entry action entryAction :>> 'entry';` — the state-subaction
        # keyword prefixes a usage-kind declaration
        subaction = toks[i]
        toks = toks[:i] + toks[i + 1:]
    if i < len(toks):
        kind_words.append(toks[i])
        i += 1
        if i + 1 < len(toks) and " ".join(toks[i - 1:i + 1]) in TWO_WORD_KINDS:
            kind_words.append(toks[i])
            i += 1
        if i < len(toks) and toks[i] == "def":
            kind_words.append("def")
            i += 1
    if not kind_words:
        return None
    if kind_words[0] in _SKIP_HEADS or kind_words[0] == "import":
        return None
    kind = " ".join(kind_words)
    if kind.endswith(" def"):
        kind = kind[: -len(" def")]
    is_def = head.rstrip().split()
    name = None
    rest = []
    # the name is the first token after the kind phrase
    rest_toks = toks[i:]
    if rest_toks:
        nt = rest_toks[0].strip("'")
        if ":" in nt and not nt.rstrip(":").endswith("::") and "::" not in nt:
            # `feature things: Anything...` — the colon rides the name token
            name, rest_of = nt.split(":", 1)
            name = name.strip("'")
            rest = [rest_of] + rest_toks[1:] if rest_of else rest_toks[1:]
        else:
            name = nt
            rest = rest_toks[1:]
        if name and "[" in name:
            # `result[0..*]` typed names carry the multiplicity on the name
            nm, _, _rest = name.partition("[")
            name = nm
            rest = ["[" + _rest] + rest if _rest else rest
    ir = {"kind": kind or "", "name": name, "mods": set(mods),
          "type": None, "lo": None, "hi": None,
          "specials": [], "subsets": [], "redefines": [], "chains": [],
          "members": [], "direction": None, "subaction": subaction}
    for m in mods:
        if m in _DIRECTION_MODS:
            ir["direction"] = _DIRECTION_MODS[m]
    text = " ".join(rest).strip()
    if text.startswith(":") and not text.startswith(":>"):
        text = text[1:].lstrip()
    # redefinition clause (`:>> Base::name`) and specialize/inherit clauses
    m = re.search(r":>>\s*([A-Za-z0-9_: '',]+)", text)
    if m:
        ir["redefines"] = [s.strip().strip("'").rstrip(",")
                           for s in m.group(1).split(",") if s.strip()]
        text = text[:m.start()] + text[m.end():]
    m = re.search(r":>\s*([A-Za-z0-9_: '',]+)", text)
    if m:
        ir["specials"] = [s.strip().strip("'").rstrip(",")
                          for s in m.group(1).split(",") if s.strip()]
    m = re.search(r"\bspecializes\s+([A-Za-z0-9_: '',]+)", text)
    if m:
        ir["specials"] = [s.strip().strip("'").rstrip(",")
                          for s in m.group(1).split(",") if s.strip()]
    m = re.search(r"\bsubsets\s+([A-Za-z0-9_: '.]+)", text)
    if m:
        ir["subsets"] = [s.strip().strip("'").rstrip(",")
                         for s in re.split(r"[,]\s*", m.group(1).strip())]
    m = re.search(r"\bredefines\s+([A-Za-z0-9_: ',]+)", text)
    if m:
        ir["redefines"] = [s.strip().strip("'").rstrip(",")
                           for s in m.group(1).split(",") if s.strip()]
    m = re.search(r"\bchains\s+([A-Za-z0-9_: '.]+)", text)
    if m:
        ir["chains"] = [s.strip().strip("'").rstrip(",")
                        for s in m.group(1).split(".")]
    # the multiplicity domain
    m = _MULT.search(text)
    if m:
        lo = m.group(1)
        hi = m.group(3)
        ir["lo"] = lo
        if hi is None:
            # `[n]` means n..n
            ir["hi"] = lo
        else:
            ir["hi"] = hi
        if lo == "*":
            ir["lo"] = 0
            ir["hi"] = "*"
        text = text[:m.start()] + text[m.end():]
    # the type: the first remaining token that is not a modifier
    toks = [t for t in text.replace(":", " ").split()]
    if toks:
        t0 = toks[0].strip("'")
        if t0 and t0 not in _MODIFIERS:
            ir["type"] = t0
    return ir


def _read_blocks(text):
    """Yield (head_text, body_text_or_None) for every top-level statement
    of `text` (braces balanced)."""
    i, n = 0, len(text)
    while i < n:
        # skip whitespace
        while i < n and text[i] in " \t\r\n":
            i += 1
        # gather the head up to ';' or '{'
        j = i
        while j < n and text[j] not in ";{":
            j += 1
        if j >= n:
            break
        head = text[i:j]
        if text[j] == ";":
            if head.strip():
                yield head, None
            i = j + 1
        else:
            # balanced braces
            depth = 0
            k = j
            while k < n:
                if text[k] == "{":
                    depth += 1
                elif text[k] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            yield head, text[j + 1:k]
            i = k + 1


def _walk(text, qprefix, into, container):
    """Populate `into` (dict qname->IR) with declarations under `text`,
    attaching member IRs to the container's members list."""
    for head, body in _read_blocks(text):
        toks = head.strip().split()
        if not toks:
            continue
        # strip leading noise (standard library / visibility) for dispatch
        d = 0
        while d < len(toks) and toks[d] in ("standard", "library"):
            d += 1
        first = toks[d] if d < len(toks) else None
        if first is None:
            continue
        # imports ride their own statement or trail a `doc` head — record
        # every import target into the current package scope
        m = _IMPORT_RE.search(head)
        if m:
            tgt = m.group(1).strip(";'").strip()
            if tgt:
                IN_IMPORTS.setdefault(qprefix or "__root__", []).append(tgt)
            if first == "import" or "import" in toks[d:d + 2]:
                continue
        if first in _SKIP_HEADS:
            # a `doc` statement that rides a declaration on one joined line
            # (`doc /*...*/ entry action entryAction :>> 'entry';`) — the
            # doc keyword heads the block, the declaration follows it
            if first == "doc" and body is None:
                tail = head.split(first, 1)[1]
                dr = _parse_decl_head(tail)
                if dr is not None and dr.get("name"):
                    ir = dr
                    ir["qname"] = (qprefix + "::" + ir["name"]) if qprefix \
                        else ir["name"]
                    ir["package"] = qprefix
                    if container is not None:
                        container["members"].append(ir)
                    into[ir["qname"]] = ir
            continue
        if first == "package":
            nm = toks[d + 1].strip("'") if len(toks) > d + 1 else None
            newprefix = qprefix + "::" + nm if qprefix else nm
            if body is not None:
                _walk(body, newprefix, into, None)
            continue
        ir = _parse_decl_head(head)
        if ir is None or not ir.get("name"):
            continue
        ir["qname"] = (qprefix + "::" + ir["name"]) if qprefix \
            else ir["name"]
        ir["package"] = qprefix
        if container is not None:
            container["members"].append(ir)
        into[ir["qname"]] = ir
        if body is not None:
            # nested declarations: members of this element
            _walk(body, ir["qname"], into, ir)


def parse_library(root_dir):
    """Parse every .kerml/.sysml under the library root; returns the IR
    dict qname -> declaration."""
    into = {}
    root = Path(root_dir)
    if not root.exists():
        return into
    for path in sorted(root.rglob("*.kerml")) + sorted(root.rglob("*.sysml")):
        try:
            text = _strip_comments(path.read_text(encoding="utf-8",
                                                  errors="replace"))
        except Exception:                      # noqa: BLE001
            continue
        _walk(text, None, into, None)
    return into


# ---------------------------------------------------------------------------
# materialization
# ---------------------------------------------------------------------------

LIB = {}
IN_IMPORTS = {}                # package qname -> imported qnames
PARSE_ROOT = None
LIBRARY_ELEMENTS = {}          # qname -> materialized runtime object
_IN_PROGRESS = set()


def init(root_dir):
    global LIB, PARSE_ROOT
    if root_dir and not LIB:
        LIB = parse_library(root_dir)
        PARSE_ROOT = root_dir
    return LIB


_MEMBERSHIP_DIRECTIONS = {"subject": "in", "objective": "in",
                          "actor": "in", "return": "return", "in": "in",
                          "out": "out", "inout": "inout"}


def _materialize_member(owner, ir, depth):
    """A feature declaration inside a library type: membership + member."""
    from . import sysml2 as _S2
    kind = ir["kind"]
    if ir.get("direction") is None and kind in _MEMBERSHIP_DIRECTIONS:
        ir["direction"] = _MEMBERSHIP_DIRECTIONS[kind]
    # membership subtype
    mkind = MEMBERSHIP_KINDS.get(kind)
    if mkind is None and ir.get("subaction"):
        # StateAction's `entry action entryAction` members
        mkind = "StateSubactionMembership"
    if mkind:
        m = _cls(mkind)()
        if mkind == "StateSubactionMembership" and ir.get("subaction"):
            from . import sysml2 as _S2k
            m._vals["kind"] = _S2k.StateSubactionKind.__members__[
                ir["subaction"]]
        m._vals["elementId"] = "libm:" + str(id(m))
        m._vals["owner"] = owner
        u = _usage_of(ir)
        if getattr(u, "_vals", {}).get("elementId") is None:
            u._vals["elementId"] = "lib:" + (ir.get("qname") or
                                             (owner._library_qname +
                                              "::" + str(ir["name"])))
        u._vals["owner"] = m
        m.ownedRelatedElement.append(u)
        owner.ownedRelationship.append(m)
        return u
    m = _S2.FeatureMembership()
    m._vals["elementId"] = "libm:" + str(id(m))
    m._vals["owner"] = owner
    u = _usage_of(ir)
    if getattr(u, "_vals", {}).get("elementId") is None:
        u._vals["elementId"] = "lib:" + (ir.get("qname") or
                                         (owner._library_qname +
                                          "::" + str(ir["name"])))
    u._vals["owner"] = m
    m.ownedRelatedElement.append(u)
    owner.ownedRelationship.append(m)
    return u


def _usage_of(ir):
    """The member feature for a declaration: a kind-mapped usage (or a
    plain Feature for kerml `feature` members)."""
    from . import sysml2 as _S2
    kind = ir["kind"]
    cls_name = USAGE_KINDS.get(kind)
    if cls_name is None and kind not in ("feature", "attribute", "multiplicity"):
        cls_name = USAGE_KINDS.get(kind.split()[-1])
    cls = _cls(cls_name) if cls_name else _S2.ReferenceUsage
    u = cls(declaredName=ir["name"])
    if ir.get("direction"):
        u._vals["direction"] = ir["direction"]
    return u


def _attach_specializations(target, ir, depth):
    from . import sysml2 as _S2
    for spec in ir.get("specials") or ():
        g = _resolve(spec, ir.get("package"), depth + 1)
        if g is None:
            continue
        sc = _S2.Subclassification()
        sc.general = g
        sc._vals["isImplied"] = True
        sc._vals["elementId"] = "libm:" + str(id(sc))
        sc._vals["owner"] = target
        target.ownedSpecialization.append(sc)


def _attach_mult(target, lo, hi):
    from . import sysml2 as _S2
    if lo is None and hi is None:
        return
    def _om(v):
        om = _S2.OwningMembership()
        om._vals["elementId"] = "libm:" + str(id(om))
        om._vals["owner"] = target
        lit = (_S2.LiteralInteger(value=int(v)) if v != "*"
               else _S2.LiteralInfinity())
        lit._vals["elementId"] = "libm:" + str(id(lit))
        lit._vals["owner"] = om
        om.ownedRelatedElement.append(lit)
        target.ownedRelationship.append(om)
    if lo is not None:
        _om(lo)
    if hi is not None and hi != lo:
        _om(hi)


def _lib_class_for(ir):
    kind = ir["kind"]
    if kind.endswith(" def"):
        kind = kind[: -len(" def")]
    cls_name = DEF_KINDS.get(kind)
    if cls_name is None:
        cls_name = DEF_KINDS.get(kind.split()[-1])
    if cls_name:
        return _cls(cls_name)
    if kind in ("classifier", "datatype", "class"):
        from . import sysml2 as _S2
        return _S2.Classifier
    if kind == "multiplicity":
        from . import sysml2 as _S2
        return _S2.MultiplicityRange
    if kind == "enumeration":
        return _cls("EnumerationDefinition")
    from . import sysml2 as _S2
    return _S2.Type


def _resolve(name, package, depth=0):
    """Resolve a library clause name (a specialization/redefines/type
    reference) against the IR: absolute qname, the member's package
    scope, its import statements, then a unique leaf-name fallback."""
    if name is None or depth > 24:
        return None
    if name in LIB:
        return member_or_type(name, depth + 1)
    pkg = package or "__root__"
    # a member's package is its OWNING TYPE qname; package-level names and
    # the import scope live on the enclosing FILE package — walk the chain
    pkgs = [pkg]
    cur = pkg
    while "::" in cur:
        cur = cur.rsplit("::", 1)[0]
        pkgs.append(cur)
    pkgs.append("__root__")
    for pk in pkgs:
        cand = pk + "::" + name
        if cand in LIB:
            return member_or_type(cand, depth + 1)
    for im in [x for pk in pkgs for x in IN_IMPORTS.get(pk, ())]:
        if im.endswith("::*"):
            c = im[:-2] + "::" + name
        else:
            leaf = im.rsplit("::", 1)[-1]
            if name == leaf:
                c = im
            elif name.startswith(leaf + "::"):
                c = im + name[len(leaf):]
            else:
                continue
            if c not in LIB:
                continue
        return member_or_type(c, depth + 1)
    cands = [q for q in LIB if q.rsplit("::", 1)[-1] == name]
    if len(cands) == 1:
        return member_or_type(cands[0], depth + 1)
    return None


def member_or_type(qname, depth):
    """A qname that names a MEMBER feature (its parent is a declared
    type) must resolve to the member object INSIDE the materialized
    parent — a standalone materialization would fork the feature into a
    second object and every identity-based rule (redefinition edges,
    isImplied chains, redefines-root grouping) would read a lie."""
    parent = qname.rsplit("::", 1)
    if len(parent) == 2 and parent[0] in LIB:
        leaf = parent[1]
        obj = library_element(parent[0], depth + 1)
        if obj is not None and depth + 1 <= 24:
            for rel in (obj.ownedRelationship or ()):
                for m in (getattr(rel, "ownedRelatedElement", None) or ()):
                    if getattr(m, "_vals", {}).get("declaredName") == leaf:
                        return m
            # member declarations are hydrated only on full entry — ask
            obj2 = library_element(parent[0], 0) if depth + 1 != 0 else obj
            if obj2 is not None:
                for rel in (obj2.ownedRelationship or ()):
                    for m in (getattr(rel, "ownedRelatedElement", None)
                              or ()):
                        if (getattr(m, "_vals", {}).get("declaredName")
                                == leaf):
                            return m
    return library_element(qname, depth + 1)


def _new_element(ir, shell=False):
    cls = _lib_class_for(ir)
    obj = cls(declaredName=ir["name"])
    if shell:
        obj._vals["_lib_shell"] = True
    obj._library_qname = ir["qname"]
    obj._vals["isLibraryElement"] = True
    obj._vals["elementId"] = "lib:" + ir["qname"]
    return obj


def library_element(qname, depth=0):
    """The runtime object for a library qname, or None when the parsed
    library does not declare it.

    The entry element is materialized in full: its own members carry
    typing, multiplicity and specialization edges. Everything reached
    THROUGH it (typing targets, specialization ancestors) is a shell —
    class, name, qname and specialization edges only — which is enough
    for chain walks (Extent.specializes_from_library, redefines()) while
    keeping the first-touch cost linear. The gate reads the supertype's
    parameters one hop from the model's base, which is full."""
    if qname is None or depth > 24:
        return None
    hit = LIBRARY_ELEMENTS.get(qname)
    if hit is not None:
        if depth == 0 and hit._vals.get("_lib_shell") and qname not in _IN_PROGRESS:
            # a shell materialized through some specialization chain is
            # upgraded on first full-depth demand
            ir0 = LIB.get(qname)
            if ir0 is not None:
                hit._vals.pop("_lib_shell")
                _IN_PROGRESS.add(qname)
                try:
                    for mir in ir0["members"]:
                        mem = _materialize_member(hit, mir, depth + 1)
                        _hydrate_member(mem, mir, depth + 1)
                finally:
                    _IN_PROGRESS.discard(qname)
        return hit
    ir = LIB.get(qname)
    if ir is None:
        # accept a bare leaf name within an unambiguous declaration set
        cands = [q for q in LIB if q.rsplit("::", 1)[-1] == qname]
        if len(cands) == 1:
            ir = LIB[cands[0]]
        if ir is None:
            return None
    if qname in _IN_PROGRESS:
        return None
    _IN_PROGRESS.add(qname)
    try:
        obj = _new_element(ir)
        if depth != 0:
            obj._vals["_lib_shell"] = True
        LIBRARY_ELEMENTS[ir["qname"]] = obj
        _attach_specializations(obj, ir, depth)
        if ir["kind"] == "multiplicity":
            _attach_mult(obj, ir["lo"], ir["hi"])
        if depth == 0:
            # full materialization: the entry element's own members
            for mir in ir["members"]:
                mem = _materialize_member(obj, mir, depth + 1)
                _hydrate_member(mem, mir, depth + 1)
        return obj
    finally:
        _IN_PROGRESS.discard(qname)


def _hydrate_member(mem, mir, depth):
    """Finish a member feature: typing, multiplicity, spec edges."""
    from . import sysml2 as _S2
    if mir.get("type"):
        t = _resolve(mir["type"], mir.get("package"), depth + 1)
        if t is not None:
            ft = _S2.FeatureTyping()
            ft.type = t
            ft._vals["isImplied"] = True
            ft._vals["elementId"] = "libm:" + str(id(ft))
            ft._vals["owner"] = mem
            mem.ownedTyping.append(ft)
    lo, hi = mir.get("lo"), mir.get("hi")
    if lo is not None or hi is not None:
        _attach_mult(mem, lo, hi)
    for spec in mir.get("specials") or ():
        g = _resolve(spec, mir.get("package"), depth + 1)
        if g is not None:
            sc = _S2.Subclassification() if isinstance(
                g, _S2.Classifier) else _S2.Subsetting()
            sc.general = g
            sc._vals["isImplied"] = True
            sc._vals["elementId"] = "libm:" + str(id(sc))
            sc._vals["owner"] = mem
            mem.ownedSpecialization.append(sc)
    for rd_name in mir.get("redefines") or ():
        rf = _resolve(rd_name, mir.get("package"), depth + 1)
        if rf is not None:
            rd = _S2.Redefinition()
            rd.redefinedFeature = rf
            rd._vals["subsettedFeature"] = rf
            rd.subsettingFeature = mem
            rd._vals["elementId"] = "libm:" + str(id(rd))
            rd._vals["owner"] = mem
            mem.ownedSpecialization.append(rd)


# ---------------------------------------------------------------------------

def covered(qname):
    return qname in LIB or any(
        q.rsplit("::", 1)[-1] == qname for q in LIB)