# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `umlmeta.v2_triage` — the validation gate's findings as a ledger (every
  violation and skip family with an owner: transform / engine / runtime /
  unattributed; 96 rows, 39 attributed on the vehicle model) plus a
  structure-consistency probe, which on the KerML AS reports
  `ownedElement` as derived-by-rule rather than union-tabled.
- `docs/v2-validation-triage.md` — the generated ledger.
- `check_v1v2_validation.py`: 14 checks (+3).

### Added

- OCL `invalid`: reading a feature the runtime does not carry now yields an
  undetermined value whose boolean use raises, and the evaluator records it as
  a skip. A constraint can no longer answer False because the generated
  runtime lacks an attribute (`_dot` used to return `None`).
- `check_v1v2_validation.py`: 11 checks (+2, the undetermined class).

### Added

- `umlmeta.v2_validate` — the semantic gate for a transformed SysML v2 model:
  runs the KerML/SysML constraint bodies over the AS with an extent bound,
  separating derivations from checks and reporting violations and skips
  separately. First run on the vehicle example: 131 elements, 1898 checks,
  284 violations, dominated by the missing library specialization edges
  (`check*Specialization`), which is the case for a resolved library (O6).
- `check_v1v2_validation.py` — 9 checks.

### Fixed

- `Extent.elements()` now walks `ownedRelationship`/`ownedRelatedElement`, so a
  freshly built SysML v2 model is reachable (it previously yielded the root
  alone — 1 element).
- The eval environment binds every `("local", ...)` lowering from the table;
  `input_parameters`/`output_parameters`/`integer_value` raised `NameError`
  when a v2 body used them.

### Added

- `umlmeta.extent` — the model scope OCL needs: composite-containment
  enumeration, metaclass filtering (module-first), qualified-name lookup and
  `specializesFromLibrary` over the model's own specialization graph.
  `eval_body(..., extent=...)` binds it for exactly one call.
- `selectByKind` / `selectAsKind` and `specializesFromLibrary` lower and
  evaluate; `T.allInstances()` answers from the extent instead of the
  empty-set stub. Corpus lowering: 676 -> 1001 of 1191 real bodies (sysml2
  170 -> 495).
- `check_ocl_extent.py` — 17 checks.

### Added

- `umlmeta.stereotype` — materializes stereotype applications as objects: the
  generated stereotype class is instantiated, its `base_<Metaclass>` end set
  to the stereotyped element, its tagged values applied with their declared
  types, and the instance attached to the element. `stereotype.check(model)`
  evaluates every applied stereotype's constraints with `self` bound to the
  instance (1113 evaluations over the 61 DoDAF applications).
- `check_stereotype.py` — 15 checks: profile index and resolution, a
  hand-written XMI application, the DoDAF corpus, and evaluation oracles that
  fail when they should.

### Fixed

- Profile modules: the generator consumed the `base_*` extension ends and
  emitted no `_props` at all, so `sysml.Block._props` was empty and every
  stereotype constraint navigating `base_Class` was untypable. The ends are
  now emitted as single-valued properties and `_finish()` builds the
  flattened `_props` map the uml25 contract expects (inherited first, own
  declarations win). 388 -> 144 unknown-feature diagnostics on the OCL
  corpus; 912 -> 1022 error-free bodies.

### Fixed

- OCL: an unqualified call inside an implicit-`it` iterator body now targets
  the element instead of `self`. 53 constraint bodies evaluated the wrong
  object (`incoming->exists(oclIsKindOf(Flow))` tested the owner, not the
  edges).
- OCL: a property with no stored carrier is read through `derived.py`
  (`owner`, `separator`, `mustBeOwned`, ...). `self.owner` returned `None`,
  `self.separator` returned a bound method, and `self.mustBeOwned` returned a
  method where a boolean belongs.

### Added

- `ocl_symbols.derived_only_props()` — the carrier-less derived-property
  table, computed from `derived.py` against the generated descriptors.
- `check_ocl.py`: five behaviour oracles for the derived route and the
  implicit receiver.

### Added

- `umlmeta.ocl_types` — the OCL type system over the generated runtimes: a
  type table built from the class descriptors (`_props`, `_UNIONS`, `_ENUMS`)
  and a static checker for OCL bodies. Diagnostics split into errors
  (unknown feature, unknown type) and the pending queue (derived-but-unwired,
  unsupported operation, implicit-`it` receiver).
