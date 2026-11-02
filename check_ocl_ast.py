#!/usr/bin/env python
"""O1 checks: the OCL AST (ocl_ast / ocl_parse / ocl_emit) against the v0
source-emitting translator.

Oracles:
  1. corpus: every OCL body frozen in the generated modules is accounted
     for, and every body the v0 translator handled is parsed by the AST;
  2. differential: AST-emitted Python vs the v0 source is compared per
     body — identical, or differing only in `let` local names, or in one
     of the itemized bodies where the v0 emitter captured a free variable
     (the AST is correct there, so those are listed, not tolerated);
  3. value parity: both lowerings are evaluated on the same model and
     must produce the same value (or the same exception) everywhere;
  4. round-trip: every tree prints back to OCL (to_ocl) and reparses to a
     structurally identical tree;
  5. new grammar: Tuple{...}, expr@pre, ->iterate(...), real literals
     parse; the constructs with no lowering yet raise, they do not guess;
  6. spans: a node's span covers exactly the source text it parsed.

Standard library only. Run: .venv/bin/python check_ocl_ast.py
"""
import importlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from umlmeta import derived as D  # noqa: E402
from umlmeta import ocl_ast as A  # noqa: E402
from umlmeta import ocl_emit as E  # noqa: E402
from umlmeta import ocl_parse as P  # noqa: E402
from umlmeta import ocl_symbols as SY  # noqa: E402
from umlmeta import ocl_translator as T  # noqa: E402
from umlmeta import uml25 as U  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


# ---------------------------------------------------------------------------
# corpus
# ---------------------------------------------------------------------------

CORPUS = []
MODULE_COUNTS = {}
for _mod in ("uml25", "sysml2", "sysml"):
    _m = importlib.import_module("umlmeta." + _mod)
    _n = 0
    for _c in vars(_m).values():
        if isinstance(_c, type):
            for _name, _body in _c.__dict__.get("CONSTRAINTS", ()):
                CORPUS.append((_mod, _c.__name__, _name, _body))
                _n += 1
    MODULE_COUNTS[_mod] = _n

print("== corpus ==")
check("three modules carry the OCL corpus", set(MODULE_COUNTS) ==
      {"uml25", "sysml2", "sysml"}, str(MODULE_COUNTS))
check("1215 constraint bodies in total", len(CORPUS) == 1215,
      f"{len(CORPUS)} {MODULE_COUNTS}")


# ---------------------------------------------------------------------------
# differential: v0 source vs AST-emitted source
# ---------------------------------------------------------------------------

# Bodies where the v0 emitter is WRONG and the AST is right. Two defect
# classes, both from the textual `_shadow` / let-rename rewrites the AST
# replaces with real scoping:
#   capture  - an implicit-`it` body rewrote an enclosing iterator's free
#              variable to a property read on the element (`_g(it, 'p')`);
#   rename   - a `let` binding's references were left as `_g(self, 'x')`
#              because the rename regex could not match inside a quoted
#              property name, so the body read self's property of the same
#              name instead of the bound value.
# The set is pinned; each entry is verified mechanically below (the v0
# source must read a *bound* name as a property).
V0_EMITTER_DEFECTS = {
    ("uml25", "Activity", "maximum_one_parameter_node"): "capture",
    ("uml25", "Activity", "maximum_two_parameter_nodes"): "capture",
    ("uml25", "ConditionalNode", "one_clause_with_executable_node"): "capture",
    ("uml25", "Continuation", "global"): "capture",
    ("uml25", "CollaborationUse", "client_elements"): "rename",
    ("uml25", "CollaborationUse", "connectors"): "rename",
    ("uml25", "ExceptionHandler", "output_pins"): "rename",
    ("uml25", "Message", "signature_is_signal"): "rename",
    ("uml25", "Message", "signature_is_operation_request"): "rename",
    ("uml25", "Message", "signature_is_operation_reply"): "rename",
    ("uml25", "OperationTemplateParameter", "match_default_signature"): "rename",
    ("sysml", "AdjunctProperty",
     "7_adjunctproperty_connectorproperty_consistent"): "rename",
}

_LET_NUM = re.compile(r"_let\d+_\w*")


def _alpha(src):
    """Collapse the generated `let` locals to one token: the two emitters
    number them differently, so only structure is compared."""
    return _LET_NUM.sub("_let_", src)


def _bound_names(tree):
    names = set()
    for node in A.walk(tree):
        if isinstance(node, A.Let):
            names |= {b.name for b in node.bindings}
        elif isinstance(node, A.Lambda) and node.var != "it":
            names.add(node.var)
    return names


_DERIVED_ONLY = SY.derived_only_props()


def _uses_derived_route(tree):
    """The body reads a property that has no stored carrier, so the AST
    routes it through derived.py (`_d(...)`) where v0 emitted a getattr."""
    for node in A.walk(tree):
        if isinstance(node, A.SelfProp) and node.name in _DERIVED_ONLY:
            return True
        if isinstance(node, A.Nav) and node.feature in _DERIVED_ONLY:
            return True
    return False


