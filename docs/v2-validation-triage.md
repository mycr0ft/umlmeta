# v2 validation triage

218 elements, 4533 checks (+8433 derivations), 2 violations, 36 skipped, coverage 99%

| kind | family | count | owner | note |
|---|---|---:|---|---|
| violation | `Association.validateAssociationRelatedTypes` | 2 | model | the vehicle model types frontAxle AND rearAxle both as Axle, so relatedType is a 1-element set; relatedType size >= 2 fails under set semantics |
| skip | `undetermined` | 26 | runtime |  |
| skip | `undetermined comparison` | 10 | runtime |  |
