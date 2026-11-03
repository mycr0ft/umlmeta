# v2 validation triage

143 elements, 2033 checks (+4999 derivations), 250 violations, 1432 skipped, coverage 59%

| kind | family | count | owner | note |
|---|---|---:|---|---|
| violation | `Type.checkTypeSpecialization` | 59 | transform | the transform emits no library specialization edges (O6) |
| violation | `Feature.checkFeatureSpecialization` | 41 | transform | same: no library specialization edge on features |
| violation | `Class.checkClassSpecialization` | 16 | transform | same: no library specialization edge on classes |
| violation | `OccurrenceUsage.checkOccurrenceUsageSpecialization` | 16 | transform | the transform emits no library specialization edges (O6) |
| violation | `Step.checkStepSpecialization` | 9 | transform | the transform emits no library specialization edges (O6) |
| violation | `ActionUsage.checkActionUsageSpecialization` | 7 | transform | the transform emits no library specialization edges (O6) |
| violation | `ActionDefinition.checkActionDefinitionSpecialization` | 5 | transform | the transform emits no library specialization edges (O6) |
| violation | `Behavior.checkBehaviorSpecialization` | 5 | transform | the transform emits no library specialization edges (O6) |
| violation | `AttributeUsage.checkAttributeUsageSpecialization` | 4 | transform | the transform emits no library specialization edges (O6) |
| violation | `Connector.checkConnectorBinarySpecialization` | 4 | transform | the transform emits no library specialization edges (O6) |
| violation | `Connector.checkConnectorSpecialization` | 4 | transform | the transform emits no library specialization edges (O6) |
| violation | `Expression.validateExpressionResultParameterMembership` | 3 | transform | LiteralInteger built without its ReturnParameterMembership |
| violation | `Expression.checkExpressionSpecialization` | 3 | transform | the transform emits no library specialization edges (O6) |
| violation | `EnumerationUsage.checkAttributeUsageSpecialization` | 3 | transform | the transform emits no library specialization edges (O6) |
| violation | `ItemDefinition.checkItemDefinitionSpecialization` | 3 | transform | the transform emits no library specialization edges (O6) |
| violation | `Structure.checkStructureSpecialization` | 3 | transform | the transform emits no library specialization edges (O6) |
| violation | `LiteralInteger.checkLiteralIntegerSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `LiteralExpression.checkLiteralExpressionSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `PortUsage.checkPortUsageSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `ParameterMembership.validateParameterMembershipOwningType` | 2 | runtime | owningType is the inverse of owningMembership; not set |
| violation | `ConnectionUsage.checkConnectionUsageSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `ConnectionUsage.checkConnectionUsageBinarySpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `PartUsage.checkPartUsageSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `PartUsage.validatePartUsagePartDefinition` | 2 | transform | ConnectionUsage is never typed by a PartDefinition |
| violation | `ItemUsage.checkItemUsageSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `DataType.checkDataTypeSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `PartDefinition.checkPartDefinitionSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `StateUsage.checkStateUsageSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `TransitionUsage.checkTransitionUsageSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `TransitionUsage.validateTransitionUsageSuccession` | 2 | transform | the succession edge the rule needs is not emitted |
| violation | `TransitionUsage.checkTransitionUsageSuccessionSourceSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `Succession.checkSuccessionSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `Connector.validateConnectorRelatedFeatures` | 2 | transform | ConnectionUsage carries no relatedFeature ends |
| violation | `UseCaseDefinition.checkUseCaseDefinitionSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `CaseDefinition.checkCaseDefinitionSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `CaseDefinition.validateCaseDefinitionSubjectParameterPosition` | 2 | transform | subject parameter emitted without its position |
| violation | `CalculationDefinition.checkCalculationDefinitionSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `Function.validateFunctionResultParameterMembership` | 2 | transform | function result parameter membership not emitted |
| violation | `Function.checkFunctionSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `MultiplicityRange.validateMultiplicityRangeBounds` | 1 | runtime | bound memberships carry no value; derived bound is null |
| violation | `Multiplicity.checkMultiplicityTypeFeaturing` | 1 | unattributed |  |
| violation | `Multiplicity.checkMultiplicitySpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `EnumerationDefinition.validateEnumerationDefinitionIsVariation` | 1 | transform | variation flag not emitted on an enumeration definition |
| violation | `StateDefinition.checkStateDefinitionSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `StateSubactionMembership.validateStateSubactionMembershipOwningType` | 1 | runtime | same inverse-maintenance gap |
| violation | `UseCaseUsage.checkUseCaseUsageSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `CaseUsage.validateCaseUsageSubjectParameterPosition` | 1 | transform | same |
| violation | `CaseUsage.checkCaseUsageSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `CalculationUsage.checkCalculationUsageSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `ConnectionDefinition.checkConnectionDefinitionSpecializations` | 1 | transform | no library specialization edge (the O6 family) |
| violation | `ConnectionDefinition.validateConnectionDefinitionIsSufficient` | 1 | transform | connection ends not sufficient: related features missing |
| violation | `ConnectionDefinition.checkConnectionDefinitionBinarySpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `AssociationStructure.checkAssociationStructureSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `AssociationStructure.checkAssociationStructureBinarySpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `Association.validateAssociationRelatedTypes` | 1 | transform | related types not emitted on the association |
| violation | `Association.checkAssociationSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `Association.validateAssociationEndTypes` | 1 | unattributed |  |
| violation | `Import.validateImportTopLevelVisibility` | 1 | transform | import emitted without its visibility |
| skip | `operation specializes(` | 187 | engine |  |
| skip | `eval-unmapped` | 159 | runtime |  |
| skip | `operation libraryNamespace(` | 143 | engine |  |
| skip | `expected ) at token ('eof', '')` | 135 | runtime |  |
| skip | `operation isOwnedCrossFeature(` | 123 | engine |  |
| skip | `undetermined comparison` | 72 | runtime |  |
| skip | `operation importedMemberships(` | 62 | engine |  |
| skip | `operation inheritedMemberships(` | 59 | engine |  |
| skip | `operation redefinesFromLibrary(` | 48 | engine |  |
| skip | `undetermined` | 47 | runtime |  |
| skip | `operation isFeaturedWithin(` | 45 | engine |  |
| skip | `expected endif at token ('eof', '')` | 45 | runtime |  |
| skip | `trailing tokens [('name', 'implied'), ('name', 'di` | 41 | runtime |  |
| skip | `operation ownedCrossFeature(` | 41 | engine |  |
| skip | `operation specializesFromLibary(` | 41 | engine |  |
| skip | `expected name at token ('eof', '')` | 41 | runtime |  |
| skip | `operation multiplicities(` | 41 | engine |  |
| skip | `operation isFeaturingType(` | 41 | engine |  |
| skip | `operation oclIsKind(` | 16 | engine |  |
| skip | `operation canAccess(` | 8 | engine |  |
| skip | `operation referencedFeatureTarget(` | 7 | engine |  |
| skip | `operation isSubactionUsage(` | 7 | engine |  |
| skip | `operation contains(` | 4 | engine |  |
| skip | `operation isSubstateUsage(` | 4 | engine |  |
| skip | `operation modelLevelEvaluable(` | 3 | engine |  |
| skip | `->isUnique has no lowering yet (O3)` | 3 | runtime |  |
| skip | `operation parameterDirection(` | 2 | engine |  |
| skip | `operation resolveGlobal(` | 2 | engine |  |
| skip | `operation inputParameter(` | 2 | engine |  |
| skip | `operation subsetsChain(` | 2 | engine |  |
| skip | `operation valueOf(` | 1 | engine |  |