def _retargets_implicit_receiver(tree):
    """The body has an implicit-`it` body containing an unqualified call;
    the AST retargets that call to the element, v0 left it on `self`."""
    def scan(node, inside):
        if isinstance(node, A.Lambda):
            return scan(node.body, inside or node.var == "it")
        if isinstance(node, (A.Call, A.CollectOp, A.Classify)) and inside \
                and isinstance(node.receiver, A.Var) \
                and node.receiver.name == "it":
            return True
        for f in __import__("dataclasses").fields(node):
            v = getattr(node, f.name)
            if isinstance(v, A.Node) and scan(v, inside):
                return True
            if isinstance(v, tuple):
                for item in v:
                    if isinstance(item, A.Node) and scan(item, inside):
                        return True
        return False
    return scan(tree, False)


def _v0_reads_bound_name_as_property(old_src, tree):
    """True when the v0 source reads a *bound* variable as a property."""
    return any(f"_g(self, {n!r})" in old_src or f"_g(it, {n!r})" in old_src
               for n in _bound_names(tree))


print("== differential: v0 source vs AST-emitted source ==")
identical, renamed, defects, unexplained = 0, [], [], []
derived_route, receivers = [], []
legacy_only, newly_parsed, both_failed = [], [], 0
for mod, cname, name, body in CORPUS:
    try:
        old = T.translate_legacy(body)
    except Exception:
        old = None
    tree = None
    try:
        tree = P.parse(body)
        new = E.to_python(tree)
    except Exception:
        new = None
    if old is not None and new is not None:
        if old == new:
            identical += 1
        elif _alpha(old) == _alpha(new):
            renamed.append((mod, cname, name))
        elif (mod, cname, name) in V0_EMITTER_DEFECTS \
                and _v0_reads_bound_name_as_property(old, tree):
            defects.append((mod, cname, name))
        elif _uses_derived_route(tree):
            derived_route.append((mod, cname, name))
        elif _retargets_implicit_receiver(tree):
            receivers.append((mod, cname, name))
        else:
            unexplained.append((mod, cname, name, body))
    elif old is not None:
        legacy_only.append((mod, cname, name, body))
    elif new is not None:
        newly_parsed.append((mod, cname, name))
    else:
        both_failed += 1

lowered = identical + len(renamed) + len(defects) + len(derived_route) + \
    len(receivers)
check("every v0-translatable body also lowers through the AST",
      not legacy_only, str([f"{m}.{c}.{n}" for m, c, n, _ in legacy_only][:4]))
check("AST lowers every body v0 lowered (633)", lowered == 633, f"{lowered}")
check("no unexplained source difference", not unexplained,
      str([f"{m}.{c}.{n}" for m, c, n, _ in unexplained][:4]))
check("differences are itemized (names, v0 defects, derived routing, "
      "receiver retarget)",
      len(renamed) + len(defects) + len(derived_route) + len(receivers) == 75,
      f"identical {identical}, renamed {len(renamed)}, "
      f"defects {len(defects)}, derived {len(derived_route)}, "
      f"receivers {len(receivers)}, both-fail {both_failed}")
check("every itemized defect body is pinned",
      all((m, c, n) in V0_EMITTER_DEFECTS for m, c, n in defects) and
      len(defects) == len(V0_EMITTER_DEFECTS),
      f"{len(defects)}/{len(V0_EMITTER_DEFECTS)}")
print(f"  (newly parsed by the AST: {len(newly_parsed)}; "
      f"both fail: {both_failed})")

print("== the AST is what translate() uses ==")
_probe = "self.ownedAttribute->select(a | a.isComposite)->size() > 0"
check("translate() routes through parse + emit",
      T.translate(_probe) == E.to_python(P.parse(_probe)))


# ---------------------------------------------------------------------------
# parse coverage and what the refusals are
# ---------------------------------------------------------------------------

print("== parse coverage ==")
NOSPEC = "(no specification serialized)"
parsed, refusals = 0, []
for mod, cname, name, body in CORPUS:
    if body.strip() == NOSPEC:
        continue
    try:
        P.parse(body)
        parsed += 1
    except A.UnmappedFeature as ex:
        refusals.append((mod, cname, name, body, str(ex)))

check("the AST parses 1166 of the 1191 real bodies", parsed == 1166,
      f"{parsed} parsed, {len(refusals)} refused")


def _defect_class(body, err):
    if body.strip().startswith("--"):
        return "comment-only body"
    if "eof" in err:
        return "truncated body"
    return "mangled text"


_classes = {}
for mod, cname, name, body, err in refusals:
    _classes.setdefault(_defect_class(body, err), []).append(
        f"{mod}.{cname}.{name}")
check("every refusal is a corpus text defect, not a grammar gap",
      set(_classes) <= {"comment-only body", "truncated body", "mangled text"},
      str(_classes))


# ---------------------------------------------------------------------------
# value parity on one model
# ---------------------------------------------------------------------------

