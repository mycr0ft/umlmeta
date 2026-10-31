# Maintaining a v1 ↔ v2 link through a prolonged transition

**Status:** pathway published; M1 (identity + provenance) shipped · umlmeta 0.2.x · Jon R. Fox

The SysML v1 → v2 transformation clause (SysML v2.0 Part 2, formal/26-03-03)
defines a **one-shot** mapping: read a v1 model, emit a v2 model. umlmeta's
R3 leg implements that and is conformance-green (194 AS oracles, 51 textual).
What it does *not* provide is anything a project needs to run the two models
side by side for a year: stable identity, persistence, change detection,
or a record of what did not cross.

This document is the pathway for that layer. It exists because "transform
once" and "keep a link" are different problems, and the second one fails
silently if identity is left to serialization artifacts.

---

## 1. What exists today (measured, not remembered)

| Capability | State |
|---|---|
| v1 → v2 abstract syntax (R3) | implemented, 194 oracles green |
| v1 → v2 textual notation | implemented, 51 oracles green (lags the AS: no probability/rate, variable actions, Reply/Unmarshall, TerminateActionUsage, imports) |
| v1 XMI reader (R1) | structural + activity internals + interactions + guards/effects/weight |
| v1 XMI writer | implemented (`xmi_write.py`, canonical parity gate) |
| **v2 serialization** | **absent** — the only AS→text renderer is `render_as()` inside `check_v1_to_v2_as.py` |
| v2 `elementId` | **M1** — deterministic `v1v2:` uuid5 ids over the declared path + type (`umlmeta.link`) |
| v1→v2 provenance | **M1** — `umlmeta.link.provenance()` over the transform's retained index (`_v1_index`/`_v1_root`), with the v1 xmi id as a cache and a v1 content signature |
| reverse (v2 → v1) | absent |
| pair diff / merge / sync | absent (`mdzip_diff` covers v1 snapshots only) |
| elision ledger | prose (module docstring, realization table, REPORT) — no per-model record |
| CLI | absent (`pyproject.toml` has no `[project.scripts]`) |

Consequence: a linked pair cannot be saved, re-loaded, diffed, or handed to a
v2 tool, and any v2-side edit is destroyed by the next full re-transform.

---

## 2. Link levels

The vocabulary is adopted from sysmlpy's `docs/stable-identities.md`, which
defines L0–L3 for idempotent interchange. The link needs the same levels plus
one that only a pair can have.

| Level | Guarantee |
|---|---|
| **L0** | transform(v1) → v2 is deterministic: same snapshot, same graph |
| **L1** | same snapshot re-transformed → identical element identities |
| **L2** | edits elsewhere in the v1 model leave untouched elements' v2 identities unchanged |
| **L3** | one element keeps one identity across renames, moves and independent files (explicit id or sidecar adoption) |
| **L4** | the pair is *maintainable*: each side's edits are attributable, mergeable or explicitly refused, and the refusals are recorded |

L0 and L1 are tests away. L2 needs content-addressed ids. L3 needs adoption
from a prior export. L4 needs a sync engine and an elision ledger — that is
the real deliverable of this pathway.

---

## 3. Identity scheme (leverages sysmlpy)

sysmlpy ships the scheme we want (`src/sysmlpy/interchange.py`):

- **key**: the declared qualified-name path of the element joined with `|`,
  plus the element `@type`; same-name sibling groups take an occurrence
  index appended as `|#<n>`;
- **id**: `uuid5(STABLE_NAMESPACE, key)`, prefixed `sysml:`;
- **anonymous elements** hash the nearest declared ancestor path plus the
  structural path from that ancestor;
- **explicit ids** carried in the source (`doc /* @id: … */`) override
  derivation; two elements claiming one id raise;
