# v2 validation triage

218 elements, 4533 checks (+8433 derivations), 4 violations, 36 skipped, coverage 99%

| kind | family | count | owner | note |
|---|---|---:|---|---|
| violation | `Association.validateAssociationRelatedTypes` | 2 | model | the vehicle model types frontAxle AND rearAxle both as Axle, so relatedType is a 1-element set; relatedType size >= 2 fails under set semantics |
| violation | `Function.validateFunctionResultParameterMembership` | 2 | corpus | the joined body counts inheritedMembership results too: the real type chain (Cases::Case, Performances::Evaluation) carries `return ref result` members, so `featureMembership->selectByKind(RPM)->size() = 1` fails every case whose own result exists; as written the check cannot hold for any model |
| skip | `undetermined` | 26 | runtime |  |
| skip | `undetermined comparison` | 10 | runtime |  |
