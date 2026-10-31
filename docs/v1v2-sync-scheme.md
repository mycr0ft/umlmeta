# Keeping a SysML v2 model in step with a continuing SysML v1 model

**Status:** current scheme, as implemented · umlmeta 0.2.x · Jon R. Fox

This is the *operating* document: how repeated updates from a legacy (or still
under development) SysML v1 model flow into a SysML v2 model that people also
edit, with umlmeta as shipped. The companion document
`docs/v1-v2-linkage-pathway.md` is the design and rationale (levels, milestone
history, open questions); this one is what to run and what to expect.

---

## 1. The model of record

A team in transition keeps two models that are both alive:

| Model | Owns | Changed by |
|---|---|---|
| SysML v1 (legacy / continuing engineering) | everything the mapping covers; the mapping authority | the engineering toolchain, weekly or daily |
| SysML v2 | v2-native content (things the legacy model cannot express) and v2-side corrections | architects, reviewers, hand edits |

Neither is a build artifact of the other. The scheme keeps them *convergent*
without pretending they are identical:

- a v1 change that the mapping covers is pushed into v2 automatically;
- a v2 edit is preserved verbatim until someone edits the same element on
  the v1 side, at which point it becomes an explicit conflict;
- everything the mapping cannot carry is recorded per run, not forgotten.

The v1 model is never modified by the tool. Nothing here writes to the legacy
toolchain's files.

---

## 2. The artifacts

Per model pair, four files (paths are yours; the names below are the
convention the CLI uses):

| File | What it is | Commit it? |
|---|---|---|
| `<name>.v2.json` | the SysML v2 model, `umlmeta.v2json/1` (metaclass-shaped JSON, every element carries its `elementId`) | yes — it is the product |
| `<name>.v1v2link.json` | the **sidecar**: the pair record (`umlmeta.v1v2link/1`) | yes — deleting it forfeits rename repair and the elision history |
| `<name>.sysml` | the same model as SysML v2 textual notation (review surface) | optional, regenerate on demand |
| `<name>.v1.xmi` | the v1 snapshot the pair was last synchronised against | yes, or pin the toolchain revision |

The JSON is deterministic (element order and identities are derived, not
allocated at random), so a clean sync produces a *no-op diff* — which is what
makes the pair reviewable in git.

---

## 3. Identity

Every v2 element carries an `elementId` of the form
`v1v2:<uuid5>`, derived from the element's declared path plus its metaclass
(same-name siblings take an occurrence index; unnamed members anchor on their
nearest named ancestor). Two consequences matter operationally:

- **Re-running the transform does not renumber anything.** The ids of
  untouched elements are the same in every week's output (L1/L2).
- **A pure rename or move changes the derived id** — and the sidecar repairs
  it (`§7`).

Ids are deliberately **not** the v1 `xmi:id`: Cameo delta-snapshots and
TeamworkCloud check-ins re-mint those on save, so an xmi id identifies a
serialisation, not an element. The xmi id is kept in the sidecar as a
per-snapshot cache.

Two content keys live beside the identity and do different jobs:

| Key | Sees a rename as | Used for |
|---|---|---|
| `signature` (`v1_hash`/`v2_hash`) | an edit | deciding *who changed what* |
| `identity_key` (`v1_key`/`v2_key`) | unchanged | repairing identity after a rename/move |

---

## 4. The update loop

Once per sync cycle (weekly, per milestone, per release — your cadence):

```bash
# 1. first time only: create the pair
umlmeta transform legacy.xmi \
    -o model.v2.json \
    --sidecar model.v1v2link.json \
    --text model.sysml \
    [--side-channel] [--library-stub]

# 2. every cycle: push the new v1 snapshot onto the existing v2 model
umlmeta sync \
    --v1 legacy.xmi                       # one or more files: one scope
    --sidecar model.v1v2link.json         # the pair record from last cycle
    --model   model.v2.json               # the v2 model as it stands
    -o        model.v2.json               # merged result (in place, or a copy)
    --sidecar-out model.v1v2link.json     # RE-BASELINE: always do this

# 3. review
umlmeta diff model.v2.json.prev model.v2.json    # what actually moved
cat model.sysml                                  # what a human reads
git commit model.v2.json model.v1v2link.json model.sysml
```

Step 2's report is the record of the cycle:

```
merged -> model.v2.json: {'v1-only': 2, 'v2-only': 1, 'unchanged': 2,
 'conflict': 0, 'v1-added': 4, 'v1-removed': 0, 'v2-native': 0,
 'renamed': 0, 'ambiguous-rename': 0}
```

Counts are per element identity, and *memberships ride with their content*:
adding one part (`Brake`) adds it plus its owning membership, so `v1-added`
reads 4 for two real additions. Read the diff, not the counts, for a change
review.