- **`--reconcile-with <previous export>`** adopts ids from the previous
  document by name path, giving L3 ("re-export with
  `--reconcile-with model.json -o model.json` to keep ids stable across the
  model's lifetime");
- `stable_ids(model)` mirrors the exporter key-for-key, so the object model
  and the interchange document agree by construction.

umlmeta adopts the same recipe with its own namespace and prefix, so the two
schemes are mechanically reconcilable:

```
LINK_NAMESPACE = uuid5(NAMESPACE_URL,
    "https://github.com/mycr0ft/umlmeta/v1v2-link/stable-ids")
elementId      = "v1v2:" + uuid5(LINK_NAMESPACE, key)
```

Why the same recipe rather than a shared namespace: the key spaces differ
(umlmeta keys on the *mapped* v2 element's declared path, sysmlpy keys on its
own parse tree), and identity must be stable for the mapping's lifetime, not
the tool's release. Agreement in *behaviour* (L2/L3 edit classes) is the
contract; agreement in *value* is achieved by adoption (§6, M4) when the v2
model is round-tripped through sysmlpy.

**Deliberately not keyed on `xmi:id`.** `docs/semantic-content-hash.md`
records Cameo delta-snapshots and TeamworkCloud check-ins re-minting ids
(47 id eras inside one corpus file). The xmi id is stored in the provenance
record as a *cache for one snapshot*, never as identity.

---

## 4. Provenance record and sidecar

One JSON sidecar per transformed model (`<name>.v1v2link.json`):

```json
{
  "format": "umlmeta.v1v2link/1",
  "generated": "2026-10-31T12:00:00Z",
  "link_namespace": "https://github.com/mycr0ft/umlmeta/v1v2-link/stable-ids",
  "v2_graph_hash": "sha256:…",
  "records": [
    {
      "v1_kind": "Block",
      "v1_path": "Vehicle::Engine",
      "v1_xmi_id": "_17_0_4_…",
      "v1_hash": "9f31c2…",
      "v2_kind": "PartDefinition",
      "v2_element_id": "v1v2:…",
      "mapping": "Block_Mapping"
    }
  ],
  "elisions": [
    {"v1_kind": "Continuation", "v1_path": "Seq::CX", "rule": "Table 11: not mapped"}
  ]
}
```

Records are per mapped element; `elisions` is the per-model ledger of v1
content that produced no v2 counterpart (or only a name-only carrier).
`v1_hash` covers the element's scalar features and is the repair key when a
path changes (M3): a renamed element re-links by hash, not by name.

---

## 5. Milestones

Each milestone lands as its own wave (TDD, full sweep green, REPORT part).

### M1 — identity and provenance *(shipped)*
- `umlmeta.link`: `assign_element_ids()`, `provenance()`, `graph_hash()`,
  the namespace/prefix above, and adoption (`adopt=True`) for L3 hand-off.
- `transform_package` retains its identity index on the returned package so
  linkage reads it instead of re-deriving.
- **Acceptance:** every AS element has a unique `elementId`; two transforms
  of one snapshot agree (L1); a sibling inserted before an element elsewhere
  leaves its id unchanged (L2); same-name siblings stay distinct; the graph
  hash is stable under re-transform and changes on content change;
  provenance carries `v1_kind`/`v1_path`/`v1_xmi_id`/`v1_hash`.
- **Exit test:** shipped in `check_v1_to_v2_as.py` (M1 link section, 15
  checks, including the XMI leg so v1 xmi ids are carried end to end).
- **Note:** the sidecar document (§4) is emitted by M3 — M1 ships the
  identity, the provenance record set and the graph hash it will carry.

### M2 — persistence of the v2 side
- Promote an AS → SysML v2 **textual** emitter into the package (the oracle
  renderer is the starting point), with a round-trip oracle: emit → sysmlpy
  parse → re-transform comparison.
- Then an AS → SysML v2 **JSON interchange** writer matching sysmlpy's
  document shape, so the v2 model can be handed to other tools.
- **Acceptance:** write → read → write is a fixed point (L0/L1 on the v2
  side); the writer is the single source of truth (the direct v1→text
  pipeline stays as a notation oracle, not a competing output).

### M3 — diff, sync, incremental transform
- Pair diff using `mdzip_diff`-style records on both sides; classify each
  change: v1-only (re-mappable), v2-only (v2-native edit), both (conflict),
  unmappable (elided).
- Incremental re-transform: re-map changed v1 subtrees onto existing v2
  elements by `elementId`; untouched v2 elements are preserved verbatim.
- Three-way merge with explicit conflict objects; a refused merge is a
  recorded outcome, never a silent overwrite.
- **Acceptance:** edit v1 → sync preserves v2-only edits; edit v2 → v1 side
  unchanged; simultaneous edits produce exactly one conflict record per
  element; re-running a clean sync is a no-op (fixed point).

### M4 — elision ledger and side-channel policy
- Emit `elisions` per model (reader `unmapped`/`unmapped_features` +
  transformer skips), keyed by v1 path.
- Policy for the permanently unmapped set (Table-11 occurrences, Gates,
  Continuations, Extend/ExtensionPoint, ActorMembership, UseCaseObjective,
  EventOccurrence, ConjugatedPortTyping): skip-with-record by default, plus
  an opt-in side-channel carrier (a v2 metadata usage annotated with the v1
  path and hash) so the content survives in the linked model.
- Adoption of sysmlpy ids (§3) when the v2 model is round-tripped through
  sysmlpy: `reconcile_with` semantics applied to the link sidecar.
- **Acceptance:** a model containing one member of every permanently-unmapped
  family transforms with zero silent losses — every skipped element appears
  in `elisions`.

### M5 — scope and library resolvability
- Cross-file v1 load scope (today a property typed outside the transformed
  tree raises "external/unordered"); a project's v1 model is rarely one file.
- A SysMLv1Library stub package so name-only references resolve in the v2
  model (probability/rate, ActivityEdgeData, PortData/RefineData/TraceData,
  allocation sources, variable-action library types) — a v2 tool must be
  able to load the result.
- CLI (`umlmeta transform|link|diff|sync`) so the loop is scriptable.

---

## 6. Decisions and open questions

| # | Decision | Rationale |
|---|---|---|
| D1 | identity = uuid5 over declared path + type, not xmi:id | xmi ids churn on every tool save (semantic-content-hash §1) |
| D2 | v2 `elementId` is the link key; the sidecar is the pair record | elementId is the only identity a v2 tool will preserve on load/save |
| D3 | elisions recorded per model, not per spec paragraph | a live link must answer "did *this* change cross?" |
| D4 | AS is the conformance artifact; text is a notation | the direct v1→text pipeline cannot carry provenance |
| Q1 | does an v2-native edit to a *derived* element get pushed back to v1, or frozen? | needs a project policy field in the sidecar (M3) |
| Q2 | do we adopt sysmlpy ids verbatim when it exports our model? | M4; the key spaces agree in behaviour but not value |
| Q3 | side-channel carrier shape for unmapped content (metadata usage vs documentation) | M4; ActivityEdgeData's metadata machinery is the working precedent |

---

## 7. Non-goals

- Byte-parity round-trip of v1 XMI through the pair (structural parity is the gate).
- A general v2 → v1 reverse transformation (the mapping is not invertible;
  elisions guarantee it).
- Automatic resolution of semantic conflicts (conflicts are surfaced and
  recorded; a human decides).
- Tool-specific dialects beyond UML 2.x/2.5.1 XMI and the SysML v1 profile.

---

## 8. References

- OMG SysML v2.0 Part 2: SysML v1 to SysML v2 Transformation, formal/26-03-03
  (`~/umlmeta/SysMLv1Tov2.xmi` — normative machine-readable).
- `REPORT.md` Parts 27–51 — mapping waves, elisions, realization table.
- `docs/semantic-content-hash.md` — why identity cannot key on serialization ids.
- sysmlpy `docs/stable-identities.md` — L0–L3, the uuid5 recipe, explicit ids,
  `reconcile_with`; `src/sysmlpy/interchange.py` (`STABLE_NAMESPACE`,
  `_StableIdAssigner`, `stable_ids`, `qn_registry`).
