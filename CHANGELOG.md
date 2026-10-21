# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