**Re-baselining is not optional.** `--sidecar-out` rewrites `v1_hash`/
`v2_hash` against the merged result; skip it and the next cycle re-reports
last week's changes forever.

---

## 5. What each element does

Classification of every element identity in the union of (new v1 mapping,
existing v2 model), decided by comparing current content against the sidecar's
snapshot:

| Class | Meaning | Result |
|---|---|---|
| `unchanged` | nobody touched it | the existing object is kept as-is |
| `v1-only` | only the v1 side changed | the freshly transformed object replaces it |
| `v2-only` | only the v2 side changed | the existing (edited) object is preserved verbatim |
| `both-changed` | **conflict** | v2 content wins, one conflict record |
| `v1-added` | new in v1 | added |
| `v1-removed` | gone from v1, untouched in v2 | dropped |
| `v2-native` | an element the mapping never produced | kept (it has no v1 counterpart) |
| `renamed` | v1 path changed, identity repaired | fresh content under the OLD identity |
| `ambiguous-rename` | several equally plausible matches | **nothing adopted** — see §7 |
| `deleted-in-v1-edited-in-v2` | **conflict** | v1 says delete, v2 says edited → kept, recorded |
| `blocked-by-edited-container` | **conflict** | a child changed in v1 inside a container edited in v2 → child change refused, recorded |

Two structural rules make this work:

- a re-mapped child forces its **content ancestors** to be rebuilt from the
  fresh transform (otherwise the child would be smuggled into a stale parent);
- relationships (memberships, typings) are scaffolding, not content: they
  follow their owner and are never classified as v2-native.

---

## 6. A worked cycle (real output)

Week 0 — the pair is created from a three-element legacy package:

```bash
$ umlmeta transform legacy.xmi -o model.v2.json --sidecar link.json --text model.sysml
wrote model.v2.json + link.json
```

```
package Vehicle {
  attribute def Kilogram;
  occurrence def Engine {
    attribute power : Kilogram;
  }
  occurrence def Wheel;
}
```

Week 1 — the legacy model retypes `power` to a new `Watt` datatype and adds a
`Brake`; meanwhile an architect renames `Wheel` to `RoadWheel` in the v2 model:

```bash
$ umlmeta sync --v1 legacy.next.xmi --sidecar link.json --model model.v2.json \
               -o merged.json --sidecar-out link.next.json
merged -> merged.json: {'v1-only': 2, 'v2-only': 1, 'unchanged': 2,
 'conflict': 0, 'v1-added': 4, ...}
```

```
package Vehicle {
  attribute def Kilogram;
  attribute def Watt;
  occurrence def Engine {
    attribute power : Watt;      ← the v1 change won
  }
  occurrence def RoadWheel;       ← the v2 edit survived
  occurrence def Brake;           ← the v1 addition arrived
}
```

Week 2 — v1 renames `Engine` to `Motor` while v2 renamed it to `EngineV2`:

```bash
$ umlmeta sync --v1 legacy.motor.xmi --sidecar link.next.json --model model.both.json -o conflict.json
CONFLICT both-changed Vehicle::Engine (v1v2:0a62e90f-…)
merged -> conflict.json: {'v1-only': 1, 'v2-only': 0, 'unchanged': 5,
 'conflict': 1, 'v1-added': 2, ...}
$ echo $?
1
```

The v2 content (`EngineV2`) is kept, the exit code is 1, and the conflict is a
record — never a silent overwrite.

Resolution — the team decides the v1 rename is authoritative, reverts the v2
side, and re-syncs:

```bash
$ umlmeta sync --v1 legacy.motor.xmi --sidecar link.next.json \
               --model model.reverted.json -o resolved.json --sidecar-out link.resolved.json
merged -> resolved.json: {'v1-only': 1, ..., 'renamed': 1, 'conflict': 0}
```

```
occurrence def Motor { ... }      ← the rename applied
```

The element's identity never moved through any of it:

```
link.json           Vehicle::Engine -> v1v2:0a62e90f-a4a4-5…
link.next.json      Vehicle::Engine -> v1v2:0a62e90f-a4a4-5…
link.resolved.json  Vehicle::Motor  -> v1v2:0a62e90f-a4a4-5…
```

---

## 7. Renames, moves, deletions

**Renames and moves are repaired automatically.** The fresh transform derives a
new id (the path changed); the sidecar's `identity_key` — content with the
names removed — matches the element to the record the link already holds, and
the fresh content takes the *old* identity. Descendants follow by path suffix
under the renamed ancestor. The gate is uniqueness in both directions: two
content-identical siblings, or one candidate claimed by two records, is
`ambiguous-rename` and **nothing is adopted** (the tool never guesses). If that
happens, disambiguate in the model — a name, a property, a stereotype — and
re-run; or accept the new identity and re-baseline the sidecar.

A rename that collides with a v2 edit of the same element is `both-changed`:
identity stable, v2 content kept. Resolve as in §6.

