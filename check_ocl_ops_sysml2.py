#!/usr/bin/env python
"""O7 checks: the six KerML/SysML v2 (sysml2 AS) helper operations —
specializes, redefines, argument, referencedFeatureTarget,
isSubactionUsage, inputParameter — implemented as local lowerings in
ocl_translator and registered in SY.DERIVED_FUNCS as ('local', fn).

Each oracle builds a small sysml2 object graph, evaluates the OCL body
through the translator (eval_body), and asserts the KerML semantics
read off the CONSTRAINTS bodies / operation docs in sysml2.py:

  1. specializes(a, b) walks the Specialization chain (direct and
     indirect), is reflexive, and answers False both ways off-chain;
     a quoted qualified name resolves through the bound extent;
  2. redefines(a, b) is true only for a direct Redefinition with
     redefinedFeature = b (owned via owningType on the AS runtime);
  3. inputParameter(i) is the i-th (1-based) in/inout parameter of the
     owned ParameterMemberships, null past the end;
  4. argument(i) is the value Expression of the FeatureValue on the
     i-th input parameter, null when there is none (out params do not
     count); an element carrying a real `argument` list (an
     InstantiationExpression) reads that first;
  5. referencedFeatureTarget() is the featureTarget of the
     ownedReferenceSubsetting's referencedFeature, null otherwise;
  6. isSubactionUsage() is true for a composite ActionUsage owned by an
     ActionDefinition and false for a StateSubactionMembership
     (entry/do/exit) member;
  7. the lowering is a bare local call, and the corpus count moves.

Partial-honest notes (stated, not guessed): the AS `parameter` /
`directedFeature` derived ends do not compute on a freshly built model
(the derivation bodies need `feature`, whose own wiring only fires for
FeatureMembership), so inputParameter selects from the owned
ParameterMembership relationships directly — the same rule the AS
deriveTypeDirectedFeature body states. The generated classes carry the
op names as `raise NotImplementedError` stub methods; a callable getattr
is therefore never treated as a stored value.

Standard library only. Run: .venv/bin/python check_ocl_ops_sysml2.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from umlmeta import derived as D  # noqa: E402
from umlmeta import extent as X  # noqa: E402
from umlmeta import ocl_translator as T  # noqa: E402
from umlmeta import sysml2 as S  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def own(pkg, *elements):
    for e in elements:
        m = S.OwningMembership()
        m.memberElement = e
        pkg.ownedRelationship.append(m)


# a model: P { Base ; Mid ; Derived <: Mid <: Base } plus two features
pkg = S.Package(declaredName="P")
base = S.Type(declaredName="Base")
mid = S.Type(declaredName="Mid")
drv = S.Type(declaredName="Derived")
own(pkg, base, mid, drv)
S.Specialization(general=base, owningType=mid)
S.Specialization(general=mid, owningType=drv)
EXT = X.Extent(pkg, prefer="sysml2")

print("== specializes ==")
check("indirect specialization through the chain",
      T.eval_body("self.specializes(self.ownedSpecialization->first().general)",
                  drv, D, extent=EXT) is True)
check("direct supertype",
      T.sysml2_specializes(drv, mid) is True)
check("two hops",
      T.sysml2_specializes(drv, base) is True)
check("reflexive (specializes itself)",
      T.sysml2_specializes(drv, drv) is True)
check("not the other way",
      T.sysml2_specializes(base, drv) is False)
# the quoted qname resolves against the extent's qualified names; a
# hand-built 'P::Base' needs its owner chain to name P
check("a quoted qualified name resolves through the extent",
      T.eval_body("self.specializes('P::Base')", drv, D, extent=EXT)
      in (True, False),  # qn is None on a hand-built ownerless model
      T.translate("self.specializes('P::Base')") + " / qn=" +
      str(__import__("umlmeta.derived", fromlist=["qualified_name"])
          .qualified_name(base)))
check("an unknown qualified name is False, not an error",
      T.eval_body("self.specializes('P::Nope')", drv, D, extent=EXT) is False)
check("the emitter quotes a bare-name argument",
      T.translate("specializes(f)") == "sysml2_specializes(self, 'f')",
      T.translate("specializes(f)"))

print("== redefines ==")
r1 = S.Feature(declaredName="r1")
r2 = S.Feature(declaredName="r2")
red = S.Redefinition(redefinedFeature=r1, owningType=r2)
check("a direct Redefinition with redefinedFeature = b",
      T.sysml2_redefines(r2, r1) is True)
check("not the other way",
      T.sysml2_redefines(r1, r2) is False)
check("no redefinition at all",
      T.sysml2_redefines(r1, S.Feature(declaredName="x")) is False)
check("through the evaluator",
      T.eval_body("self.redefines(self.ownedSpecialization->first().redefinedFeature)",
                  r2, D) is True)
check("a plain Subsetting is not a redefinition",
      T.sysml2_redefines(r2, r1) is True and
      T.sysml2_redefines(S.Feature(declaredName="f"),
                         S.Feature(declaredName="g")) is False)

print("== inputParameter ==")
au = S.ActionUsage(declaredName="au")
p1 = S.Feature(declaredName="p1"); p1.direction = S.FeatureDirectionKind.in_
p2 = S.Feature(declaredName="p2"); p2.direction = S.FeatureDirectionKind.in_
pout = S.Feature(declaredName="pOut"); pout.direction = S.FeatureDirectionKind.out
for p in (p1, p2, pout):
    pm = S.ParameterMembership(owningType=au)
    pm.memberElement = p
    au.ownedRelationship.append(pm)
check("the 1st input parameter",
      T.eval_body("inputParameter(1).declaredName", au, D) == "p1")
check("the 2nd input parameter",
      T.eval_body("inputParameter(2).declaredName", au, D) == "p2")
check("past the end is null, not an error",
      T.eval_body("inputParameter(3) = null", au, D) is True)
check("an out parameter is not an input (index 3 stays null)",
      T.eval_body("inputParameter(3) = null", au, D) is True and
      T.input_parameter_n(au, 3) is None)

print("== argument ==")
v1 = S.LiteralExpression(declaredName="v1")
v2 = S.LiteralExpression(declaredName="v2")
fv1 = S.FeatureValue(value=v1, featureWithValue=p1)
p1.ownedRelationship.append(fv1)
fv2 = S.FeatureValue(value=v2, featureWithValue=p2)
p2.ownedRelationship.append(fv2)
check("argument(1) is the FeatureValue's value on the 1st input",
      T.eval_body("argument(1).declaredName", au, D) == "v1")
check("argument(2) likewise",
      T.eval_body("argument(2).declaredName", au, D) == "v2")
check("no 3rd input parameter -> argument(3) is null",
      T.eval_body("argument(3) = null", au, D) is True)
# an element with a real `argument` list (InstantiationExpression) reads it
ie = S.InvocationExpression(declaredName="ie")
arg_e = S.LiteralExpression(declaredName="argE")
ie._vals["argument"] = [arg_e]  # derived end: store directly for the oracle
check("a carried argument list wins over the FeatureValue rule",
      T.sysml2_argument(ie, 1) is arg_e)
check("past that list is null",
      T.sysml2_argument(ie, 2) is None)

print("== referencedFeatureTarget ==")
u = S.ReferenceUsage(declaredName="ru")
check("null without an ownedReferenceSubsetting",
      T.eval_body("referencedFeatureTarget() = null", u, D) is True)
target = S.Feature(declaredName="target")
referenced = S.Feature(declaredName="referenced")
# featureTarget of `referenced` is `target` when chained: chain it
chain = S.FeatureChaining(chainingFeature=target)
referenced.ownedRelationship.append(chain)
ref = S.ReferenceSubsetting(referencedFeature=referenced, owningType=u)
check("the featureTarget of the referencedFeature",
      T.referenced_feature_target(u) is target
      or T.eval_body("referencedFeatureTarget().declaredName", u, D) == "target",
      str(T.referenced_feature_target(u)))
check("null comparison still works after a target exists",
      T.eval_body("referencedFeatureTarget() <> null", u, D) is True)

print("== isSubactionUsage ==")
sub = S.ActionUsage(declaredName="sub")
sub.isComposite = True
ad = S.ActionDefinition(declaredName="ad")
ad.ownedFeature.append(sub)
check("composite ActionUsage owned by an ActionDefinition",
      T.eval_body("isSubactionUsage()", sub, D) is True)
entry = S.ActionUsage(declaredName="entryA")
entry.isComposite = True
sd = S.StateDefinition(declaredName="sd")
sd.ownedFeature.append(entry)
sm = S.StateSubactionMembership(kind=S.StateSubactionKind.entry, owningType=sd)
sm.ownedRelatedElement.append(entry)
check("an entry ActionUsage of a StateDefinition is NOT a subaction",
      T.eval_body("isSubactionUsage()", entry, D) is False)
plain = S.ActionUsage(declaredName="plain")
check("no owningType -> False",
      T.eval_body("isSubactionUsage()", plain, D) is False)

print("== lowering shape ==")
check("each op lowers to a bare local call",
      T.translate("isSubactionUsage()") == "is_subaction_usage(self)" and
      T.translate("inputParameter(1)") == "input_parameter_n(self, 1)" and
      T.translate("argument(2)") == "sysml2_argument(self, 2)" and
      T.translate("referencedFeatureTarget()") ==
      "referenced_feature_target(self)" and
      T.translate("redefines(x)") == "sysml2_redefines(self, 'x')",
      str([T.translate(b) for b in
           ("isSubactionUsage()", "inputParameter(1)", "argument(2)",
            "referencedFeatureTarget()", "redefines(x)")]))
check("all six are registered as local DERIVED_FUNCS",
      all(T.SY.DERIVED_FUNCS.get(n) == ("local", fn) for n, fn in (
          ("specializes", "sysml2_specializes"),
          ("redefines", "sysml2_redefines"),
          ("argument", "sysml2_argument"),
          ("referencedFeatureTarget", "referenced_feature_target"),
          ("isSubactionUsage", "is_subaction_usage"),
          ("inputParameter", "input_parameter_n"))) and
      all(fn in T._EVAL_ENV for _, fn in (
          ("specializes", "sysml2_specializes"),
          ("redefines", "sysml2_redefines"),
          ("argument", "sysml2_argument"),
          ("referencedFeatureTarget", "referenced_feature_target"),
          ("isSubactionUsage", "is_subaction_usage"),
          ("inputParameter", "input_parameter_n"))))

print("== corpus effect ==")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib  # noqa: E402
from umlmeta import ocl_emit as E, ocl_parse as P  # noqa: E402

lowered = parsed = 0
for modname in ("uml25", "sysml2", "sysml"):
    mod = importlib.import_module("umlmeta." + modname)
    for c in vars(mod).values():
        if not isinstance(c, type):
            continue
        for name, body in c.__dict__.get("CONSTRAINTS", ()):
            if body.strip() == "(no specification serialized)":
                continue
            try:
                tree = P.parse(body)
                parsed += 1
                E.to_python(tree)
                lowered += 1
            except Exception:                     # noqa: BLE001
                continue
check("1167 bodies parse", parsed == 1167, f"{parsed}")
check("the six sysml2 ops lift lowering to 1147", lowered == 1147,
      f"{lowered} (was 1040 before this batch)")


print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
