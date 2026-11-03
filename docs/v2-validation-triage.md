# v2 validation triage

211 elements, 4137 checks (+8291 derivations), 17 violations, 441 skipped, coverage 90%

| kind | family | count | owner | note |
|---|---|---:|---|---|
| violation | `Feature.checkFeatureParameterRedefinition` | 12 | unattributed |  |
| violation | `Usage.checkUsageVariationDefinitionSpecialization` | 3 | transform | the transform emits no library specialization edges (O6) |
| violation | `Association.validateAssociationRelatedTypes` | 2 | transform | related types not emitted on the association |
| skip | `corpus-defect` | 204 | runtime |  |
| skip | `->closure(typingFeatures())` | 67 | runtime |  |
| skip | `operation allSuperTypes(` | 67 | engine |  |
| skip | `operation isCartesianProduct(` | 67 | engine |  |
| skip | `undetermined` | 29 | runtime |  |
| skip | `operation isUnique(` | 3 | engine |  |
| skip | `operation triggerPayloadParameter(` | 2 | engine |  |
| skip | `eval-unmapped` | 2 | runtime |  |
