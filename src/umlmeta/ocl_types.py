"""ocl_types.py — the OCL type system over the generated runtimes (O2).

Two halves:

- a **type table** built from the generated class descriptors
  (`class._props[name].t/.multi/.derived/.union`), so the type system is the
  generated hierarchy, not a hand-kept second model;
- a **checker** that walks an `ocl_ast` tree and computes the type of every
  expression, reporting diagnostics for what cannot be typed.

What the checker is for: turning the evaluator's runtime surprises into a
static list. `check_ocl.py` reports `eval-unmapped: 'Port' object has no
attribute 'encapsulatedClassifier'` *after* an attribute error; the checker
says the same thing before anything runs, with a span, and it says it for
bodies the sample model never exercises.

Diagnostics carry a severity:

- `error`   — the body cannot be right against this hierarchy (unknown
              feature, unknown type, arithmetic on a non-numeric);
- `pending` — understood but not yet supported (an operation the operation
              library owes, a type-scoped call, `@pre`). These are the O3/O4
              queue, not defects.

Nothing here evaluates; it is pure static analysis over the tree and the
descriptors. Standard library only.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from enum import Enum as _Enum

from . import derived
from . import ocl_ast as A
from . import ocl_symbols as SY


# --------------------------------------------------------------------------
# OCL types
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ClassT:
    """A metaclass of the generated hierarchy."""
    name: str
    module: str = ""


@dataclass(frozen=True, slots=True)
class PrimT:
    """Integer / Real / String / Boolean / UnlimitedNatural / OclVoid /
    OclInvalid / OclAny."""
    name: str


@dataclass(frozen=True, slots=True)
class CollT:
    """A collection: kind in Set/Bag/OrderedSet/Sequence/Collection."""
    kind: str
    element: object


@dataclass(frozen=True, slots=True)
class TupleT:
    parts: tuple


@dataclass(frozen=True, slots=True)
class UnknownT:
    """No type assigned yet — the checker stopped rather than guessing."""

    reason: str = ""

    def __repr__(self):
        return "UNKNOWN"


UNKNOWN = UnknownT()

INTEGER, REAL, STRING = PrimT("Integer"), PrimT("Real"), PrimT("String")
BOOLEAN, UNLIMITED = PrimT("Boolean"), PrimT("UnlimitedNatural")
VOID, INVALID = PrimT("OclVoid"), PrimT("OclInvalid")
ANY = PrimT("OclAny")

NUMERIC = (INTEGER, REAL, UNLIMITED)

_PY_PRIM = {bool: BOOLEAN, int: INTEGER, float: REAL, str: STRING}


def _snake(name):
    """OCL camelCase -> the repo's snake_case helper name."""
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def is_collection(t):
    return isinstance(t, CollT)


def collection_kind(t):
    return t.kind if isinstance(t, CollT) else None


def element_type(t):
    return t.element if isinstance(t, CollT) else t


# --------------------------------------------------------------------------
# descriptors -> type table
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Prop:
    name: str
    type_name: str | None      # metaclass name, or None for a primitive
    prim: str | None           # primitive OCL type name, or None
    multi: bool
    lo: int
    hi: object
    union: bool
    derived: bool
    composite: bool

    def describe(self):
        return f"{self.name}: {'*' if self.multi else '1'} {self.type_name or self.prim}"


class ModuleTable:
    """The classes, enums and properties of one generated module."""

    def __init__(self, name):
        mod = importlib.import_module("umlmeta." + name)
        self.name = name
        # the profile modules (sysml/standard_profile/uaf) carry no _CLASSES
        # registry: fall back to whatever the module itself defines
        defined = [v for v in vars(mod).values()
                   if isinstance(v, type) and getattr(v, "__module__", None)
                   == mod.__name__]
        self.classes = {c.__name__: c for c in
                        (getattr(mod, "_CLASSES", None) or defined)
                        if not issubclass(c, _Enum)}
        enum_map = getattr(mod, "_ENUMS", None)
        if enum_map is None:
            enum_map = {c.__name__: c for c in defined if issubclass(c, _Enum)}
        self.enums = {ename: [e.name for e in enum]
                      for ename, enum in enum_map.items()}
        self._props = {}

    def has(self, name):
        return name in self.classes

    def props(self, cls):
        """Merged property table for a class (base first, subclass wins)."""
        cached = self._props.get(cls.__name__)
        if cached is not None:
            return cached
        out = {}
        for base in reversed(cls.__mro__):
            for pname, d in base.__dict__.get("_props", {}).items():
                t = d.t
                prim = _PY_PRIM.get(t) if isinstance(t, type) else None
                if prim is not None:
                    out[pname] = Prop(pname, None, prim.name, d.multi, d.lo,
                                      d.hi, d.union, d.derived, d.composite)
                elif isinstance(t, str):
                    out[pname] = Prop(pname, t, None, d.multi, d.lo, d.hi,
                                      d.union, d.derived, d.composite)
                else:
                    out[pname] = Prop(pname, None, str(t), d.multi, d.lo,
                                      d.hi, d.union, d.derived, d.composite)
        self._props[cls.__name__] = out
        return out

    def is_kind(self, sub, sup):
        c = self.classes.get(sub)
        return c is not None and sup in {b.__name__ for b in c.__mro__}


