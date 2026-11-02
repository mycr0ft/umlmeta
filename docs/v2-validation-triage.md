# v2 validation triage

131 elements, 1898 checks (+4026 derivations), 284 violations, 1876 skipped

| kind | family | count | owner | note |
|---|---|---:|---|---|
| violation | `Type.checkTypeSpecialization` | 55 | transform | the transform emits no library specialization edges (O6) |
| violation | `Feature.checkFeatureSpecialization` | 37 | transform | same: no library specialization edge on features |
| violation | `Usage.validateUsageIsReferential` | 26 | unattributed |  |
| violation | `Class.checkClassSpecialization` | 16 | transform | same: no library specialization edge on classes |
| violation | `OccurrenceUsage.checkOccurrenceUsageSpecialization` | 16 | unattributed |  |
| violation | `Step.checkStepSpecialization` | 9 | unattributed |  |
| violation | `ActionUsage.checkActionUsageSpecialization` | 7 | unattributed |  |
| violation | `EndFeatureMembership.validateEndFeatureMembershipIsEnd` | 6 | unattributed |  |
| violation | `ReferenceUsage.validateReferenceUsageIsReference` | 5 | unattributed |  |
| violation | `ActionDefinition.checkActionDefinitionSpecialization` | 5 | unattributed |  |
| violation | `Behavior.checkBehaviorSpecialization` | 5 | unattributed |  |
| violation | `AttributeUsage.validateAttributeUsageIsReference` | 4 | unattributed |  |
| violation | `AttributeUsage.checkAttributeUsageSpecialization` | 4 | unattributed |  |
| violation | `Connector.checkConnectorSpecialization` | 4 | unattributed |  |
| violation | `Connector.validateConnectorRelatedFeatures` | 4 | unattributed |  |
| violation | `Expression.validateExpressionResultParameterMembership` | 3 | unattributed |  |
| violation | `Expression.checkExpressionSpecialization` | 3 | unattributed |  |
| violation | `EnumerationUsage.validateAttributeUsageIsReference` | 3 | unattributed |  |
| violation | `EnumerationUsage.checkAttributeUsageSpecialization` | 3 | unattributed |  |
| violation | `ItemDefinition.checkItemDefinitionSpecialization` | 3 | unattributed |  |
| violation | `Structure.checkStructureSpecialization` | 3 | unattributed |  |
| violation | `LiteralInteger.checkLiteralIntegerSpecialization` | 2 | unattributed |  |
| violation | `LiteralExpression.checkLiteralExpressionSpecialization` | 2 | unattributed |  |
| violation | `PortUsage.validatePortUsageIsReference` | 2 | unattributed |  |
| violation | `PortUsage.checkPortUsageSpecialization` | 2 | unattributed |  |
| violation | `EventOccurrenceUsage.validateEventOccurrenceUsageIsReference` | 2 | unattributed |  |
| violation | `ParameterMembership.validateParameterMembershipOwningType` | 2 | unattributed |  |
| violation | `ConnectionUsage.checkConnectionUsageSpecialization` | 2 | unattributed |  |
| violation | `PartUsage.checkPartUsageSpecialization` | 2 | unattributed |  |
| violation | `PartUsage.validatePartUsagePartDefinition` | 2 | unattributed |  |
| violation | `ItemUsage.checkItemUsageSpecialization` | 2 | unattributed |  |
| violation | `ConnectorAsUsage.validateUsageIsReferential` | 2 | unattributed |  |
| violation | `DataType.checkDataTypeSpecialization` | 2 | unattributed |  |
| violation | `PartDefinition.checkPartDefinitionSpecialization` | 2 | unattributed |  |
| violation | `StateUsage.checkStateUsageSpecialization` | 2 | unattributed |  |
| violation | `TransitionUsage.checkTransitionUsageSpecialization` | 2 | unattributed |  |
| violation | `TransitionUsage.validateTransitionUsageSuccession` | 2 | unattributed |  |
| violation | `TransitionUsage.checkTransitionUsageSuccessionSourceSpecialization` | 2 | unattributed |  |
| violation | `Succession.checkSuccessionSpecialization` | 2 | unattributed |  |
| violation | `UseCaseDefinition.checkUseCaseDefinitionSpecialization` | 2 | unattributed |  |
| violation | `CaseDefinition.checkCaseDefinitionSpecialization` | 2 | unattributed |  |
| violation | `CaseDefinition.validateCaseDefinitionSubjectParameterPosition` | 2 | unattributed |  |
| violation | `CalculationDefinition.checkCalculationDefinitionSpecialization` | 2 | unattributed |  |
| violation | `Function.validateFunctionResultParameterMembership` | 2 | unattributed |  |
| violation | `Function.checkFunctionSpecialization` | 2 | unattributed |  |
| violation | `MultiplicityRange.validateMultiplicityRangeBounds` | 1 | unattributed |  |
| violation | `Multiplicity.checkMultiplicitySpecialization` | 1 | unattributed |  |
| violation | `EnumerationDefinition.validateEnumerationDefinitionIsVariation` | 1 | unattributed |  |
| violation | `StateDefinition.checkStateDefinitionSpecialization` | 1 | unattributed |  |
| violation | `StateSubactionMembership.validateStateSubactionMembershipOwningType` | 1 | unattributed |  |
| violation | `UseCaseUsage.checkUseCaseUsageSpecialization` | 1 | unattributed |  |
| violation | `CaseUsage.validateCaseUsageSubjectParameterPosition` | 1 | unattributed |  |
| violation | `CaseUsage.checkCaseUsageSpecialization` | 1 | unattributed |  |
| violation | `CalculationUsage.checkCalculationUsageSpecialization` | 1 | unattributed |  |
| violation | `ConnectionDefinition.checkConnectionDefinitionSpecializations` | 1 | unattributed |  |
| violation | `ConnectionDefinition.validateConnectionDefinitionIsSufficient` | 1 | unattributed |  |
| violation | `AssociationStructure.checkAssociationStructureSpecialization` | 1 | unattributed |  |
| violation | `Association.validateAssociationRelatedTypes` | 1 | unattributed |  |
| violation | `Association.checkAssociationSpecialization` | 1 | unattributed |  |
| violation | `Import.validateImportTopLevelVisibility` | 1 | unattributed |  |
| skip | `eval-unmapped` | 231 | runtime |  |
| skip | `operation specializes(` | 167 | engine |  |
| skip | `operation directionOf(` | 165 | engine |  |
| skip | `operation effectiveName(` | 131 | engine |  |
| skip | `operation escapedName(` | 131 | engine |  |
| skip | `operation effectiveShortName(` | 131 | engine |  |
| skip | `operation libraryNamespace(` | 131 | engine |  |
| skip | `expected ) at token ('eof', '')` | 123 | runtime |  |
| skip | `operation isOwnedCrossFeature(` | 111 | engine |  |
| skip | `operation importedMemberships(` | 58 | engine |  |
| skip | `operation inheritedMemberships(` | 55 | engine |  |
| skip | `operation redefinesFromLibrary(` | 44 | engine |  |
| skip | `operation isFeaturedWithin(` | 41 | engine |  |
| skip | `expected endif at token ('eof', '')` | 41 | runtime |  |
| skip | `trailing tokens [('name', 'implied'), ('name', 'di` | 37 | runtime |  |
| skip | `operation ownedCrossFeature(` | 37 | engine |  |
| skip | `operation specializesFromLibary(` | 37 | engine |  |
| skip | `expected name at token ('eof', '')` | 37 | runtime |  |
| skip | `operation multiplicities(` | 37 | engine |  |
| skip | `operation isFeaturingType(` | 37 | engine |  |
| skip | `trailing tokens [('name', 'isComposite'), ('eof', ` | 28 | runtime |  |
| skip | `operation oclIsKind(` | 16 | engine |  |
| skip | `operation referencedFeatureTarget(` | 7 | engine |  |
| skip | `operation isSubactionUsage(` | 7 | engine |  |
| skip | `operation subSequence(` | 5 | engine |  |
| skip | `operation contains(` | 4 | engine |  |
| skip | `operation isSubstateUsage(` | 4 | engine |  |
| skip | `undetermined comparison` | 4 | runtime |  |
| skip | `operation canAccess(` | 4 | engine |  |
| skip | `operation modelLevelEvaluable(` | 3 | engine |  |
| skip | `->isUnique has no lowering yet (O3)` | 3 | runtime |  |
| skip | `operation parameterDirection(` | 2 | engine |  |
| skip | `operation resolveGlobal(` | 2 | engine |  |
| skip | `operation inputParameter(` | 2 | engine |  |
| skip | `operation subsetsChain(` | 2 | engine |  |
| skip | `operation valueOf(` | 1 | engine |  |
