"""ocl_emit.py — backends for the OCL AST.

Two textual forms come out of the tree:

- `to_python(node)` lowers an expression to the Python source the repo
  already evaluates (`_dot`, `_nav`, `_eq`, `_d(...)`), reproducing the
  v0 translator's output. It is the compatibility path: `translate()`
  goes AST -> Python, and `translate_legacy()` stays around as the
  differential oracle.
- `to_ocl(node)` prints the tree back as OCL surface syntax. That exists
  so parse/print round-trips are a real test of the parser, and so
  diagnostics and (later) the operation library can quote what they read.

Operations with no lowering yet (`->iterate`, `->sortedBy`,
`->collectNested`, `@pre`) parse and print, but raise `UnmappedFeature`
when lowered — honest: the AST understands them, the evaluator does not
(O3/O4).

Standard library only.
"""
from __future__ import annotations

from . import ocl_symbols as SY
# dispatch is by node type name; only the classes the code isinstance-checks
# (or constructs) are imported
from .ocl_ast import (
    Lambda, Nav, SelfProp, TypeRef, UnmappedFeature, Var, Node, Call as A_Call,
    Lambda as A_Lambda, TypeRef as A_TypeRef, CollectOp as A_CollectOp,
    replace as ast_replace, fields as dc_fields,
)

# operations whose receiver is coerced to a collection before the op runs
_NAV_WRAP = {
    "size", "isEmpty", "notEmpty", "includes", "excludes", "includesAll",
    "excludesAll", "exists", "forAll", "select", "reject", "one", "any",
    "collect", "asSet", "asSequence", "asOrderedSet", "asBag", "union",
    "intersection", "flatten", "closure", "first", "last", "at", "indexOf",
    "excluding", "isUnique", "selectByType", "count",
    "collectNested",
}


def _retarget_to_e(node):
    """Re-root a closure argument chain on `e`: an unqualified name (the
    implicit self's property) becomes a navigation on `e`; explicit
    `self` references stay bound to the outer self."""
    return ast_replace(node, lambda n: (
        Nav(receiver=Var(span=None, name="e"), feature=n.name)
        if isinstance(n, SelfProp) and n.name[:1].islower() else n))


# --------------------------------------------------------------------------
# AST -> Python source
# --------------------------------------------------------------------------

def to_python(node):
    if node is None:
        return "None"
    fn = _PY.get(type(node).__name__)
    if fn is None:
        raise UnmappedFeature(f"no Python lowering for {type(node).__name__}")
    return fn(node)


def _py_literal(n):
    if n.kind == "string":
        return repr(n.value)
    if n.kind == "bool":
        return "True" if n.value else "False"
    if n.kind in ("null", "invalid"):
        return "None"
    if n.kind == "star":
        return repr("*")
    if n.kind == "real":
        return repr(n.value)
    return str(n.value)


def _py_var(n):
    return n.name


def _py_selfprop(n):
    # a derived-only property has no stored carrier: read it through
    # derived.py instead of getattr (see ocl_symbols.derived_only_props)
    fn = SY.derived_only_props().get(n.name)
    if fn is not None:
        return f"_d({fn!r}, self)"
    return f"_g(self, {n.name!r})"


def _py_typeref(n):
    return n.name


def _py_enum(n):
    return repr(n.literal)


def _py_nav(n):
    # Compatibility lowering: inside the implicit-`it` iterator form the
    # v0 translator rewrote a bare property name to a *read* on the
    # element (`_g(it, 'x')`), not to navigation (`_dot`). They differ
    # only when the feature is absent (AttributeError vs None), and the
    # OCL suite treats AttributeError as "unmapped", so the shim keeps
    # the read form until the type checker picks navigation (O2/O3).
    recv = n.receiver
    if isinstance(recv, Var) and recv.name == "it":
        return f"_g(it, {n.feature!r})"
    return f"_dot({to_python(recv)}, {n.feature!r})"