class TypeTable:
    """All generated modules, resolved module-first then across."""

    def __init__(self, modules=("uml25", "sysml2", "sysml")):
        self.modules = {name: ModuleTable(name) for name in modules}
        self.order = list(modules)

    def module_of(self, cls):
        mod = (cls.__module__ or "").rsplit(".", 1)[-1]
        return self.modules.get(mod, self.modules[self.order[0]])

    def table_for(self, self_cls):
        return self.module_of(self_cls)

    def is_kind(self, sub, sup):
        """True when metaclass `sub` conforms to `sup` (same module family)."""
        found = self.resolve_class(sub)
        found_sup = self.resolve_class(sup)
        if not found or not found_sup:
            return False
        return self.modules[found[0].name].is_kind(sub, sup) or \
            found[1].__name__ == found_sup[1].__name__

    def resolve_class(self, name, prefer=None):
        """(ModuleTable, class) for a metaclass name, or None."""
        if not name:
            return None
        order = ([prefer.name] if prefer else []) + [m for m in self.order
                                                     if not prefer or m != prefer.name]
        for modname in order:
            table = self.modules[modname]
            cls = table.classes.get(name)
            if cls is not None:
                return table, cls
        return None


# --------------------------------------------------------------------------
# diagnostics
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: str          # "error" | "pending"
    message: str
    span: object = None

    def __str__(self):
        return f"{self.severity}: {self.code}: {self.message}"


_ERRORS = {"unknown-feature", "unknown-type", "arithmetic-on-non-numeric"}


# --------------------------------------------------------------------------
# return types for the operations the repo already implements
# --------------------------------------------------------------------------

def _ret_bool(*_):
    return BOOLEAN


def _ret_int(*_):
    return INTEGER


def _ret_string(*_):
    return STRING


RETURN_TYPES = {
    "qualifiedName": _ret_string, "separator": _ret_string,
    "lowerBound": _ret_int, "upperBound": _ret_int,
    "isComposite": _ret_bool, "mustBeOwned": _ret_bool,
    "isAttribute": _ret_bool, "isNavigable": _ret_bool,
    "isMultivalued": _ret_bool, "is": _ret_bool, "conformsTo": _ret_bool,
    "isDistinguishableFrom": _ret_bool, "compatibleWith": _ret_bool,
    "allInstances": lambda checker, node: CollT(
        "Set", _class_arg_type(checker, node) or UNKNOWN),
}


def _class_arg_type(checker, node):
    if isinstance(node.receiver, A.TypeRef):
        found = checker.table.resolve_class(node.receiver.name.split("::")[-1],
                                            checker.prefer)
        if found:
            return ClassT(found[1].__name__, found[0].name)
    if isinstance(node.receiver, (A.SelfProp, A.Var)) \
            and node.receiver.name[:1].isupper():
        found = checker.table.resolve_class(node.receiver.name, checker.prefer)
        if found:
            return ClassT(found[1].__name__, found[0].name)
    return None


# --------------------------------------------------------------------------
# the checker
# --------------------------------------------------------------------------

