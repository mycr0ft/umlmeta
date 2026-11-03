# v2 validation triage

143 elements, 2416 checks (+5272 derivations), 269 violations, 776 skipped, coverage 76%

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
| violation | `ReferenceSubsetting.validateSubsettingFeaturingTypes` | 4 | transform | same rule on the reference subsetting |
| violation | `Subsetting.validateSubsettingFeaturingTypes` | 4 | transform | subsettingFeature.canAccess(subsettedFeature) needs the featuring-type edges; the transform emits subsetting but not featuring |
| violation | `Expression.validateExpressionResultParameterMembership` | 3 | transform | LiteralInteger built without its ReturnParameterMembership |
| violation | `Expression.checkExpressionSpecialization` | 3 | transform | the transform emits no library specialization edges (O6) |
| violation | `EnumerationUsage.checkAttributeUsageSpecialization` | 3 | transform | the transform emits no library specialization edges (O6) |
| violation | `ItemDefinition.checkItemDefinitionSpecialization` | 3 | transform | the transform emits no library specialization edges (O6) |
| violation | `Structure.checkStructureSpecialization` | 3 | transform | the transform emits no library specialization edges (O6) |
| violation | `LiteralInteger.checkLiteralIntegerSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `LiteralExpression.checkLiteralExpressionSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `PortUsage.checkPortUsageSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `EventOccurrenceUsage.checkEventOccurrenceUsageSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `ParameterMembership.validateParameterMembershipParameterDirection` | 2 | runtime | parameterDirection default is derivable but the membership's ownedMemberParameter inverse is not set |
| violation | `ParameterMembership.validateParameterMembershipOwningType` | 2 | runtime | owningType is the inverse of owningMembership; not set |
| violation | `ConnectionUsage.checkConnectionUsageSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `ConnectionUsage.checkConnectionUsageBinarySpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `PartUsage.checkPartUsageSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `PartUsage.validatePartUsagePartDefinition` | 2 | transform | ConnectionUsage is never typed by a PartDefinition |
| violation | `ItemUsage.checkItemUsageSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `Connector.checkConnectorTypeFeaturing` | 2 | transform | connector featuringType not emitted; rule falls back to isFeaturedWithin(null) which needs featuring edges |
| violation | `DataType.checkDataTypeSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `PartDefinition.checkPartDefinitionSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `StateUsage.checkStateUsageSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `TransitionUsage.checkTransitionUsageSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `TransitionUsage.validateTransitionUsageSuccession` | 2 | transform | the succession edge the rule needs is not emitted |
| violation | `TransitionUsage.checkTransitionUsageSuccessionBindingConnector` | 2 | transform | the succession binding connector the rule requires is not emitted |
| violation | `TransitionUsage.checkTransitionUsageSourceBindingConnector` | 2 | transform | same, for the source binding connector |
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
| violation | `Multiplicity.checkMultiplicityTypeFeaturing` | 1 | transform | multiplicity's featuringType derives from its owning feature's featuringType; the owning chain is incomplete |
| violation | `Multiplicity.checkMultiplicitySpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `EnumerationDefinition.validateEnumerationDefinitionIsVariation` | 1 | transform | variation flag not emitted on an enumeration definition |
| violation | `StateDefinition.checkStateDefinitionSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `StateSubactionMembership.validateStateSubactionMembershipOwningType` | 1 | runtime | same inverse-maintenance gap |
| violation | `UseCaseUsage.checkUseCaseUsageSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `CaseUsage.validateCaseUsageSubjectParameterPosition` | 1 | transform | same |
| violation | `CaseUsage.checkCaseUsageSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `CalculationUsage.checkCalculationUsageSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `CalculationUsage.checkCalculationUsageSubcalculationSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `ConnectionDefinition.checkConnectionDefinitionSpecializations` | 1 | transform | no library specialization edge (the O6 family) |
| violation | `ConnectionDefinition.validateConnectionDefinitionIsSufficient` | 1 | transform | connection ends not sufficient: related features missing |
| violation | `ConnectionDefinition.checkConnectionDefinitionBinarySpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `AssociationStructure.checkAssociationStructureSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `AssociationStructure.checkAssociationStructureBinarySpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `Association.validateAssociationRelatedTypes` | 1 | transform | related types not emitted on the association |
| violation | `Association.checkAssociationSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `Association.validateAssociationEndTypes` | 1 | transform | an end feature carries no type; the transform emits end usages untyped |
| violation | `Import.validateImportTopLevelVisibility` | 1 | transform | import emitted without its visibility |
| skip | `eval-unmapped` | 206 | runtime |  |
| skip | `undetermined comparison` | 136 | runtime |  |
| skip | `expected ) at token ('eof', '')` | 135 | runtime |  |
| skip | `undetermined` | 85 | runtime |  |
| skip | `expected endif at token ('eof', '')` | 45 | runtime |  |
| skip | `trailing tokens [('name', 'implied'), ('name', 'di` | 41 | runtime |  |
| skip | `expected name at token ('eof', '')` | 41 | runtime |  |
| skip | `operation allSuperTypes(` | 41 | engine |  |
| skip | `operation isCartesianProduct(` | 41 | engine |  |
| skip | `->isUnique has no lowering yet (O3)` | 3 | runtime |  |
| skip | `operation triggerPayloadParameter(` | 2 | engine |  |