def _py_call(n):
    # a type name used as a receiver (`Property.allInstances()`) names the
    # class, not a property of self
    if n.name in ("allInstances", "instances") and n.receiver is not None \
            and not isinstance(n.receiver, A_TypeRef):
        r = n.receiver
        if isinstance(r, (SelfProp, Var)) and r.name[:1].isupper():
            return f"all_instances({r.name.split('::')[-1]!r})"
    if isinstance(n.receiver, TypeRef):
        # `UML::Association.allInstances()` — the v0 emitter passed the bare
        # class name to the (still-empty) extent stub; keep that lowering so
        # the corpus source stays comparable, and refuse the rest until the
        # metaclass registry lands (O2).
        if n.name == "allInstances" and not n.args:
            leaf = n.receiver.name.split("::")[-1]
            return f"all_instances({leaf!r})"
        raise UnmappedFeature(
            f"type-scoped call {n.receiver.name}.{n.name}() needs the "
            f"metaclass registry (O2)")
    recv = to_python(n.receiver) if n.receiver is not None else "self"
    # Class::member(args): a static member call — the helper table keys by
    # the leaf name; no receiver is passed (static defs take no self)
    if "::" in n.name and n.receiver is None:
        leaf = n.name.rsplit("::", 1)[-1]
        if leaf in SY.HELPER_OPS:
            vals = [to_python(a) for a in n.args]
            return (f"call_helper({leaf!r}"
                    + "".join(", " + a for a in vals) + ")")
    if (not n.args and n.name in SY.PROPERTY_CALLS
            and n.name not in SY.DERIVED_FUNCS
            and n.name not in SY.HELPER_OPS):
        # the corpus property-call dialect: X.feature() reads the feature
        return f"_g({recv}, {n.name!r})"
    entry = SY.DERIVED_FUNCS.get(n.name)
    if entry is None and n.name in SY.HELPER_OPS:
        # the overlay: a helper defined by an external corpus (FACE UDDL
        # `def:` declarations) — its body evaluates through call_helper,
        # never through the shared tables
        vals = [to_python(a) for a in n.args]
        return (f"call_helper({n.name!r}, {recv}"
                + "".join(", " + a for a in vals) + ")")
    if entry is None:
        if n.name in SY.PENDING_OPS:
            raise UnmappedFeature(
                f"operation {n.name} has no lowering yet (O3)")
        raise UnmappedFeature(f"operation {n.name}(")
    kind, fnname = entry
    args = []
    for i, a in enumerate(n.args):
        if isinstance(a, A_Lambda):
            # a lambda argument on a call-form operation (x->isUnique(kind)
            # parses as a Call when the grammar takes the non-iterator
            # branch): bind the RECEIVER as the iterator variable
            args.append(f"(lambda {a.var}: {to_python(a.body)})")
        elif n.name in SY.TYPE_ARG_OPS and i == 0 and \
                isinstance(a, (SelfProp, Var)):
            # a type/library name, not an expression: keep it a string —
            # but only when the name LOOKS like a type reference; a
            # lowercase property name (specializes(owningVariationUsage))
            # is an expression read on self
            if a.name[:1].isupper() or "::" in a.name:
                args.append(repr(a.name))
            else:
                args.append(to_python(a))
        else:
            args.append(to_python(a))
    if kind == "derived":
        head = f"_d({fnname!r}, {recv}"
    else:
        head = f"{fnname}({recv}"
    if args:
        return head + ", " + ", ".join(args) + ")"
    return head + ")"