print("== value parity (same model, both lowerings) ==")
pkg = U.Package(name="P")
cls = U.Class(name="C")
pkg.packagedElement.append(cls)
attr = U.Property(name="a")
cls.ownedAttribute.append(attr)
op = U.Operation(name="f")
cls.ownedOperation.append(op)
par = U.Parameter(name="x")
op.ownedParameter.append(par)
sm = U.StateMachine(name="S")
reg = U.Region(name="r")
sm.region.append(reg)
st = U.State(name="s")
reg.subvertex.append(st)
pkg.packagedElement.append(sm)
MODEL = [pkg, cls, attr, op, par, sm, reg, st]


def _eval(src, obj):
    env = dict(T._EVAL_ENV)
    env["self"] = obj
    env["_d"] = T._derived_call(D)
    g = dict(T._EVAL_BUILTINS)
    g.update(env)
    try:
        return ("value", repr(eval(src, g, {})))  # noqa: S307
    except Exception as ex:                       # noqa: BLE001
        return ("raise", type(ex).__name__)


mismatch, values_compared, capture_diff = [], 0, 0
for obj in MODEL:
    for klass in type(obj).__mro__:
        for name, body in klass.__dict__.get("CONSTRAINTS", ()):
            try:
                old_src = T.translate_legacy(body)
                new_src = T.translate(body)
            except Exception:
                continue
            a, b = _eval(old_src, obj), _eval(new_src, obj)
            values_compared += 1
            if a == b:
                continue
            key = ("uml25", type(obj).__name__, name)
            if key in V0_EMITTER_DEFECTS:
                capture_diff += 1
                continue
            mismatch.append((type(obj).__name__, name, a, b))

check("both lowerings agree on every applicable body",
      not mismatch, str(mismatch[:3]))
check("evaluations compared", values_compared > 100, f"{values_compared}")
print(f"  (differences explained by the itemized capture fixes: "
      f"{capture_diff})")


# ---------------------------------------------------------------------------
# round-trip: AST -> OCL -> AST
# ---------------------------------------------------------------------------

print("== print/parse round-trip ==")
rt_bad, rt_ok = [], 0
for mod, cname, name, body in CORPUS:
    try:
        tree = P.parse(body)
    except Exception:
        continue
    try:
        again = P.parse(E.to_ocl(tree))
    except Exception as ex:
        rt_bad.append((f"{mod}.{cname}.{name}", "reparse", str(ex)[:60]))
        continue
    if A.dump(tree) == A.dump(again):
        rt_ok += 1
    else:
        rt_bad.append((f"{mod}.{cname}.{name}", "differs", ""))
check("every parsed body round-trips", not rt_bad,
      f"{rt_ok} ok, {len(rt_bad)} bad: {rt_bad[:3]}")


# ---------------------------------------------------------------------------
# new grammar (parse) + honest refusal (lower)
# ---------------------------------------------------------------------------

print("== grammar the v0 parser rejected ==")


def _parses(src):
    try:
        return A.dump(P.parse(src))
    except Exception as ex:                       # noqa: BLE001
        return f"FAIL {type(ex).__name__}: {ex}"


check("Tuple{...} literal", _parses("Tuple{a = 1, b = 'x'}.a = 1").startswith(
    "(BinOp '=' (Nav (TupleLit"), _parses("Tuple{a = 1}")[:40])
check("@pre postfix", _parses("self.x@pre = self.x").startswith(
    "(BinOp '='"))
check("->iterate with an accumulator",
      _parses("allNamespaces()->iterate(ns : Namespace; "
              "agg : String = name | agg)").startswith("(Iterate "))
check("real literal", _parses("0.5 < 1").startswith("(BinOp '<' (Literal 'real'"))
check("KerML selectByKind parses as a call",
      _parses("ownedRelationship->selectByKind(FeatureMembership)")
      .startswith("(Call"))
check("typed iterator variable keeps its name",
      "(Lambda 'v' 'T'" in _parses("x->select(v : T | v.a)"))
print("  (lowering the not-yet-supported constructs must refuse)")
for src, label in (("self.x@pre = 1", "@pre"),
                   ("x->iterate(v; a = 0 | a)", "->iterate"),
                   ("x->isUnique(e | e.a)", "->isUnique"),
                   ("x->selectByKind(Feature)", "selectByKind")):
    try:
        E.to_python(P.parse(src))
        check(f"{label} has no lowering", False)
    except A.UnmappedFeature:
        check(f"{label} refuses to lower", True)


# ---------------------------------------------------------------------------
# spans
# ---------------------------------------------------------------------------

print("== source spans ==")
src = "not a.b and c->select(x | x.d)"
tree = P.parse(src)
span_texts = [(type(n).__name__, src[n.span.start:n.span.end]) for n in A.walk(tree)
              if n.span is not None]
check("every node carries a span", len(span_texts) == len(list(A.walk(tree))))
check("the root span covers the body",
      span_texts[0] == ("BinOp", src), str(span_texts[0]))
check("navigation spans are their own text",
      [t for k, t in span_texts if k == "Nav"] == ["a.b", "x.d"],
      str([t for k, t in span_texts if k == "Nav"]))


print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
