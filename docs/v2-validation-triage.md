# v2 validation triage

171 elements, 3032 checks (+6706 derivations), 10 violations, 951 skipped, coverage 76%

| kind | family | count | owner | note |
|---|---|---:|---|---|
| violation | `Association.validateAssociationRelatedTypes` | 2 | transform | related types not emitted on the association |
| violation | `TransitionUsage.validateTransitionUsageSuccession` | 2 | transform | the succession edge the rule needs is not emitted |
| violation | `TransitionUsage.checkTransitionUsageSuccessionBindingConnector` | 2 | transform | the succession binding connector the rule requires is not emitted |
| violation | `TransitionUsage.checkTransitionUsageSourceBindingConnector` | 2 | transform | same, for the source binding connector |
| violation | `TransitionUsage.checkTransitionUsageSuccessionSourceSpecialization` | 2 | transform | the transform emits no library specialization edges (O6) |
| skip | `eval-unmapped` | 207 | runtime |  |
| skip | `undetermined comparison` | 200 | runtime |  |
| skip | `expected ) at token ('eof', '')` | 171 | runtime |  |
| skip | `undetermined` | 96 | runtime |  |
| skip | `expected endif at token ('eof', '')` | 57 | runtime |  |
| skip | `trailing tokens [('name', 'implied'), ('name', 'di` | 53 | runtime |  |
| skip | `expected name at token ('eof', '')` | 53 | runtime |  |
| skip | `operation allSuperTypes(` | 53 | engine |  |
| skip | `operation isCartesianProduct(` | 53 | engine |  |
| skip | `->isUnique has no lowering yet (O3)` | 3 | runtime |  |
| skip | `corpus-defect` | 3 | runtime |  |
| skip | `operation triggerPayloadParameter(` | 2 | engine |  |