def _py_collect(n):
    recv = to_python(n.receiver) if n.receiver is not None else "self"
    args = n.args
    if n.op in _NAV_WRAP:
        recv = f"_nav({recv})"
    op = n.op
    if op in SY.PENDING_OPS:
        raise UnmappedFeature(f"->{op} has no lowering yet (O3)")
    if op == "size":
        return f"len({recv})"
    if op == "isEmpty":
        return f"(len({recv}) == 0)"
    if op == "notEmpty":
        return f"(len({recv}) > 0)"
    if op in ("asSet", "asSequence", "asOrderedSet", "asBag"):
        return recv
    if op == "iterate":
        return _py_iterate(n)
    if op == "includes":
        return f"(({to_python(args[0])}) in {recv})"
    if op == "excludes":
        return f"(({to_python(args[0])}) not in {recv})"
    if op == "includesAll":
        return f"all(a in {recv} for a in ({to_python(args[0])}))"
    if op == "excludesAll":
        return f"all(a not in {recv} for a in ({to_python(args[0])}))"
    if op in ("exists", "one", "any"):
        var, body = _iterator(args, op)
        if op == "exists":
            # three-valued: a True element decides True; None propagates
            # when no element decides (any() would Python-False nulls)
            return f"_ex_ists({body} for {var} in {recv})"
        return f"(sum(1 for {var} in {recv} if ({body})) == 1)"
    if op == "forAll":
        var, body = _iterator(args, op, allow_pairs=True)
        if isinstance(var, tuple):        # the two-variable pair form
            (a, b) = var
            return f"_for_all_pairs({recv}, (lambda {a}, {b}: {body}))"
        # three-valued: a False element decides False; None (undetermined)
        # propagates when no element decides (all() would Python-False the
        # whole quantifier and pin a violation the rule text never earned)
        return (f"_for_all({body} for {var} in {recv})")
    if op == "select":
        var, body = _iterator(args, op)
        return f"[{var} for {var} in {recv} if ({body})]"
    if op == "reject":
        var, body = _iterator(args, op)
        return f"[{var} for {var} in {recv} if not ({body})]"
    if op == "collect":
        var, body = _iterator(args, op)
        return f"_collect([{body} for {var} in {recv}])"
    if op == "collectNested":
        var, body = _iterator(args, op)
        return f"([{body} for {var} in {recv}])"
    if op == "selectByType":
        # the type argument lowers as a string; _select_by_type matches
        # the runtime metaclass by name (or isinstance for a class obj).
        # A capitalized bare name is the metaclass (OCL convention)
        a0 = args[0] if args else None
        if isinstance(a0, A_TypeRef):
            return f"_select_by_type({recv}, {a0.name!r})"
        if isinstance(a0, (SelfProp, Var)) and a0.name[:1].isupper():
            return f"_select_by_type({recv}, {a0.name!r})"
        raise UnmappedFeature("->selectByType|Kind without a type")
    if op == "selectByKind":
        # arrow form is the collection filter; the bare call form (the
        # v1v2 corpus's kind predicate on the implicit element) parses as
        # a Call and lowers through DERIVED_FUNCS -> select_by_kind (the
        # dual: scalar receiver -> oclIsKindOf, list receiver -> filter)
        a0 = args[0] if args else None
        if isinstance(a0, (A_TypeRef, SelfProp, Var)) and \
                getattr(a0, "name", "")[:1].isupper():
            return f"select_by_kind({recv}, {a0.name!r})"
        raise UnmappedFeature("->selectByKind without a type")
    if op == "count":
        a = to_python(args[0])
        return f"(sum(1 for _e in {recv} if _eq(_e, ({a}))))"
    if op == "flatten":
        return f"_flatten({recv})"
    if op == "union":
        return f"_union({recv}, ({to_python(args[0])}))"
    if op == "intersection":
        return f"[a for a in {recv} if a in ({to_python(args[0])})]"
    if op == "excluding":
        return f"[a for a in {recv} if a != ({to_python(args[0])})]"
    if op == "closure":
        chain = _chain(args[0]) if args else None
        if not chain:
            # `closure(typingFeatures())` — a per-element query instead of
            # a property chain: BFS applying the query repeatedly
            a0 = args[0]
            if isinstance(a0, A_Call) and not a0.args and \
                    a0.receiver is None:
                fn = SY.DERIVED_FUNCS.get(a0.name)
                if fn is not None and fn[0] == "local":
                    return f"_closure_call({recv}, {fn[1]})"
                if a0.name in SY.HELPER_OPS:
                    return (f"_closure_call({recv}, (lambda e: "
                            f"call_helper({a0.name!r}, e)))")
            if isinstance(a0, (A_CollectOp, A_Call)):
                # the corpus closure form: an arrow chain (collection op
                # or call chain) re-rooted on the per-element var `e`; a
                # Call chain here is the selectByKind-as-kind-query shape
                arg = _retarget_to_e(a0)
                return (f"_closure_call({recv}, "
                        f"(lambda e: {to_python(arg)}))")
            if isinstance(a0, A_Lambda):
                # `->closure(pn : PathNode | ...)` — the traversal IS the
                # lambda, applied per element
                return f"_closure_call({recv}, {to_python(a0)})"
            raise UnmappedFeature(
                f"->closure({to_ocl(args[0])[:40] if args else ''})")
        return f"_closure_iter({recv}, {chain!r})"
    if op == "first":
        return f"({recv}[0] if {recv} else None)"
    if op == "last":
        return f"({recv}[-1] if {recv} else None)"
    if op == "at":
        a = to_python(args[0])
        return (f"(({recv})[{a} - 1] "
                f"if (isinstance(({a}), int) and 1 <= ({a}) <= len({recv})) "
                f"else None)")
    if op == "indexOf":
        a = to_python(args[0])
        # a non-member index is OCL Invalid -> None (three-valued): the
        # checkFeatureParameterRedefinition body guards on indexOf(self)
        # and any definite answer for an absent element invents a truth
        return (f"((({recv}).index(({a})) + 1) if (({a}) in ({recv})) "
                f"else None)")
    if op == "isUnique":
        # Collection::isUnique(lambda): no duplicated lambda results
        var, body = _iterator(args, op)
        return (f"(len({recv}) <= 1 or "
                f"len(set({body} for {var} in {recv})) == len({recv}))")
    raise UnmappedFeature(f"->{op}")