**Deletions** flow from v1 only. Delete an element in v1 and it leaves the pair
on the next sync — unless it was edited in v2, which is
`deleted-in-v1-edited-in-v2` (kept and recorded). Delete deliberately on both
sides, or accept the conflict, then re-baseline.

> **Caveat when v2 wins a rename:** the re-baselined sidecar records the
> *mapped* element's path, which is the v2 spelling (`Vehicle::EngineV2`) while
> the v1 element is still `Engine`. Matching continues by identity, so updates
> keep working, but the honest fix is to make the same rename in v1 — a pair
> whose two halves disagree on a name will keep producing path drift.

---

## 8. What did not cross

Every run records what the mapping deliberately did not carry
(`_v1_elisions`, written to the sidecar):

```json
"elisions": [{"v1_kind": "Continuation", "v1_name": "cont",
              "v1_path": "ElidePkg::Seq::cont", "v1_hash": "f4dd82…",
              "anchor": "7.7.8.2",
              "rule": "Table 11 (7.7.8.2): the formal 2.0 transformation does not map this element"}],
"reader_gaps": {"unmapped": [], "unmapped_features": []}
```

`reader_gaps` is the R1 half: metaclasses the XMI reader could not construct
and features it could not read. Both blocks are per run — check them *before*
declaring a milestone, not after.

The permanently unmapped families (Table-11 interaction occurrences, Gates,
Continuations, `Extend`/`ExtensionPoint`, initial/final activity nodes and
their edges) have a policy, not an accident:

- default: skip and record;
- `umlmeta transform --side-channel`: additionally carry each one into the v2
  model as a `v1Elided` metadata usage owned by the nearest mapped element —
  `v1Kind` / `v1Path` / `v1Hash` as literal features — so the content survives
  in a model a v2 tool can read.

Choose the side channel when the linked pair is itself a deliverable; skip it
when v1 remains the only authority for that content.

---

## 9. Library references

The transformation carries `SysMLv1Library` references name-only (probability
and rate, the edge-weight metadata, port/refine/trace metadata, allocation and
variable-action library types) because the library is not input to the
mapping. A v2 tool then cannot resolve them.

```bash
umlmeta transform legacy.xmi -o model.v2.json --library-stub
```

`--library-stub` collects every referenced library name (contained *or* merely
referenced) into one `SysMLv1Library` package with a definition per name and a
feature per nested name, and types the metadata usages against it. Gate before
shipping a v2 model to another tool:

```python
from umlmeta import v2_library as LIB
assert LIB.unresolved([root]) == []
```

---

## 10. Scope: one model spans several files

A legacy project is rarely one file. Pass every file and it is read as one
identity space — relative `other.xmi#id` references resolve across files, and
the transformation shares one index across all roots:

```bash
umlmeta transform core.xmi vehicle.xmi brakes.xmi -o model.v2.json --sidecar link.json
```

If a file is left out, references into it are refused
(`UnmappedFeature: … external/unordered …`) — that refusal is the scope
boundary talking, not a mapping gap. Widen the file list, not the mapping.

---

## 11. Reviewing a cycle

- **Machine view:** `umlmeta diff old.json new.json` — one line per added,
  removed or changed element identity; exit code 1 when anything differs, which
  makes it usable in CI.
- **Human view:** `<name>.sysml` — the same model in the calibrated notation
  the v1→v2 emitter writes, generated from the AS (so the text cannot drift
  from the model).
- **git:** the JSON is deterministic, so a clean cycle is a no-op diff and a
  real cycle shows exactly the elements that moved. Commit the sidecar with the
  model — reverting the model without the sidecar puts the link out of step.

---

## 12. Invariants the tooling enforces

Each of these is an oracle in `check_v1_to_v2_as.py`, not a convention:

| Invariant | Meaning |
|---|---|
| deterministic identity | re-transforming an unchanged snapshot changes no `elementId` |
| edit locality | an insertion elsewhere leaves untouched identities untouched |
| repair uniqueness | a rename is repaired only when the match is unique |
| clean sync is a no-op | `graph_hash(merged) == sidecar.v2_graph_hash` |
| no silent loss | every elided element appears in `elisions`; malformed
  documents and unknown metaclasses are rejected |
| resolved model | no library name left unresolvable when the stub is built |
| v2 fidelity | write → read → write of the v2 model is byte-identical |

---

## 13. Failure modes