class Checker:
    """Types one body against one self type."""

    def __init__(self, table, self_cls):
        self.table = table
        self.self_cls = self_cls
        self.prefer = table.module_of(self_cls)
        self.diagnostics = []
        self._seen = set()

    # -- diagnostics --------------------------------------------------------
    def add(self, code, message, span=None):
        key = (code, message)
        if key in self._seen:
            return
        self._seen.add(key)
        sev = "error" if code in _ERRORS else "pending"
        self.diagnostics.append(Diagnostic(code, sev, message, span))

    # -- helpers ------------------------------------------------------------
    def prop(self, cls_name, feature):
        found = self.table.resolve_class(cls_name, self.prefer)
        if found is None:
            return None
        _, cls = found
        table = self.table.module_of(cls)
        return table.props(cls).get(feature)

    def prop_to_type(self, p):
        if p.type_name:
            found = self.table.resolve_class(p.type_name, self.prefer)
            base = ClassT(p.type_name, found[0].name if found else "")
        elif p.prim:
            base = PrimT(p.prim)
        else:
            base = UNKNOWN
        return CollT("Set", base) if p.multi else base

    def class_type(self, cls_name):
        found = self.table.resolve_class(cls_name, self.prefer)
        if found is None:
            return UNKNOWN
        return ClassT(found[1].__name__, found[0].name)

    def check(self, tree):
        self.type_of(tree, {"self": self.class_type(self.self_cls.__name__)})
        return self.diagnostics

    # -- the type function --------------------------------------------------
    def type_of(self, node, env):
        if node is None:
            return UNKNOWN
        fn = getattr(self, "_t_" + type(node).__name__, None)
        if fn is None:
            return UNKNOWN
        return fn(node, env)

    def _t_Literal(self, n, env):
        return {"int": INTEGER, "real": REAL, "string": STRING,
                "bool": BOOLEAN, "null": VOID, "invalid": INVALID,
                "star": UNLIMITED}.get(n.kind, UNKNOWN)

    def _t_Var(self, n, env):
        if n.name == "self":
            return env.get("self", UNKNOWN)
        return env.get(n.name, UNKNOWN)

    def _t_SelfProp(self, n, env):
        """A bare name, resolved the way OCL does it:

        enclosing binding > classifier (a type used in expression position,
        e.g. `Block.allInstances()`) > enumeration > property of self.
        """
        bound = env.get(n.name)
        if bound is not None:
            return bound
        if n.name[:1].isupper():
            found = self.table.resolve_class(n.name, self.prefer)
            if found is not None:
                return ClassT(found[1].__name__, found[0].name)
            if n.name in self.prefer.enums:
                return PrimT(n.name)
        return self.feature_on(env.get("self", UNKNOWN), n.name, n.span)

    def _t_TypeRef(self, n, env):
        found = self.table.resolve_class(n.name.split("::")[-1], self.prefer)
        if found is None:
            self.add("unknown-type", f"unknown metaclass {n.name}", n.span)
            return UNKNOWN
        return ClassT(found[1].__name__, found[0].name)

    def _t_EnumLit(self, n, env):
        table = self.prefer
        literals = table.enums.get(n.type_name)
        if literals is None:
            self.add("unknown-type",
                     f"unknown enumeration {n.type_name}", n.span)
            return UNKNOWN
        bare = [x.rstrip("_") for x in literals]
        if n.literal.rstrip("_") not in bare:
            self.add("unknown-type",
                     f"unknown literal {n.type_name}::{n.literal}", n.span)
            return UNKNOWN
        return PrimT(f"{n.type_name}::{n.literal}")

    def feature_on(self, recv_type, feature, span, via_collection=False):
        """Type of `recv.feature`, with implicit collect over collections."""
        t = recv_type
        kind = collection_kind(t)
        if kind is not None:
            t = element_type(t)
        if isinstance(t, UnknownT):
            return UNKNOWN
        if isinstance(t, PrimT):
            self.add("unknown-feature",
                     f"no feature {feature!r} on {t.name}", span)
            return UNKNOWN
        name = t.name if isinstance(t, ClassT) else None
        if name is None:
            return UNKNOWN
        p = self.prop(name, feature)
        if p is None:
            impl = _snake(feature)
            if hasattr(derived, impl):
                self.add("derived-not-wired",
                         f"{feature} is derived (derived.{impl}) and has no "
                         f"stored carrier", span)
            else:
                self.add("unknown-feature",
                         f"no feature {feature!r} on {name}", span)
            return UNKNOWN
        out = self.prop_to_type(p)
        if via_collection or kind is not None:
            out = CollT(kind or "Set", element_type(out))
        return out

    def _t_Nav(self, n, env):
        recv = self.type_of(n.receiver, env)
        if isinstance(recv, CollT):
            return CollT(recv.kind, element_type(
                self.feature_on(recv, n.feature, n.span)))
        return self.feature_on(recv, n.feature, n.span)

    def _t_Classify(self, n, env):
        recv = self.type_of(n.receiver, env)
        op = n.op
        if op == "oclType":
            return STRING
        if op == "oclIsUndefined":
            return BOOLEAN
        self._note_implicit_receiver(n.receiver, env, op)
        found = self.table.resolve_class(n.type_name.split("::")[-1],
                                         self.prefer)
        if found is None:
            self.add("unknown-type", f"unknown metaclass {n.type_name}", n.span)
            return UNKNOWN if op == "oclAsType" else BOOLEAN
        if op == "oclAsType":
            return ClassT(found[1].__name__, found[0].name)
        # a type test that cannot hold is worth saying out loud
        if isinstance(recv, ClassT):
            recv_table = self.table.module_of(
                self.table.resolve_class(recv.name, self.prefer)[1])
            if not (self.table.is_kind(recv.name, found[1].__name__)
                    or self.table.is_kind(found[1].__name__, recv.name)
                    or recv.name == found[1].__name__):
                self.add("impossible-type-test",
                         f"{recv.name}.{op}({found[1].__name__}) cannot hold "
                         f"in this hierarchy", n.span)
        return BOOLEAN

    # operations whose argument names a metaclass/literal rather than a value
    TYPE_ARG_OPS = {"selectByKind", "selectAsKind", "oclIsType", "specializes",
                    "redefines", "redefinesFromLibrary", "specializesFromLibrary",
                    "isType", "isKindOf"}

    def _t_type_argument(self, node):
        """Check a type-name argument without reading it as a feature."""
        if isinstance(node, (A.SelfProp, A.Var)) and node.name[:1].isupper():
            found = self.table.resolve_class(node.name, self.prefer)
            if found is None:
                self.add("unknown-type",
                         f"unknown metaclass {node.name}", node.span)
            return
        self.type_of(node, {"self": UNKNOWN})

    def _note_implicit_receiver(self, receiver, env, what):
        """An unqualified call inside an implicit-`it` body is lowered with
        `self` as receiver (the v0 behaviour the AST reproduces), so it
        tests self instead of the element. Flagged, and left alone until the
        interpreter owns receiver scoping (O3)."""
        if env.get("_implicit_it") and isinstance(receiver, A.Var) \
                and receiver.name == "self":
            self.add("implicit-it-receiver",
                     f"unqualified {what}(...) inside an `it` body keeps "
                     f"self as receiver", None)
        return receiver

    def _t_Call(self, n, env):
        if n.receiver is not None:
            self._note_implicit_receiver(n.receiver, env, n.name)
            self.type_of(n.receiver, env)
        for i, a in enumerate(n.args):
            if n.name in self.TYPE_ARG_OPS and i == 0:
                self._t_type_argument(a)
            else:
                self.type_of(a, env)
        ret = RETURN_TYPES.get(n.name)
        if ret is not None:
            return ret(self, n)
        if n.name in SY.DERIVED_FUNCS:
            return UNKNOWN
        self.add("unsupported-operation",
                 f"operation {n.name}() — operation library (O4)", n.span)
        return UNKNOWN

    def _t_CollectOp(self, n, env):
        recv = self.type_of(n.receiver, env)
        elem = element_type(recv)
        kind = collection_kind(recv) or "Set"
        for a in n.args:
            if isinstance(a, A.Lambda):
                inner = dict(env)
                inner[a.var] = elem
                if a.var == "it":
                    inner["_implicit_it"] = True
                self.type_of(a.body, inner)
            else:
                self.type_of(a, env)
        op = n.op
        if op in ("size", "indexOf"):
            return INTEGER
        if op in ("isEmpty", "notEmpty", "includes", "excludes", "includesAll",
                  "excludesAll", "exists", "forAll", "one", "any"):
            return BOOLEAN
        if op in ("select", "reject"):
            return CollT(kind, elem)
        if op == "collect":
            lam = n.args[0] if n.args else None
            body = UNKNOWN
            if isinstance(lam, A.Lambda):
                inner = dict(env)
                inner[lam.var] = elem
                body = self.type_of(lam.body, inner)
            return CollT("Bag", body)
        if op == "closure":
            return CollT(kind, elem)
        if op == "flatten":
            return CollT(kind, element_type(elem))
        if op in ("asSet", "asOrderedSet", "asSequence", "asBag"):
            return CollT({"asSet": "Set", "asOrderedSet": "OrderedSet",
                          "asSequence": "Sequence", "asBag": "Bag"}[op], elem)
        if op in ("first", "last", "at"):
            return elem
        if op in ("union", "intersection", "excluding", "including"):
            return CollT(kind, elem)
        if op in SY.PENDING_OPS:
            self.add("unsupported-operation", f"->{op} — collection (O3)",
                     n.span)
            return UNKNOWN
        return UNKNOWN

    def _t_BinOp(self, n, env):
        left = self.type_of(n.left, env)
        right = self.type_of(n.right, env)
        if n.op in ("and", "or", "xor", "implies", "=", "<>", "<", "<=", ">",
                    ">="):
            return BOOLEAN
        # OCL: `+`/`-` are union/difference on collections, and the KerML
        # dialect concatenates strings with `+`
        if isinstance(left, CollT) or isinstance(right, CollT):
            coll = left if isinstance(left, CollT) else right
            return CollT(coll.kind, coll.element)
        if n.op == "+" and (left == STRING or right == STRING):
            return STRING
        # only a KNOWN non-numeric operand is an error: unknown is ignorance,
        # and ignorance does not make a body wrong
        for side, t in (("left", left), ("right", right)):
            if isinstance(t, PrimT) and t not in NUMERIC:
                self.add("arithmetic-on-non-numeric",
                         f"arithmetic on {t.name} ({side} operand)", n.span)
                return UNKNOWN
        if left in NUMERIC and right in NUMERIC:
            return REAL if REAL in (left, right) else (
                UNLIMITED if UNLIMITED in (left, right) else INTEGER)
        return UNKNOWN

    def _t_Not(self, n, env):
        self.type_of(n.operand, env)
        return BOOLEAN

    def _t_Neg(self, n, env):
        t = self.type_of(n.operand, env)
        return t if t in NUMERIC else UNKNOWN

    def _t_If(self, n, env):
        self.type_of(n.cond, env)
        a = self.type_of(n.then, env)
        b = self.type_of(n.els, env)
        return a if a == b else UNKNOWN

    def _t_Let(self, n, env):
        inner = dict(env)
        for b in n.bindings:
            btype = self.type_of(b.value, inner)
            if b.type_ann:
                declared = self.declared_type(b.type_ann)
                if declared is not None:
                    btype = declared
            inner[b.pyvar] = btype
            inner[b.name] = btype
        return self.type_of(n.body, inner)

    def declared_type(self, text):
        """Best-effort parse of a `let x : T = ...` annotation."""
        text = text.strip()
        for prefix in ("OrderedSet", "Sequence", "Bag", "Set", "Collection"):
            if text.startswith(prefix + "(") and text.endswith(")"):
                inner = self.declared_type(text[len(prefix) + 1:-1])
                return CollT(prefix, inner or UNKNOWN)
        if text in ("Integer", "Real", "String", "Boolean",
                    "UnlimitedNatural"):
            return PrimT(text)
        found = self.table.resolve_class(text, self.prefer)
        return ClassT(found[1].__name__, found[0].name) if found else None

    def _t_CollectionLit(self, n, env):
        types = [self.type_of(i, env) for i in n.items]
        elem = types[0] if types and len(set(types)) == 1 else UNKNOWN
        return CollT(n.kind or "Set", elem)

    def _t_RangeLit(self, n, env):
        self.type_of(n.lo, env)
        self.type_of(n.hi, env)
        return CollT(n.kind or "Sequence", INTEGER)

    def _t_TupleLit(self, n, env):
        return TupleT(tuple((k, self.type_of(v, env)) for k, v in n.parts))

    def _t_Pre(self, n, env):
        self.add("pre-state", "@pre needs postcondition context (O3)", n.span)
        return self.type_of(n.expr, env)

    def _t_Iterate(self, n, env):
        self.type_of(n.receiver, env)
        self.add("unsupported-operation", "->iterate — collection (O3)", n.span)
        return UNKNOWN

    def _t_Lambda(self, n, env):
        inner = dict(env)
        inner[n.var] = env.get("_element", UNKNOWN)
        return self.type_of(n.body, inner)


def check_tree(tree, self_cls, table=None):
    """Type one body. Returns the diagnostics list."""
    table = table or TypeTable()
    return Checker(table, self_cls).check(tree)