def _iterator(args, op, allow_pairs=False):
    if len(args) != 1 or not isinstance(args[0], Lambda):
        raise UnmappedFeature(f"->{op} without an iterator expression")
    lam = args[0]
    if allow_pairs and "," in (lam.var or ""):
        parts = tuple(lam.var.split(", "))
        if len(parts) == 2:
            return parts, to_python(lam.body)
        raise UnmappedFeature(f"->{op} with {len(parts)} variables")
    return lam.var, to_python(lam.body)


def _chain(node):
    """Property chain of a `->closure` argument: SelfProp/Nav spine."""
    if isinstance(node, SelfProp):
        return [node.name]
    if isinstance(node, Var) and node.name not in ("self",):
        return [node.name]
    if isinstance(node, Nav):
        head = _chain(node.receiver)
        return None if head is None else head + [node.feature]
    return None


def _py_classify(n):
    recv = to_python(n.receiver) if n.receiver is not None else "self"
    op = n.op
    if op == "oclIsKindOf":
        return f"_k({recv}, {n.type_name!r})"
    if op == "oclIsTypeOf":
        return f"_t({recv}, {n.type_name!r})"
    if op == "oclAsType":
        return f"_a({recv}, {n.type_name!r})"
    if op == "oclIsUndefined":
        return f"(({recv}) is None)"
    if op == "oclType":
        return f"type({recv}).__name__"
    raise UnmappedFeature(op)


def _py_binop(n):
    l, r = to_python(n.left), to_python(n.right)
    if n.op == "=":
        return f"(_eq({l}, {r}))"
    if n.op == "<>":
        return f"(not (_eq({l}, {r})))"
    if n.op == "xor":
        return f"(bool({l}) != bool({r}))"
    if n.op == "implies":
        # three-valued KerML implies = or(not a, b): a null antecedent is
        # UNDETERMINED (null or false is null) unless it is decided by b
        # (null or true is true) — a Python `not None` would answer True
        # and silently evaluate the consequent; the consequent is a THUNK
        # so the short-circuit survives (v0 relied on Python `or`)
        return f"_implies({l}, (lambda: {r}))"
    if n.op == "and":
        # the KerML AND table: false decides, null and true is null
        return f"_land({l}, (lambda: {r}))"
    if n.op == "or":
        # the KerML OR table: true decides, null or false is null
        return f"_lor({l}, (lambda: {r}))"
    if n.op in ("<", ">", "<=", ">="):
        # three-valued comparisons: a null operand is UNDETERMINED, not a
        # Python TypeError (KerML: size() >= invalidIndex is invalid)
        fn = {"<": "_lt", ">": "_gt", "<=": "_le", ">=": "_ge"}[n.op]
        return f"{fn}({l}, {r})"
    return f"({l} {n.op} {r})"


