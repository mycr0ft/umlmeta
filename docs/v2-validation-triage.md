# v2 validation triage

143 elements, 2411 checks (+5272 derivations), 50 violations, 781 skipped, coverage 76%

| kind | family | count | owner | note |
|---|---|---:|---|---|
| violation | `Connector.checkConnectorBinarySpecialization` | 4 | transform | the transform emits no library specialization edges (O6) |
| violation | `ReferenceSubsetting.validateSubsettingFeaturingTypes` | 4 | transform | same rule on the reference subsetting |
| violation | `Subsetting.validateSubsettingFeaturingTypes` | 4 | transform | subsettingFeature.canAccess(subsettedFeature) needs the featuring-type edges; the transform emits subsetting but not featuring |
| violation | `Expression.validateExpressionResultParameterMembership` | 3 | transform | LiteralInteger built without its ReturnParameterMembership |
| violation | `ParameterMembership.validateParameterMembershipParameterDirection` | 2 | runtime | parameterDirection default is derivable but the membership's ownedMemberParameter inverse is not set |
| violation | `ParameterMembership.validateParameterMembershipOwningType` | 2 | runtime | owningType is the inverse of owningMembership; not set |
| violation | `ConnectionUsage.checkConnectionUsageBinarySpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `PartUsage.validatePartUsagePartDefinition` | 2 | transform | ConnectionUsage is never typed by a PartDefinition |
| violation | `Connector.checkConnectorTypeFeaturing` | 2 | transform | connector featuringType not emitted; rule falls back to isFeaturedWithin(null) which needs featuring edges |
| violation | `TransitionUsage.validateTransitionUsageSuccession` | 2 | transform | the succession edge the rule needs is not emitted |
| violation | `TransitionUsage.checkTransitionUsageSuccessionBindingConnector` | 2 | transform | the succession binding connector the rule requires is not emitted |
| violation | `TransitionUsage.checkTransitionUsageSourceBindingConnector` | 2 | transform | same, for the source binding connector |
| violation | `TransitionUsage.checkTransitionUsageSuccessionSourceSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| violation | `Connector.validateConnectorRelatedFeatures` | 2 | transform | ConnectionUsage carries no relatedFeature ends |
| violation | `CaseDefinition.validateCaseDefinitionSubjectParameterPosition` | 2 | transform | subject parameter emitted without its position |
| violation | `Function.validateFunctionResultParameterMembership` | 2 | transform | function result parameter membership not emitted |
| violation | `MultiplicityRange.validateMultiplicityRangeBounds` | 1 | runtime | bound memberships carry no value; derived bound is null |
| violation | `Multiplicity.checkMultiplicityTypeFeaturing` | 1 | transform | multiplicity's featuringType derives from its owning feature's featuringType; the owning chain is incomplete |
| violation | `EnumerationDefinition.validateEnumerationDefinitionIsVariation` | 1 | transform | variation flag not emitted on an enumeration definition |
| violation | `StateSubactionMembership.validateStateSubactionMembershipOwningType` | 1 | runtime | same inverse-maintenance gap |
| violation | `CaseUsage.validateCaseUsageSubjectParameterPosition` | 1 | transform | same |
| violation | `CalculationUsage.checkCalculationUsageSubcalculationSpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `ConnectionDefinition.validateConnectionDefinitionIsSufficient` | 1 | transform | connection ends not sufficient: related features missing |
| violation | `AssociationStructure.checkAssociationStructureBinarySpecialization` | 1 | transform | the transform emits no library specialization edges (O6) |
| violation | `Association.validateAssociationRelatedTypes` | 1 | transform | related types not emitted on the association |
| violation | `Association.validateAssociationEndTypes` | 1 | transform | an end feature carries no type; the transform emits end usages untyped |
| violation | `Import.validateImportTopLevelVisibility` | 1 | transform | import emitted without its visibility |
| skip | `eval-unmapped` | 211 | runtime |  |
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
