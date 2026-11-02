"""ocl_parse.py — OCL tokenizer and recursive-descent parser producing
`ocl_ast` nodes.

This is the O1 replacement for the source-emitting parser that used to
live in `ocl_translator.py`: same grammar (OCL 2.4 §7.5.3 precedence,
`let` scoping, iterator expressions) but the result is a tree with source
spans, which is what a type checker and an interpreter need. The old
parser is kept under `ocl_translator.translate_legacy` as the differential
oracle for one release.

Grammar additions over the v0 parser (parse-only until O3): `Tuple{...}`
literals, `expr@pre`, `->iterate(...)`, real literals, and the
KerML-extension operation names (`selectByKind`, `specializesFromLibrary`)
which parse as ordinary calls and raise in the emitter.

Standard library only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace as dc_replace

from . import ocl_symbols as SY
from .ocl_ast import (
    BinOp, Binding, Call, Classify, CollectionLit, CollectOp, EnumLit, If,
    Iterate, Lambda, Let, Literal, Nav, Neg, Not, Pre, RangeLit, SelfProp,
    Span, TupleLit, TypeRef, UnmappedFeature, Var, dump, replace as ast_replace,
)


# --------------------------------------------------------------------------
# tokenizer
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    text: str
    start: int
    end: int


_TWO_CHAR = ("<>", "<=", ">=", "::", "..", "->")
_SINGLE = "()=<>+-*/.,:|{}@;"
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def tokenize(body):
    """Split an OCL body into tokens carrying source offsets."""
    toks = []
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c.isspace():
            i += 1
            continue
        if c == "'":
            j = body.find("'", i + 1)
            if j < 0:
                raise UnmappedFeature(
                    f"unterminated string near {body[i:i + 20]!r}")
            toks.append(Token("qstr", body[i + 1:j], i, j + 1))
            i = j + 1
            continue
        two = body[i:i + 2]
        if two == "--":                      # OCL line comment
            j = body.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if two in _TWO_CHAR:
            toks.append(Token("op", two, i, i + 2))
            i += 2
            continue
        if c == "_" and i + 1 < n and body[i + 1] == "'":
            j = body.find("'", i + 2)
            if j < 0:
                raise UnmappedFeature("unterminated _'...'")
            toks.append(Token("name", body[i + 2:j], i, j + 1))
            i = j + 1
            continue
        if c in "(),":
            toks.append(Token("paren", c, i, i + 1))
            i += 1
            continue
        if c == "|":
            toks.append(Token("bar", c, i, i + 1))
            i += 1
            continue
        if c == ":":
            toks.append(Token("colon", c, i, i + 1))
            i += 1
            continue
        if c == "{":
            toks.append(Token("lc", c, i, i + 1))
            i += 1
            continue
        if c == "}":
            toks.append(Token("rc", c, i, i + 1))
            i += 1
            continue
        if c.isdigit():
            j = i
            while j < n and body[j].isdigit():
                j += 1
            # real literal: 0.5 (but not the range operator 1..5)
            if j < n and body[j] == "." and j + 1 < n and body[j + 1].isdigit():
                k = j + 1
                while k < n and body[k].isdigit():
                    k += 1
                toks.append(Token("num", body[i:k], i, k))
                i = k
                continue
            toks.append(Token("num", body[i:j], i, j))
            i = j
            continue
        m = _NAME_RE.match(body, i)
        if m:
            toks.append(Token("name", m.group(0), i, m.end()))
            i = m.end()
            continue
        if c in _SINGLE:
            toks.append(Token("op", c, i, i + 1))
            i += 1
            continue
        raise UnmappedFeature(f"character {c!r} in {body[i:i + 30]!r}")
    toks.append(Token("eof", "", n, n))
    return toks




# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------

class Parser:
    def __init__(self, body):
        self.body = body
        self.toks = tokenize(body)
        self.i = 0
        self.uid = 0
        self.scopes = []          # (ocl name, python name)

    # -- token helpers ------------------------------------------------------
    def peek(self):
        return self.toks[self.i]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def at(self, kind, text=None):
        t = self.peek()
        return t.kind == kind and (text is None or t.text == text)

    def accept(self, kind, text=None):
        if self.at(kind, text):
            return self.next().text
        return None

    def expect(self, kind, text=None):
        t = self.accept(kind, text)
        if t is None:
            raise UnmappedFeature(
                f"expected {text or kind} at token {(self.peek().kind, self.peek().text)!r}")
        return t

    def _span(self, i0):
        start = self.toks[i0].start
        end = self.toks[self.i - 1].end if self.i else start
        return Span(start, end)

    def _s(self, node, i0):
        return dc_replace(node, span=self._span(i0))

    def _resolve(self, name):
        for ocl, py in reversed(self.scopes):
            if ocl == name:
                return py
        return None

    # -- entry --------------------------------------------------------------
    def parse(self):
        e = self.implication()
        if self.peek().kind != "eof":
            raise UnmappedFeature(
                f"trailing tokens {[(t.kind, t.text) for t in self.toks[self.i:self.i + 5]]}")
        return e

    # -- precedence ladder (OCL 2.4 §7.5.3) ---------------------------------
    def implication(self):
        i0 = self.i
        if self.at("name", "let"):
            return self.let_expression()
        left = self.or_()
        if self.accept("name", "implies"):
            return self._s(BinOp(op="implies", left=left,
                                 right=self.implication()), i0)
        return left

    def or_(self):
        i0 = self.i
        e = self.xor_()
        while self.accept("name", "or"):
            e = self._s(BinOp(op="or", left=e, right=self.xor_()), i0)
        return e

    def xor_(self):
        i0 = self.i
        e = self.and_()
        while self.accept("name", "xor"):
            e = self._s(BinOp(op="xor", left=e, right=self.and_()), i0)
        return e

    def and_(self):
        i0 = self.i
        e = self.not_()
        while self.accept("name", "and"):
            e = self._s(BinOp(op="and", left=e, right=self.not_()), i0)
        return e

    def not_(self):
        i0 = self.i
        if self.accept("name", "not"):
            return self._s(Not(operand=self.not_()), i0)
        return self.equality()

    def equality(self):
        i0 = self.i
        e = self.relational()
        while True:
            op = self.accept("op", "=") or self.accept("op", "<>")
            if op is None:
                return e
            e = self._s(BinOp(op=op, left=e, right=self.relational()), i0)

    def relational(self):
        i0 = self.i
        e = self.additive()
        for op in ("<=", ">=", "<", ">"):
            if self.accept("op", op):
                return self._s(BinOp(op=op, left=e, right=self.additive()), i0)
        return e

    def additive(self):
        i0 = self.i
        e = self.multiplicative()
        while True:
            op = self.accept("op", "+") or self.accept("op", "-")
            if op is None:
                return e
            e = self._s(BinOp(op=op, left=e, right=self.multiplicative()), i0)

    def multiplicative(self):
        i0 = self.i
        e = self.unary()
        while self.accept("op", "*"):
            e = self._s(BinOp(op="*", left=e, right=self.unary()), i0)
        return e

    def unary(self):
        i0 = self.i
        if self.accept("op", "-"):
            return self._s(Neg(operand=self.unary()), i0)
        return self.postfix()

    # -- postfix chains -----------------------------------------------------
    def postfix(self, i0=None):
        i0 = self.i if i0 is None else i0
        e = self.primary()
        while True:
            if self.accept("op", "."):
                e = self.suffix_dot(e, i0)
            elif self.accept("op", "->"):
                e = self.suffix_arrow(e, i0)
            elif self.accept("op", "@"):
                self.expect("name", "pre")
                e = self._s(Pre(expr=e), i0)
            else:
                return e

    def suffix_dot(self, recv, i0):
        name = self.expect("name")
        if self.at("paren", "("):
            return self.call(recv, name, i0)
        return self._s(Nav(receiver=recv, feature=name), i0)

    def suffix_arrow(self, recv, i0):
        name = self.expect("name")
        if not self.at("paren", "("):
            raise UnmappedFeature(f"->{name} without ()")
        return self.call(recv, name, i0)

    # -- calls --------------------------------------------------------------
    def call(self, recv, name, i0):
        self.expect("paren", "(")
        if name == "iterate":
            node = self.iterate(recv, i0)
            self.expect("paren", ")")
            return node
        args = self.arg_list(name)
        self.expect("paren", ")")
        return self.op_node(recv, name, args, i0)

    def arg_list(self, name):
        if self.at("paren", ")"):
            return []
        first = self.implication()
        vname = self._var_name(first)
        # typed iterator variable: 'v : T | body'
        if self.at("colon", ":") and vname:
            self.next()
            tname = self.expect("name")
            if not self.at("bar", "|"):
                raise UnmappedFeature("typed lambda without |")
            self.next()
            ocl = vname
            self.scopes.append((ocl, ocl))
            try:
                body = self.implication()
            finally:
                self.scopes.pop()
            args = [Lambda(var=ocl, type_ann=tname, body=body,
                           span=body.span)]
            while self.at("paren", ","):
                self.next()
                args.append(self.implication())
            return self._shape(name, args)
        # untyped iterator variable: 'v | body'
        if self.at("bar", "|") and vname:
            self.next()
            ocl = vname
            self.scopes.append((ocl, ocl))
            try:
                body = self.implication()
            finally:
                self.scopes.pop()
            args = [Lambda(var=ocl, type_ann=None, body=body,
                           span=body.span)]
            while self.at("paren", ","):
                self.next()
                args.append(self.implication())
            return self._shape(name, args)
        args = [first]
        while self.at("paren", ",") or self.at("bar", "|"):
            self.next()
            args.append(self.implication())
        return self._shape(name, args)

    def _shape(self, name, args):
        """Apply OCL's argument shapes for iterator operations
        (1 arg = implicit `it`; 2/3 args = variable form)."""
        if name not in SY.LAMBDA_OPS and name not in SY.PENDING_OPS:
            return args
        if len(args) == 1 and not isinstance(args[0], Lambda):
            body = self._rebind_it(args[0])
            return [Lambda(var="it", type_ann=None, body=body,
                           span=body.span)]
        v2 = self._var_name(args[0]) if len(args) >= 2 else None
        if len(args) == 2 and v2:
            body = self._rebind_named(args[1], v2)
            return [Lambda(var=v2, type_ann=None, body=body, span=body.span)]
        if len(args) == 3 and v2:
            body = self._rebind_named(args[2], v2)
            return [Lambda(var=v2, type_ann=None, body=body, span=body.span)]
        return args

    @staticmethod
    def _var_name(node):
        if isinstance(node, (SelfProp, Var)):
            return node.name
        return None

    def _rebind_it(self, node):
        """Implicit-`it` rebind: inside an iterator body with no declared
        variable, unqualified lower-case names AND unqualified calls belong
        to the element, not to self.

        The v0 emitter only rewrote property reads (`_g(self,'x')`), so an
        unqualified call such as `incoming->exists(oclIsKindOf(Flow))` kept
        `self` as the classification receiver and tested the wrong object.
        """
        def fn(n):
            if isinstance(n, SelfProp) and n.name[:1].islower():
                return Nav(receiver=Var(name="it"), feature=n.name,
                           span=n.span)
            if isinstance(n, (Call, CollectOp, Classify)) and n.receiver is None:
                return dc_replace(n, receiver=Var(name="it"))
            return n
        return ast_replace(node, fn)

    def _rebind_named(self, node, var):
        def fn(n):
            if isinstance(n, SelfProp) and n.name == var:
                return Var(name=var, span=n.span)
            return n
        return ast_replace(node, fn)

    def iterate(self, recv, i0):
        """`x->iterate(v : T; acc : T2 = init | body)`."""
        var = self.expect("name")
        if self.accept("colon", ":"):
            self.expect("name")
        self.expect("op", ";")
        acc = self.expect("name")
        acc_type = None
        if self.accept("colon", ":"):
            acc_type = self.expect("name")
        self.expect("op", "=")
        init = self.implication()
        self.expect("bar", "|")
        self.scopes.append((var, var))
        self.scopes.append((acc, acc))
        try:
            body = self.implication()
        finally:
            self.scopes.pop()
            self.scopes.pop()
        return self._s(Iterate(receiver=recv, var=var, acc_name=acc,
                               acc_type=acc_type, acc_init=init, body=body), i0)

    def op_node(self, recv, name, args, i0):
        """Build the call node. `recv is None` means an implicit call on
        self (OCL's unqualified form)."""
        if name in SY.COLLECTION_OPS or name in SY.PENDING_OPS:
            return self._s(CollectOp(receiver=recv, op=name,
                                     args=tuple(args)), i0)
        if name in SY.CLASSIFY_OPS:
            if name in ("oclType", "oclIsUndefined"):
                if args:
                    raise UnmappedFeature(f"{name} takes no argument")
                return self._s(Classify(receiver=recv, op=name,
                                        type_name=""), i0)
            if not args:
                raise UnmappedFeature(f"{name} without a type argument")
            return self._s(Classify(receiver=recv, op=name,
                                    type_name=self._type_arg(args[0])), i0)
        if name in SY.DERIVED_FUNCS:
            return self._s(Call(receiver=recv, name=name, args=tuple(args)), i0)
        # unknown operation: the grammar accepts it (KerML/SysML extensions
        # and the spec's helper operations), the emitter refuses to lower it
        return self._s(Call(receiver=recv, name=name, args=tuple(args)), i0)

    def _type_arg(self, node):
        if isinstance(node, (SelfProp, Var)) and node.name[:1].isupper():
            return node.name
        if isinstance(node, EnumLit):
            # qualified type: oclIsKindOf(UML::Property)
            return f"{node.type_name}::{node.literal}"
        raise UnmappedFeature(f"type argument {dump(node)!r}")

    # -- primaries ----------------------------------------------------------
    def primary(self):
        i0 = self.i
        t = self.peek()
        if t.kind == "paren" and t.text == "(":
            self.next()
            e = self.implication()
            self.expect("paren", ")")
            return self._s(e, i0)
        if t.kind == "name":
            return self.name_or_call()
        if t.kind == "qstr":
            self.next()
            return self._s(Literal(kind="string", value=t.text), i0)
        if t.kind == "num":
            self.next()
            if "." in t.text:
                return self._s(Literal(kind="real", value=float(t.text)), i0)
            return self._s(Literal(kind="int", value=int(t.text)), i0)
        if t.kind == "op" and t.text == "*":
            self.next()
            return self._s(Literal(kind="star", value="*"), i0)
        if t.kind == "lc":
            return self.collection_literal(None)
        raise UnmappedFeature(f"primary at {(t.kind, t.text)!r}")

    def name_or_call(self):
        i0 = self.i
        name = self.expect("name")
        if name == "let":
            self.i -= 1
            return self.let_expression()
        if name == "if":
            self.i -= 1
            return self.if_then_else()
        if name == "Tuple" and self.at("lc", "{"):
            return self.tuple_literal()
        if name in SY.COLLECTION_TYPES:
            if self.at("lc", "{"):
                return self.collection_literal(name)
            if self.at("paren", "("):
                # Set(Type){...}: the element type is the checker's business
                depth = 0
                while True:
                    tok = self.next()
                    if tok.kind == "eof":
                        raise UnmappedFeature("unbalanced collection type")
                    if tok.kind == "paren" and tok.text == "(":
                        depth += 1
                    elif tok.kind == "paren" and tok.text == ")":
                        depth -= 1
                        if depth == 0:
                            break
                if self.at("lc", "{"):
                    return self.collection_literal(name)
                raise UnmappedFeature(
                    f"collection type {name}(T) used as a value")
            raise UnmappedFeature(f"collection type {name} used as value")
        if name == "self":
            return Var(name="self")
        if name in SY.CONSTANTS:
            py = SY.CONSTANTS[name]
            kind = "bool" if py in ("True", "False") else (
                "invalid" if name.lower().replace("ocl", "") == "invalid"
                else "null")
            if kind == "bool":
                return self._s(Literal(kind="bool", value=py == "True"), i0)
            return self._s(Literal(kind=kind, value=None), i0)
        if self.at("op", "::"):
            parts = [name]
            while self.accept("op", "::"):
                parts.append(self.expect("name"))
            qualified = "::".join(parts)
            # `UML::Behavior.allInstances()` / `UML::Class(` is a type-scoped
            # reference, not an enumeration literal
            if self.at("op", ".") or self.at("paren", "("):
                return self._s(TypeRef(name=qualified), i0)
            return self._s(EnumLit(type_name="::".join(parts[:-1]),
                                   literal=parts[-1]), i0)
        if self.at("paren", "("):
            # no receiver node: an implicit call on self. Keeping it None
            # (rather than Var('self')) is what lets the implicit-`it`
            # rebind retarget it to the element without touching an
            # explicit `self.f()`.
            return self.call(None, name, i0)
        py = self._resolve(name)
        if py is not None:
            return self._s(Var(name=py), i0)
        if name in SY.LOCAL_BARE:
            return self._s(Call(receiver=Var(name="self"), name=name,
                                args=()), i0)
        return self._s(SelfProp(name=name), i0)

    def collection_literal(self, kind):
        i0 = self.i
        self.expect("lc", "{")
        items = []
        if not self.at("rc", "}"):
            items.append(self.implication())
            while self.at("paren", ","):
                self.next()
                items.append(self.implication())
            if self.accept("op", ".."):
                hi = self.implication()
                self.expect("rc", "}")
                return self._s(RangeLit(kind=kind, lo=items[0], hi=hi), i0)
        self.expect("rc", "}")
        return self._s(CollectionLit(kind=kind, items=tuple(items)), i0)

    def tuple_literal(self):
        i0 = self.i
        self.expect("lc", "{")
        parts = []
        if not self.at("rc", "}"):
            while True:
                pname = self.expect("name")
                self.expect("op", "=")
                parts.append((pname, self.implication()))
                if not self.at("paren", ","):
                    break
                self.next()
        self.expect("rc", "}")
        return self._s(TupleLit(parts=tuple(parts)), i0)

    def if_then_else(self):
        i0 = self.i
        self.expect("name", "if")
        cond = self.implication()
        self.expect("name", "then")
        then = self.implication()
        self.expect("name", "else")
        els = self.implication()
        self.expect("name", "endif")
        return self._s(If(cond=cond, then=then, els=els), i0)

    def let_expression(self):
        """`let a : T = e, b = e2 in body` — each value sees only the
        bindings before it; the body sees all of them. Python names are
        assigned in reverse binding order (the legacy emitter's naming, so
        the differential oracle compares equal)."""
        i0 = self.i
        self.expect("name", "let")
        raw = []          # [(name, type_ann, value node)]
        while True:
            var = self.expect("name")
            type_ann = None
            if self.at("colon", ":"):
                self.next()
                type_ann = self._skip_type()
            self.expect("op", "=")
            self.scopes.extend((n, n) for n, _t, _v in raw)
            try:
                val = self.implication()
            finally:
                del self.scopes[len(self.scopes) - len(raw):]
            raw.append((var, type_ann, val))
            if not self.at("paren", ","):
                break
            self.next()
        if not self.accept("name", "in"):
            raise UnmappedFeature("let without 'in'")
        py = {}
        for (v, _t, _val) in reversed(raw):
            self.uid += 1
            py[v] = f"_let{self.uid}_{v}"
        self.scopes.extend((v, py[v]) for v, _t, _val in raw)
        try:
            body = self.implication()
        finally:
            del self.scopes[len(self.scopes) - len(raw):]
        raw = [(v, ty, self._rename_vars(val, py))
               for v, ty, val in raw]
        bindings = tuple(Binding(name=v, type_ann=ty, value=val, pyvar=py[v],
                                 span=val.span)
                         for v, ty, val in raw)
        return self._s(Let(bindings=bindings, body=body), i0)

    @staticmethod
    def _rename_vars(node, mapping):
        def fn(n):
            if isinstance(n, Var) and n.name in mapping:
                return Var(name=mapping[n.name], span=n.span)
            return n
        return ast_replace(node, fn)

    def _skip_type(self):
        """Swallow a type annotation up to the binding '=' at paren depth 0
        (types nest parens; '=' inside a nested lambda is not the binding)."""
        depth = 0
        start = self.i
        while True:
            t = self.peek()
            if t.kind == "eof":
                raise UnmappedFeature("let without '='")
            if t.kind == "paren" and t.text == "(":
                depth += 1
            elif t.kind == "paren" and t.text == ")":
                if depth == 0:
                    raise UnmappedFeature("unbalanced let type")
                depth -= 1
            elif t.kind == "op" and t.text == "=" and depth == 0:
                break
            self.next()
        text = " ".join(x.text for x in self.toks[start:self.i]).strip()
        return text or None


def parse(body):
    """Parse an OCL body into an `ocl_ast` tree."""
    return Parser(body).parse()
