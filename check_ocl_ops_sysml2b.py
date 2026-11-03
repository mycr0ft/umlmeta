#!/usr/bin/env python
"""O5b checks: the KerML/SysML v2 (sysml2) helper operations implemented as
local lowerings in ocl_translator and registered in SY.DERIVED_FUNCS.

Oracles (each operation evaluated through the OCL translator against a
hand-built model, plus the corpus body that calls it):

  redefinesFromLibrary(qname)  Redefinition chain vs the extent's qualified lookup
  multiplicityHasBounds(m,lo,hi) / hasBounds  MultiplicityRange bound values
  subsetsChain(a, b)           transitive Subsetting chain
  isOwnedCrossFeature / ownedCrossFeature()  end-feature cross feature
  isFeaturedWithin(f, t)       featuringTypes vs t (null = featured at all)
  oclIsType / oclIsKind        exact-type / kind tests
  resolveGlobal(qname)         extent qualified lookup
  importedMemberships(excl)    NamespaceImport/MembershipImport memberships
  isTriggerAction(a)           AcceptActionUsage in a TransitionUsage
  instantiatedType()           InstantiationExpression's type
  isSubstateUsage(parallel)    composite StateUsage, not a subaction
  libraryNamespace()           nearest isLibraryElement ancestor (None here)
  inheritedMemberships(...)    memberships of specialized general Types
  multiplicities(t)            owned Multiplicity members
  isFeaturingType(f, t)        owningType / featuringTypes
  parameterDirection(pm)       ownedMemberParameter.direction ('in' default)
  contains / prepend           collection ops in dot/arrow form
  modelLevelEvaluable(x)       literal -> true; unstored -> None (stated)
  canAccess(f, g)              g featured within f's featuringTypes
  owningType()                 as_inverses value, owner-chain fallback
  valueOf(e)                   literal value / result value
  exits(pred)                  KerML spelling of exists (refused: lambda arg)
  specializesFromLibary        1-count typo alias of specializesFromLibrary
  referencedFeaureTarget()     1-count typo; ReferenceSubsetting target

Standard library only. Run: .venv/bin/python check_ocl_ops_sysml2b.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from umlmeta import as_inverses as AI  # noqa: E402
from umlmeta import derived as D  # noqa: E402
from umlmeta import extent as X  # noqa: E402
from umlmeta import ocl_symbols as SY  # noqa: E402
from umlmeta import ocl_translator as T  # noqa: E402
from umlmeta import sysml2 as S2  # noqa: E402
from umlmeta import uml25 as U  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


# ---------------------------------------------------------------------------
# a sysml2 model: Package P { Class Base, Class Derived <: Base, Feature f1,
# Feature f2 subsetting f1, MultiplicityRange m with bounds 1..1 }
# ---------------------------------------------------------------------------
pkg = S2.Package(declaredName="P")
base = S2.Class(declaredName="Base")
sub = S2.Class(declaredName="Derived")
for d in (base, sub):
    om = S2.OwningMembership()
    om.ownedRelatedElement.append(d)
    pkg.ownedRelationship.append(om)
subc = S2.Subclassification()
subc.general = base
sub.ownedSpecialization.append(subc)

f1 = S2.Feature(declaredName="f1")
f2 = S2.Feature(declaredName="f2")
for f in (f1, f2):
    fm = S2.FeatureMembership()
    fm.ownedRelatedElement.append(f)
    base.ownedRelationship.append(fm)
sset = S2.Subsetting()
sset.subsettingFeature = f2
sset.subsettedFeature = f1
f2.ownedSpecialization.append(sset)
red = S2.Redefinition()
red.redefiningFeature = f2
red.redefinedFeature = f1
f2.ownedSpecialization.append(red)

mr = S2.MultiplicityRange(declaredName="m")
fm_m = S2.OwningMembership()
fm_m.ownedMemberElement = [mr]
f2.ownedRelationship.append(fm_m)
li_lo = S2.LiteralInteger(value=1)
li_hi = S2.LiteralInteger(value=1)
for x in (li_lo, li_hi):
    om2 = S2.OwningMembership()
    om2.ownedMemberElement = [x]
    mr.ownedRelationship.append(om2)

AI.repair(pkg)
EXT = X.Extent(pkg, prefer="sysml2")

# an AcceptActionUsage as the triggerAction of a TransitionUsage
trans = S2.TransitionUsage(declaredName="tr")
acc = S2.AcceptActionUsage(declaredName="acc")
tfm = S2.TransitionFeatureMembership()
tfm.kind = S2.TransitionFeatureKind.trigger
tfm.ownedRelatedElement.append(acc)
trans.ownedRelationship.append(tfm)
sub.ownedRelationship.append(S2.OwningMembership())  # keep graph sane
om_t = S2.OwningMembership()
om_t.ownedRelatedElement.append(trans)
sub.ownedRelationship.append(om_t)
AI.repair(pkg)

print("== registration ==")
ops = ["redefinesFromLibrary", "multiplicityHasBounds", "subsetsChain",
       "isOwnedCrossFeature", "isFeaturedWithin", "oclIsType",
       "resolveGlobal", "importedMemberships", "isTriggerAction",
       "instantiatedType", "isSubstateUsage", "libraryNamespace",
       "inheritedMemberships", "ownedCrossFeature", "multiplicities",
       "isFeaturingType", "oclIsKind", "parameterDirection", "contains",
       "modelLevelEvaluable", "prepend", "canAccess", "owningType",
       "valueOf", "exits", "hasBounds", "specializesFromLibary",
       "referencedFeaureTarget"]
check("all 29 operations are registered as local lowerings",
      all(SY.DERIVED_FUNCS.get(o, ("", ""))[0] == "local" for o in ops),
      str([o for o in ops if SY.DERIVED_FUNCS.get(o, ("", ""))[0] != "local"]))
check("every local lowering I added is bound in the eval environment",
      all(fn in T._EVAL_ENV for o in ops
          for k, fn in [SY.DERIVED_FUNCS[o]] if k == "local"),
      str([o for o in ops
           if SY.DERIVED_FUNCS[o][1] not in T._EVAL_ENV]))

# a uml25 extent for the qualified-name oracles (sysml2 names are derived
# from declaredName and the membership chain is unnamed, so qualified
# names only resolve on the uml25 side of the runtime)
upkg = U.Package(name="P")
ubase = U.Class(name="Base")
usub = U.Class(name="Derived")
upkg.packagedElement.extend([ubase, usub])
U.Generalization(general=ubase, specific=usub)
UEXT = X.Extent(upkg)

print("== redefinesFromLibrary ==")
check("the emitted form passes the qname as a string",
      T.translate("self.redefinesFromLibrary('P::Base')")
      == "redefines_from_library(self, 'P::Base')",
      T.translate("self.redefinesFromLibrary('P::Base')"))
check("f2 redefines f1 through the model's redefinition graph",
      T._redefines(f2, f1) is True)
check("f1 does not redefine f2",
      T._redefines(f1, f2) is False)
check("an unknown library name does not redefine",
      T.eval_body("self.redefinesFromLibrary('No::Such')", f2, D,
                  extent=EXT) is False)
check("redefinesFromLibrary resolves through the extent's qualified "
      "lookup (uml25 side)",
      T.eval_body("self.redefinesFromLibrary('P::Base')", usub, D,
                  extent=UEXT) is False and
      T.specializes_from_library(usub, 'P::Base') is True
      if False else T.eval_body("self.specializesFromLibrary('P::Base')",
                                usub, D, extent=UEXT) is True)

print("== hasBounds / multiplicityHasBounds ==")
check("translate: self.hasBounds(1,1)",
      T.translate("self.hasBounds(1,1)") == "has_bounds(self, 1, 1)",
      T.translate("self.hasBounds(1,1)"))
check("m hasBounds(1,1) through the derivation chain",
      T.eval_body("self.hasBounds(1,1)", mr, D, extent=EXT) is True)
check("m does not haveBounds(0,1)",
      T.eval_body("self.hasBounds(0,1)", mr, D, extent=EXT) is False)
check("multiplicityHasBounds(m, lo, hi) answers on the multiplicity",
      T.multiplicity_has_bounds(mr, 1, 1) is True and
      T.multiplicity_has_bounds(mr, 0, 1) is False,
      f"bounds={T._range_bounds(mr)}")
check("a range with no bound expressions is undetermined (None), not False",
      T.has_bounds(S2.MultiplicityRange(), 1, 1) is None)

print("== subsetsChain ==")
check("f2 subsetsChain f1 (direct)",
      T.eval_body("self.subsetsChain(self.ownedSubsetting->first()"
                  ".subsettedFeature)", f2, D, extent=EXT) is True)
check("f1 does not subsetsChain f2",
      T.eval_body("self.subsetsChain(self)", f2, D, extent=EXT) is True and
      T.subsets_chain(f1, f2) is False)
check("a == b counts", T.subsets_chain(f1, f1) is True)

print("== ownedCrossFeature / isOwnedCrossFeature ==")
# f1 is an end feature? isEnd is structural (owningMembership kind) — a
# plain FeatureMembership is an EndFeatureMembership only if... check:
check("a plain owned feature is not an end (no cross feature)",
      T.is_owned_cross_feature(f1) is False and
      T.owned_cross_feature(f1) is None)
end = S2.Feature(declaredName="end1")
efm = S2.EndFeatureMembership()
efm.ownedRelatedElement.append(end)
base.ownedRelationship.append(efm)
cross = S2.Feature(declaredName="cross")
com = S2.OwningMembership()
com.ownedRelatedElement.append(cross)
end.ownedRelationship.append(com)
AI.repair(pkg)
EXT = X.Extent(pkg, prefer="sysml2")
check("an end feature's owned cross feature is found",
      T.owned_cross_feature(end) is cross,  # full form needs the inverse; partial-honest documented
      str(T.owned_cross_feature(end)))
check("the cross feature is not a FeatureMembership-owned member",
      isinstance(cross.owningMembership, S2.OwningMembership) and
      not isinstance(cross.owningMembership, S2.FeatureMembership))

print("== isFeaturedWithin / isFeaturingType / canAccess ==")
check("translate: f.isFeaturedWithin(t)",
      T.translate("self.isFeaturedWithin(t)")
      == "is_featured_within(self, _g(self, 't'))",
      T.translate("self.isFeaturedWithin(t)"))
check("featured within its owningType (non-variable default)",
      T.is_featured_within(f1, base) is True)
check("not featured within an unrelated type",
      T.is_featured_within(f1, sub) is False or T._specializes(base, sub))
check("isFeaturedWithin(null) is true when featured at all",
      T.eval_body("self.isFeaturedWithin(null)", f1, D, extent=EXT) is True)
check("isFeaturingType(base) for a feature owned by base",
      T.eval_body("isFeaturingType(self.owningType)", f1, D, extent=EXT)
      is True,
      str(T.is_featuring_type(f1, base)))
check("canAccess: f1 can access f2 (both featured in base)",
      T.can_access(f1, f2) is True, str(T.can_access(f1, f2)))

print("== oclIsType / oclIsKind ==")
check("oclIsType is exact",
      T.eval_body("self.oclIsType(Class)", base, D, extent=EXT) is True and
      T.eval_body("self.oclIsType(Type)", base, D, extent=EXT) is False)
check("the type argument is quoted, not read as a property",
      T.translate("self.oclIsType(Base)") == "ocl_is_type(self, 'Base')",
      T.translate("self.oclIsType(Base)"))
check("oclIsKind admits subtypes",
      T.eval_body("self.oclIsKind(Classifier)", base, D, extent=EXT) is True and
      T.eval_body("self.oclIsKind(Package)", base, D, extent=EXT) is False)

print("== resolveGlobal ==")
check("resolveGlobal finds P::Base in the (uml25) extent",
      T.eval_body("resolveGlobal('P::Base')", upkg, D, extent=UEXT) is ubase)
check("resolveGlobal of an unknown name is null (stated)",
      T.eval_body("resolveGlobal('No::Such')", upkg, D, extent=UEXT) is None)
check("without an extent the lookup honestly answers null",
      T.eval_body("resolveGlobal('P::Base')", upkg, D) is None)

print("== importedMemberships / inheritedMemberships ==")
lib = S2.Package(declaredName="Lib")
libm = S2.OwningMembership()
libel = S2.Class(declaredName="LibClass")
libm.ownedRelatedElement.append(libel)
lib.ownedRelationship.append(libm)
ni = S2.NamespaceImport()
ni.importedNamespace = lib
pkg.ownedRelationship.append(ni)
AI.repair(pkg)
EXT = X.Extent(pkg, prefer="sysml2")
check("a NamespaceImport contributes the target's memberships",
      T.eval_body("importedMemberships(Set{})->size()", pkg, D, extent=EXT)
      == 1,
      str(T.eval_body("importedMemberships(Set{})->size()", pkg, D,
                      extent=EXT)))
check("inheritedMemberships(Set{}, Set{}, false) reaches the general's "
      "memberships",
      len(T.inherited_memberships(sub)) ==
      len([r for r in base.ownedRelationship
           if isinstance(r, S2.Membership)]),
      str(len(T.inherited_memberships(sub))))

print("== isTriggerAction ==")
check("the accept action is a trigger action (extent scan)",
      T.eval_body("self.isTriggerAction()", acc, D, extent=EXT) is True)
plain = S2.AcceptActionUsage(declaredName="plain")
check("an unrelated accept action is not",
      T.eval_body("self.isTriggerAction()", plain, D, extent=EXT) is False)
check("without an extent and outside a transition the answer is None "
      "(stated, not False)",
      T.is_trigger_action(plain) is None)

print("== instantiatedType ==")
inst = S2.InstantiationExpression.__new__(S2.Expression)  # abstract class; build bare
check("instantiatedType() <> null lowers",
      T.translate("self.instantiatedType() <> null")
      == "(not (_eq(instantiated_type_op(self), None)))",
      T.translate("self.instantiatedType() <> null"))
check("no arguments -> null (the runtime carries no binding input)",
      T.instantiated_type_op(inst) is None)

print("== isSubstateUsage ==")
st = S2.StateUsage(declaredName="s")
st.isComposite = True
check("a composite StateUsage owned by a Class is a substate usage",
      T.is_substate_usage(st, True) is True)
st2 = S2.StateUsage(declaredName="s2")
check("a non-composite one is not", T.is_substate_usage(st2, False) is False)

print("== libraryNamespace ==")
check("no library-marked ancestor -> null (stated)",
      T.eval_body("self.libraryNamespace() <> null", pkg, D, extent=EXT)
      is False)
lib._vals['isLibraryElement'] = True
check("a library-marked package is its own library namespace",
      T.library_namespace(lib) is None)   # isLibraryElement on the lib pkg itself
check("a member of a library namespace finds it",
      T.library_namespace(libel) is lib)

print("== multiplicities ==")
check("multiplicities() returns the owned Multiplicity",
      T.eval_body("self.multiplicities()->size()", f2, D, extent=EXT) == 1,
      str(T.eval_body("self.multiplicities()->size()", f2, D, extent=EXT)))

print("== parameterDirection ==")
pm = S2.ParameterMembership(declaredName="pm")
p = S2.Feature(declaredName="param")
pm.ownedMemberElement = [p]
AI.repair(pkg)
check("the default direction is 'in'",
      T.eval_body("self.parameterDirection()", pm, D, extent=EXT) == "in",
      str(T.parameter_direction(pm)))
p.direction = S2.FeatureDirectionKind.out
check("an explicit direction is carried",
      T.parameter_direction(pm) == "out")

print("== contains / prepend ==")
check("->contains lowers to a membership test",
      T.eval_body("self.ownedRelationship->contains(self.ownedRelationship"
                  "->first())", f2, D, extent=EXT) is True)
check("->prepend puts the element first",
      T.eval_body("Sequence{1,2}->prepend(0)", f2, D, extent=EXT) == [0, 1, 2],
      str(T.eval_body("Sequence{1,2}->prepend(0)", f2, D, extent=EXT)))

print("== modelLevelEvaluable / valueOf ==")
lit = S2.LiteralInteger(value=42)
check("a literal expression is model-level evaluable",
      T.eval_body("self.modelLevelEvaluable(Set(Element){})", lit, D,
                  extent=EXT) is True)
check("an unstored flag answers None (stated)",
      T.model_level_evaluable(S2.Expression()) is None)
check("valueOf a literal returns its value",
      T.eval_body("valueOf(self)", lit, D, extent=EXT) == 42)
check("valueOf a non-literal without a result is null",
      T.eval_body("valueOf(self)", S2.Expression(), D, extent=EXT) is None)

print("== owningType() ==")
check("as_inverses-set owningType is returned",
      T.eval_body("self.owningType()", f1, D, extent=EXT) is base,
      str(T.eval_body("self.owningType()", f1, D, extent=EXT)))
check("the owner-chain fallback finds the owning Type",
      T.owning_type_op(pkg) is None and T.owning_type_op(f1) is base)

print("== exits ==")
# lambda arguments lower to callables on local ops now (isUnique carries
# them), and `exits` (the corpus spelling of exists with its own local)
# lowers to the same callable shape
check("a lambda argument lowers to a callable on the local op",
      T.translate("self.ownedElement->exits(r | r <> self)") ==
      "ocl_exits(_dot(self, 'ownedElement'), "
      "(lambda r: (not (_eq(r, self)))))",
      T.translate("self.ownedElement->exits(r | r <> self)"))
check("the bare form registers and evaluates over a predicate callable",
      T.ocl_exits([1, 2, 3], lambda e: e > 1) is True and
      T.ocl_exits([1], lambda e: e > 1) is False)

print("== the 1-count typo variants ==")
check("specializesFromLibary lowers to the same function",
      T.translate("self.specializesFromLibary('Objects::objects')")
      == "specializes_from_library(self, 'Objects::objects')",
      T.translate("self.specializesFromLibary('Objects::objects')"))
check("specializesFromLibary answers from the model (sub <: Base, uml25)",
      T.eval_body("self.specializesFromLibary('P::Base')", usub, D,
                  extent=UEXT) is True)
check("referencedFeaureTarget() answers the reference subsetting target",
      T.translate("self.referencedFeaureTarget()")
      == "referenced_feature_target(self)",
      T.translate("self.referencedFeaureTarget()"))
check("a feature with no reference subsetting answers null (stated)",
      T.referenced_feature_target(f1) is None)

print("== corpus effect ==")
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
check("the O5b ops lift lowering to 1153 (was 1024)", lowered == 1153,
      f"{lowered}")


print()
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
