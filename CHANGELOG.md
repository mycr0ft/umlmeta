# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