def _py_not(n):
    # three-valued KerML not: not null is null (undetermined), not False
    # is True — Python `not` already agrees except for None
    return f"((None if ({to_python(n.operand)}) is None else (not ({to_python(n.operand)}))))"


def _py_neg(n):
    return f"(-({to_python(n.operand)}))"


def _py_if(n):
    return (f"(({to_python(n.then)}) if ({to_python(n.cond)}) "
            f"else ({to_python(n.els)}))")


def _py_let(n):
    src = to_python(n.body)
    for b in reversed(n.bindings):
        src = f"(lambda {b.pyvar}: ({src}))({to_python(b.value)})"
    return src


def _py_collection(n):
    return "[" + ", ".join(to_python(i) for i in n.items) + "]"


def _py_range(n):
    return f"_range({to_python(n.lo)}, {to_python(n.hi)})"


def _py_tuple(n):
    body = ", ".join(f"{name!r}: {to_python(v)}" for name, v in n.parts)
    return f"_tuple({{{body}}})"


def _py_pre(n):
    raise UnmappedFeature("@pre has no lowering yet (needs postcondition "
                          "context, O3)")


def _py_iterate(n):
    """`x->iterate(v; acc : T = init | body)` — the accumulator form
    (OCL 2.4 §10.3.6): fold the body over the receiver's elements,
    starting from the accumulator initializer. Lowered to a call on a
    runtime helper so the accumulator variable binds inside the body
    exactly once, however deeply the body nests."""
    recv = to_python(n.receiver) if n.receiver is not None else "self"
    recv = f"_nav({recv})"
    body = to_python(n.body)
    init = to_python(n.acc_init)
    return (f"_iterate({recv}, {n.var!r}, {n.acc_name!r}, "
            f"({init}), {body!r})")


def _py_lambda(n):
    # a bare lambda is only meaningful as a closure traversal function
    # (`->closure(pn : PathNode | ...)`); the iterator ops consume their
    # own lambdas before to_python ever sees this node
    body = to_python(n.body)
    return f"(lambda {n.var}: {body})"


_PY = {
    "Literal": _py_literal, "Var": _py_var, "SelfProp": _py_selfprop,
    "TypeRef": _py_typeref, "EnumLit": _py_enum, "Nav": _py_nav,
    "Call": _py_call, "CollectOp": _py_collect, "Classify": _py_classify,
    "BinOp": _py_binop, "Not": _py_not, "Neg": _py_neg, "If": _py_if,
    "Let": _py_let, "CollectionLit": _py_collection, "RangeLit": _py_range,
    "TupleLit": _py_tuple, "Pre": _py_pre, "Iterate": _py_iterate,
    "Lambda": _py_lambda,
}


# --------------------------------------------------------------------------
# AST -> OCL surface syntax (round-trip printing)
# --------------------------------------------------------------------------

def to_ocl(node):
    if node is None:
        return ""
    fn = _OCL.get(type(node).__name__)
    if fn is None:
        raise UnmappedFeature(f"no OCL printing for {type(node).__name__}")
    return fn(node)


def _ocl_literal(n):
    if n.kind == "string":
        return "'" + str(n.value).replace("'", "\\'") + "'"
    if n.kind == "bool":
        return "true" if n.value else "false"
    if n.kind == "null":
        return "null"
    if n.kind == "invalid":
        return "invalid"
    if n.kind == "star":
        return "*"
    return str(n.value)


