# v2 validation triage

211 elements, 4276 checks (+8358 derivations), 14 violations, 235 skipped, coverage 95%

| kind | family | count | owner | note |
|---|---|---:|---|---|
| violation | `Feature.checkFeatureParameterRedefinition` | 12 | library | the rule compares parameters against the supertype's owned features; our KerML library stubs are name-only, so Cases::Case etc. carry no parameter features |
| violation | `Association.validateAssociationRelatedTypes` | 2 | transform | related types not emitted on the association |
| skip | `corpus-defect` | 204 | runtime |  |
| skip | `undetermined` | 29 | runtime |  |
| skip | `eval-unmapped` | 2 | runtime |  |