- `check_ocl_types.py` — 29 checks: table construction, typing,
  diagnostics, a static-vs-runtime cross-check (every AttributeError the
  evaluator raised was predicted), and the corpus sweep (1166 bodies, 912
  error-free).

### Added

- `umlmeta.ocl_ast` / `ocl_parse` / `ocl_emit` — an OCL abstract syntax tree,
  a tokenizer and recursive-descent parser that produce it (with source spans),
  and two backends: Python lowering (what `translate()` uses) and OCL printing
  (every parsed body round-trips). Grammar added over the v0 translator:
  `Tuple{}`, `expr@pre`, `->iterate`, real literals, qualified names at any
  depth, qualified type arguments, `Set(T){}` literals, `--` line comments.
- `scripts/ocl_corpus.py` — measures the OCL corpus frozen in the generated
  modules (1215 bodies: 1166 parse, 676 lower, 24 no-spec placeholders),
  asserts the pinned counts with `--check`, exports JSON with `--out`.
- `check_ocl_ast.py` — 26 checks: corpus, differential against the v0
  emitter, value parity, print/parse round-trip, spans, refusals.

### Fixed

- The v0 OCL emitter produced wrong programs for 12 constraint bodies (free
  variable captured by the implicit-`it` rewrite, and `let` bindings whose
  references were left as self-property reads). The AST path resolves both
  correctly; the bodies are pinned in `check_ocl_ast.py`.

## [0.2.0] — 2026-10-28

The SysML v1 → v2 abstract-syntax transformer (R3 of the
transformation-conformance clause, OMG ptc/2025-04-07) grows from the
wave-A subset to waves A–H: the use-case, interface, port-definition,
import, association, multiplicity and InformationFlow mapping families
are now realized AS-side. First full corpus-suite run on local storage.

### Added