def _ocl_name(n):
    return n.name


def _ocl_enum(n):
    return f"{n.type_name}::{n.literal}"


def _ocl_nav(n):
    return f"{to_ocl(n.receiver)}.{n.feature}"


def _ocl_call(n):
    args = ", ".join(to_ocl(a) for a in n.args)
    if n.receiver is None:
        return f"{n.name}({args})"
    return f"{to_ocl(n.receiver)}.{n.name}({args})"


def _ocl_collect(n):
    args = ", ".join(to_ocl(a) for a in n.args)
    if n.receiver is None:
        # the implicit form: a bare `op(args)` call on self
        return f"{n.op}({args})"
    return f"{to_ocl(n.receiver)}->{n.op}({args})"


def _ocl_classify(n):
    if n.receiver is None:
        return f"{n.op}({n.type_name})" if n.type_name else f"{n.op}()"
    return f"{to_ocl(n.receiver)}.{n.op}({n.type_name})"


def _ocl_lambda(n):
    if n.type_ann:
        return f"{n.var} : {n.type_ann} | {to_ocl(n.body)}"
    return f"{n.var} | {to_ocl(n.body)}"


def _ocl_iterate(n):
    acc = n.acc_name + (f" : {n.acc_type}" if n.acc_type else "")
    recv = "" if n.receiver is None else f"{to_ocl(n.receiver)}->"
    return (f"{recv}iterate({n.var} ; {acc} = "
            f"{to_ocl(n.acc_init)} | {to_ocl(n.body)})")


def _ocl_binop(n):
    return f"({to_ocl(n.left)} {n.op} {to_ocl(n.right)})"


def _ocl_not(n):
    return f"not {to_ocl(n.operand)}"


def _ocl_neg(n):
    return f"-{to_ocl(n.operand)}"


def _ocl_if(n):
    return (f"if {to_ocl(n.cond)} then {to_ocl(n.then)} "
            f"else {to_ocl(n.els)} endif")


def _ocl_let(n):
    # the tree carries the generated Python names (`_let1_x`); print the
    # original OCL names so the text parses back to the same tree
    ren = {b.pyvar: b.name for b in n.bindings}

    def restore(node):
        def fn(x):
            if isinstance(x, Var) and x.name in ren:
                return Var(name=ren[x.name], span=x.span)
            return x
        return ast_replace(node, fn) if node is not None else node

    binds = []
    for b in n.bindings:
        ty = f" : {b.type_ann}" if b.type_ann else ""
        binds.append(f"{b.name}{ty} = {to_ocl(restore(b.value))}")
    return f"let {', '.join(binds)} in {to_ocl(restore(n.body))}"


def _ocl_collection(n):
    prefix = n.kind or ""
    return prefix + "{" + ", ".join(to_ocl(i) for i in n.items) + "}"


def _ocl_range(n):
    prefix = n.kind or ""
    return f"{prefix}{{{to_ocl(n.lo)}..{to_ocl(n.hi)}}}"


def _ocl_tuple(n):
    return "Tuple{" + ", ".join(f"{k} = {to_ocl(v)}" for k, v in n.parts) + "}"


def _ocl_pre(n):
    return f"{to_ocl(n.expr)}@pre"


_OCL = {
    "Literal": _ocl_literal, "Var": _ocl_name, "SelfProp": _ocl_name,
    "TypeRef": _ocl_name, "EnumLit": _ocl_enum, "Nav": _ocl_nav,
    "Call": _ocl_call, "CollectOp": _ocl_collect, "Classify": _ocl_classify,
    "Lambda": _ocl_lambda, "Iterate": _ocl_iterate, "BinOp": _ocl_binop,
    "Not": _ocl_not, "Neg": _ocl_neg, "If": _ocl_if, "Let": _ocl_let,
    "CollectionLit": _ocl_collection, "RangeLit": _ocl_range,
    "TupleLit": _ocl_tuple, "Pre": _ocl_pre,
}
