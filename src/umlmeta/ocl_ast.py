"""ocl_ast.py — the OCL abstract syntax tree.

Standard library only. Nodes are frozen dataclasses carrying a source
`span` (character offsets into the original body) so diagnostics can
point at the offending text — the thing the source-emitting v0 parser
could never do.

The tree is deliberately *untyped*: `SelfProp` is an unqualified name
that resolved to a property of `self`, `TypeRef` is a metaclass used as a
type argument. Type assignment is the type checker's job (O2), which is
why no node carries a type.

`dump()` produces a canonical S-expression (spans excluded) — the
equality oracle for parse/print round-trips.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields


class UnmappedFeature(Exception):
    """An OCL construct outside the implemented grammar."""


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class Node:
    """Base class: every node carries its source span."""

    span: Span | None = field(default=None, kw_only=True)


# -- leaves -----------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Literal(Node):
    """A literal: kind in int/real/string/bool/null/invalid/star.

    `star` is OCL's unbounded UnlimitedNatural (`*`), carried as the
    string "*" so multiplicity tests can compare it.
    """

    kind: str = ""
    value: object = None


@dataclass(frozen=True, slots=True)
class Var(Node):
    """A name bound by an iterator or a `let`."""

    name: str = ""


@dataclass(frozen=True, slots=True)
class SelfProp(Node):
    """An unqualified name resolved against `self`."""

    name: str = ""


@dataclass(frozen=True, slots=True)
class TypeRef(Node):
    """A metaclass name used where a type is expected."""

    name: str = ""


@dataclass(frozen=True, slots=True)
class EnumLit(Node):
    type_name: str = ""
    literal: str = ""


@dataclass(frozen=True, slots=True)
class Binding(Node):
    """One `let` binding. `pyvar` is assigned by the parser (legacy
    naming) and is what the Python backend binds."""

    name: str = ""
    type_ann: str | None = None
    value: Node | None = None
    pyvar: str = ""


# -- navigation and calls ---------------------------------------------------

@dataclass(frozen=True, slots=True)
class Nav(Node):
    """Property navigation `receiver.feature` (implicit collect when the
    receiver is multi-valued)."""

    receiver: Node | None = None
    feature: str = ""


@dataclass(frozen=True, slots=True)
class Call(Node):
    """A call. `receiver is None` means the receiver is `self`.

    Covers derived properties, local helpers and the pending extension
    operations; the emitter decides which lowering applies.
    """

    receiver: Node | None = None
    name: str = ""
    args: tuple[Node, ...] = ()


@dataclass(frozen=True, slots=True)
class CollectOp(Node):
    """An arrow operation over a collection (`->select`, `->size`)."""

    receiver: Node | None = None
    op: str = ""
    args: tuple[Node, ...] = ()


@dataclass(frozen=True, slots=True)
class Classify(Node):
    """The type-test family; the argument is a type, not an expression."""

    receiver: Node | None = None
    op: str = ""
    type_name: str = ""


@dataclass(frozen=True, slots=True)
class Lambda(Node):
    """An iterator expression: `var | body` or `var : T | body`.

    `var == "it"` is the implicit form.
    """

    var: str = ""
    type_ann: str | None = None
    body: Node | None = None


@dataclass(frozen=True, slots=True)
class Iterate(Node):
    """`x->iterate(v; acc : T = init | body)` — the accumulator form."""

    receiver: Node | None = None
    var: str = ""
    acc_name: str = ""
    acc_type: str | None = None
    acc_init: Node | None = None
    body: Node | None = None


# -- operators --------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BinOp(Node):
    op: str = ""
    left: Node | None = None
    right: Node | None = None


@dataclass(frozen=True, slots=True)
class Not(Node):
    operand: Node | None = None


@dataclass(frozen=True, slots=True)
class Neg(Node):
    operand: Node | None = None


# -- structure --------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class If(Node):
    cond: Node | None = None
    then: Node | None = None
    els: Node | None = None


@dataclass(frozen=True, slots=True)
class Let(Node):
    bindings: tuple[Binding, ...] = ()
    body: Node | None = None


@dataclass(frozen=True, slots=True)
class CollectionLit(Node):
    """`kind{items}`; kind is None for a bare `{...}` literal."""

    kind: str | None = None
    items: tuple[Node, ...] = ()


@dataclass(frozen=True, slots=True)
class RangeLit(Node):
    """`kind{lo..hi}` (a range literal; the kind is the prefix, if any)."""

    kind: str | None = None
    lo: Node | None = None
    hi: Node | None = None


@dataclass(frozen=True, slots=True)
class TupleLit(Node):
    parts: tuple[tuple[str, Node], ...] = ()


@dataclass(frozen=True, slots=True)
class Pre(Node):
    """`expr@pre`: the value in the precondition state."""

    expr: Node | None = None


# -- utilities --------------------------------------------------------------

def walk(node):
    """Yield every node in the tree, pre-order."""
    if node is None:
        return
    yield node
    for f in fields(node):
        v = getattr(node, f.name)
        if isinstance(v, Node):
            yield from walk(v)
        elif isinstance(v, tuple):
            for item in v:
                if isinstance(item, Node):
                    yield from walk(item)
                elif isinstance(item, tuple):
                    for sub in item:
                        if isinstance(sub, Node):
                            yield from walk(sub)


def dump(node):
    """Canonical S-expression for structural comparison (spans dropped)."""
    if node is None:
        return "nil"
    name = type(node).__name__
    parts = []
    for f in fields(node):
        if f.name == "span":
            continue
        v = getattr(node, f.name)
        if isinstance(v, Node):
            parts.append(dump(v))
        elif isinstance(v, tuple):
            inner = []
            for item in v:
                if isinstance(item, Node):
                    inner.append(dump(item))
                elif isinstance(item, tuple):
                    inner.append(dump_list(item))
                else:
                    inner.append(repr(item))
            parts.append("(" + " ".join(inner) + ")")
        else:
            parts.append(repr(v))
    return "(" + name + (" " + " ".join(parts) if parts else "") + ")"


def dump_list(items):
    out = []
    for item in items:
        out.append(dump(item) if isinstance(item, Node) else repr(item))
    return "[" + " ".join(out) + "]"


def replace(node, fn):
    """Rebuild the tree applying `fn` bottom-up (used by the implicit-`it`
    rebind, which has to rewrite unqualified names after the fact)."""
    if not isinstance(node, Node):
        return node
    kwargs = {}
    for f in fields(node):
        if f.name == "span":
            continue
        v = getattr(node, f.name)
        if isinstance(v, Node):
            kwargs[f.name] = replace(v, fn)
        elif isinstance(v, tuple):
            new = []
            for item in v:
                if isinstance(item, Node):
                    new.append(replace(item, fn))
                elif isinstance(item, tuple):
                    new.append(tuple(replace(x, fn) if isinstance(x, Node)
                                     else x for x in item))
                else:
                    new.append(item)
            kwargs[f.name] = tuple(new)
        else:
            kwargs[f.name] = v
    rebuilt = type(node)(span=node.span, **kwargs)
    return fn(rebuilt)