- `v1_to_v2_as` waves E–H (completing the wave-A/D structural core):
  - Wave E — UseCase → UseCaseDefinition with subject memberships
    (`subject_<name>` ReferenceUsages), Include → IncludeUseCaseUsage
    typed by the addition's definition per the normative mapping classes
    (pinned against the OMG machine-readable mapping XMI,
    SysMLv1Tov2.xmi), Extend/ExtensionPoint normatively unmapped;
    InterfaceBlock → PortDefinition (7.8.7.3.16) replacing the
    PartDefinition carrier; InterfaceBlock-typed Property →
    OccurrenceUsage (7.7.4.2.37).
  - Wave E add-on — use-case actors: association ends typed by the use
    case contribute ActorMembership members (PartUsages typed by the
    actor's definition), closing the ToActorMembership_Init elision.
  - Wave F — PackageImport → NamespaceImport and ElementImport →
    MembershipImport (7.7.9.3.12; visibility per
    Helper.getKerMLVisibilityKind; importedMembership = the AS
    OwningMembership of the imported element), and recursive namespace
    population (nested packages now transform).
  - Wave G — Association/AssociationClass → ConnectionDefinition
    (7.7.12.2.x) with memberEnd → isEnd ReferenceUsages via
    EndFeatureMembership; v1 multiplicity bounds → MultiplicityRange
    carrier (lowerBound/upperBound OwningMembership memberNames,
    LiteralInfinity for `*`) — the "no AS multiplicity carrier"
    elision is closed for properties, association ends and parameters.
  - Wave H — InformationFlow → FlowDefinition (first implementation of
    the family anywhere in the tree): normative filter (only flows
    realized by connectors/associations map), one FlowDefinition per
    realizing element, isEnd features typed by the mapped end elements,
    conveyed → carried ItemUsage, association realization →
    Subclassification to the realized ConnectionDefinition.
- `xmi21` reader: `packageImport`/`elementImport`/`InformationFlow`
  constructible, `importedElement`, the InformationFlow end/carrier
  refs, and 2.1-dialect enum text children (`aggregation`, `direction`)
  carried rather than recorded unmapped.
- `xmi_write` — Cameo/MagicDraw dialect output (UML 2.5.1 namespaces,
  `uml:Model` root, profile applications) behind keyword-only controls,
  plus the SysML v1 stereotype-base reader tables exercised by the
  synthetic VehicleExample round-trip (see docs/CAMEO_XMI.md).
- 551 checks across 19 suites (was 481/18); the AS transformer suite
  alone grew from 50 to 78 checks.

### Fixed

- Committed generator faults found while verifying regeneration
  idempotence: `generate.py` / `generate_sysml2.py` carried an
  IndentationError (stray indented write line) since the rename commit;
  `generate_bpmn.py` emitted an absolute pre-rename import causing a
  spurious diff on every regeneration; `generate_profiles.py` read the
  pre-rename `gen/` path and a non-existent `_sysml` attribute. All
  four generators now regenerate their modules byte-identically from
  the real OMG feeds.
- Corpus home restored to local storage: `/mnt/TBFox` (the tablet SD
  card, a never-committed manual mount) is now a symlink to
  `/storage16/home/jfox/TBFox`; every corpus suite (DoDAF, mdzip,
  query, xmi/cmof/emof write, derived) runs again — the whole 551-check
  sweep is green for the first time since the mount vanished.
  `scripts/tbfox_sync.sh` re-pulls if ever needed.

### Notes

- The transformation specification, whose Beta 4 anchors this release
  carries, has since gone formal (formal/2026-03-03, Part 2 of
  SysML v2.0); the next release will re-base the anchors and
  machine-readable mappings to the formal document.
- v0.1.0 never reached PyPI: its trusted-publisher upload failed and
  the one-time pending-project setup was never completed. 0.2.0 is the
  first published release.

## [0.1.0] — 2026-10-21

First release. Published to PyPI as `umlmeta`; the GitHub repository is
`mycr0ft/umlmeta` (renamed from `mycr0ft/uml2py`).

### Added

- The importable `umlmeta` package, installed from PyPI:
  - `umlmeta.uml25` — the UML 2.5.1 metamodel generated from the OMG-published
    UML XMI: 242 metaclasses, 620 reference descriptors, 22 derived unions
    computed at read time, 328 hidden association ends, 449 OCL constraints
    carried as metadata. Pure stdlib.
  - `umlmeta.sysml`, `umlmeta.standard_profile`, `umlmeta.uaf`,
    `umlmeta.uaf13` — the StandardProfile, SysML v1 and UAF 1.2 / 1.3
    profile stereotypes, with cross-profile folds.
  - `umlmeta.sysml2` — the SysML v2 abstract syntax (KerML + SysML) with the
    KerML ownership/membership wiring computed at runtime.
  - `umlmeta.bpmn` — the BPMN 2.0.2 CMOF metamodel.
  - `umlmeta.xmi21`, `umlmeta.xmi_write`, `umlmeta.mm_write` — XMI 2.1 / EMF
    and CMOF / EMOF readers and writers with canonical structural parity.
  - `umlmeta.mdzip`, `umlmeta.mdzip_import`, `umlmeta.mdzip_diff` — MagicDraw
    and Cameo `.mdzip` scraping, import and semantic diff.
  - `umlmeta.v1_to_v2`, `umlmeta.v1_to_v2_as` — the SysML v1 → v2 textual
    emitter and abstract-syntax transformer, anchored to OMG ptc/2025-04-07.
    Both follow the honesty rule: a construct with no normative mapping
    raises `UnmappedFeature` rather than guessing.
  - `umlmeta.derived`, `umlmeta.query`, `umlmeta.ocl_translator`,
    `umlmeta.canon`, `umlmeta.boxes_view` — normative derivations, query
    helpers, the clean-room OCL-to-Python translator, the canonical XML
    comparator, and the diagramboxes adapter.
- `pyproject.toml` (PEP 621, src layout) and a `check` GitHub Actions
  workflow covering Python 3.9, 3.12 and 3.13.
- Trusted-publishing PyPI workflow: a published GitHub release builds and
  uploads the distributions with no API token in the repository.

### Changed

- The project was renamed from `uml2py` to `umlmeta`. The PyPI name `uml2py`
  is taken by an unrelated PlantUML-to-Python converter; `umlmeta` is
  available and names what the project is. The GitHub repository was renamed
  to `mycr0ft/umlmeta`; the old URL redirects.
- The generated metamodel modules and the library modules moved from `gen/`
  and the repository root into a `src/umlmeta/` package. Imports inside the
  package are relative; the check suites import `umlmeta`. The generators
  write into `src/umlmeta/` and emit the new import forms.

### Notes

- The generated metamodel modules and the textual emitter are pure standard
  library. `lxml` is only needed by the XMI/CMOF/EMOF readers and writers
  and by the generators: `pip install "umlmeta[xmi]"`.
- 481 checks across 18 suites. Six suites (193 checks) run on the standard
  library alone and are what the CI workflow runs.

[0.1.0]: https://github.com/mycr0ft/umlmeta/releases/tag/v0.1.0