| Symptom | Cause | Action |
|---|---|---|
| `UnmappedFeature: … external/unordered …` | a referenced element is outside the transformed scope | add the file/package to the command |
| `ambiguous-rename` | content-identical siblings renamed at once | disambiguate in v1, or accept new identities and re-baseline |
| `both-changed` conflict every week | sidecar not re-baselined after resolution | always pass `--sidecar-out` |
| Every element reported `v1-only` | sidecar from a different model or never written | re-baseline from a known-good pair (`umlmeta link`) |
| `link` empties the records | a v2 JSON has no v1 provenance | it now carries the previous sidecar's records through; supply `--sidecar` pointing at the existing file |
| merged model looks stale | `-o` wrote elsewhere; the next cycle read the old file | check the paths in the report line |
| conflicts on elements nobody edited | an out-of-band tool rewrote the v2 model's names/anchors | diff, then re-baseline once the pair agrees |
| sidecar hash differs but no diff | element ordering or a v2-native addition | expected; the hash covers content, `diff` covers identity |

---

## 14. Current limits (stated, not hidden)

- **No reverse transformation.** v2 → v1 is not implemented and the mapping is
  not invertible; v2-side changes are carried back to v1 by people.
- **No automatic conflict resolution.** Conflicts are surfaced and recorded;
  the policy (v1 wins / v2 wins / reconcile by hand) is a team decision.
- **Full re-transform plus merge**, not incremental subtree remapping. The
  cost is linear in model size; the merge is what preserves v2 edits.
- **Elided content is not semantically merged.** With the side channel the v1
  text survives as metadata; it is not re-mapped on later cycles.
- **v2-native elements under a removed parent** are reported, not re-parented.
- **The textual notation is a review surface**, not a round-trip format: the
  JSON is the persistence format.
- **`elementId` derivation is path-based**, so a rename is repaired through the
  sidecar; without a sidecar a rename is a new element.

---

## Appendix A — formats

**Sidecar** (`umlmeta.v1v2link/1`):

```json
{"format": "umlmeta.v1v2link/1",
 "generated": "2026-10-31T12:00:00Z",
 "link_namespace": "https://github.com/mycr0ft/umlmeta/v1v2-link/stable-ids",
 "v2_graph_hash": "5842ea7d…",
 "records": [{"v1_kind": "Block", "v1_name": "Engine",
              "v1_path": "Vehicle::Engine", "v1_xmi_id": "_17_0_4_…",
              "v1_hash": "04ee7905…", "v1_key": "7c3d7b16…",
              "v2_kind": "PartDefinition", "v2_element_id": "v1v2:0a62e90f-…",
              "v2_hash": "9a1f…", "v2_key": "7c3d7b16…",
              "mapping": null}],
 "elisions": [ … ],
 "reader_gaps": {"unmapped": [], "unmapped_features": []}}
```

**v2 model** (`umlmeta.v2json/1`): `{"format", "@context", "@id", "@graph"}`
where every graph node is `{"@type": <metaclass>, "@id": <elementId>, …features}`
and references are `{"@id": …}`.

**Conflict record:** `{"kind", "element_id", "path", "v1_kind", "v2_kind"}`
with `kind` ∈ `both-changed` · `deleted-in-v1-edited-in-v2` ·
`blocked-by-edited-container`.

## Appendix B — API surface

| Module | Entry points |
|---|---|
| `umlmeta.v1_to_v2_as` | `transform_packages(pkgs, side_channel=)` · `transform_package(pkg)` · `transform_xmi_files(paths, side_channel=)` · `transform_xmi(path)` |
| `umlmeta.xmi21` | `read_xmi21(path)` · `read_xmi21_files(paths)` |
| `umlmeta.link` | `assign_element_ids(root, adopt=)` · `provenance(root)` · `graph_hash(root)` · `sidecar(root)` · `write_sidecar`/`read_sidecar` · `adopt_ids(root, {path: id})` · `signature` · `identity_key` |
| `umlmeta.sync` | `merge(v1_new, sidecar, existing)` → `MergeResult(root, conflicts, report)` · `diff_graph` · `diff_v1` |
| `umlmeta.v2_json` | `to_json` / `to_json_text` / `from_json` / `from_json_text` |
| `umlmeta.v2_text` | `emit_package` / `emit_model` |
| `umlmeta.v2_library` | `stub_package` · `resolve` · `unresolved` |
| `umlmeta.cli` | `umlmeta transform` · `link` · `diff` · `sync` |

## Appendix C — command cheat-sheet

```bash
# create the pair
umlmeta transform legacy.xmi -o model.v2.json --sidecar link.json --text model.sysml
# push a new v1 snapshot (always re-baseline)
umlmeta sync --v1 legacy.xmi --sidecar link.json --model model.v2.json \
             -o model.v2.json --sidecar-out link.json
# review
umlmeta diff model.prev.json model.v2.json
# rebuild a sidecar's identities/hash without losing its records
umlmeta link model.v2.json --sidecar link.json
# resolvable library references for a v2 tool
umlmeta transform legacy.xmi -o model.v2.json --library-stub
# keep the content the mapping cannot carry
umlmeta transform legacy.xmi -o model.v2.json --side-channel
```
