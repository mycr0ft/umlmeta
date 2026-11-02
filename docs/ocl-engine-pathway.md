# OCL engine pathway — parsing and evaluating OCL over the generated runtimes

Status: assessment + plan (no code yet). Every number below was produced by a
command in this repo; the commands are listed so they can be re-run.

## 1. Where OCL already lives

The generated modules freeze the normative constraint bodies as OCL text:

| module | classes | OCL bodies | translate today | still unmapped |
|---|---:|---:|---:|---:|
| `uml25` (UML 2.5.1) | 259 | 449 | 384 | 41 + 24 no-spec |
| `sysml2` (KerML + SysML v2 AS) | 187 | 623 | 169 | 454 |
| `sysml` (SysML v1 profile) | 61 | 143 | 80 | 63 |
| `uaf` / `uaf13` | 277 / 294 | 259 / 269 | 0 | English prose, not OCL |
| **total OCL** | | **1215** | **633 (52%)** | |

Re-measure:

```python
# bodies: for each class, cls.__dict__["CONSTRAINTS"] (own only)
from umlmeta import ocl_translator as T
tr, un = T.translate_all(bodies)
```

`uaf`/`uaf13` constraints are English requirements ("Value for the client
metaproperty must be stereotyped by …"), 258/259 of them carrying `«»`; they
are not an OCL surface. `standard_profile` and `bpmn` carry no constraints.

Three modules already do part of the job:

- **`ocl_translator.py`** (1324 lines) — a real hand-written tokenizer and a
  recursive-descent parser (precedence per OCL 2.4 §7.5.3, `let` scoping,
  comprehension variables, `if/then/else/endif`) that **emits Python source
  strings** which are then `eval()`-ed against the generated objects.
- **`derived.py`** (479 lines, 34 functions) — clean-room Python for the
  tractable UML derivations (`union`, `qualified_name`, `owner`, `parents`,
  `inherit`, `must_be_owned`, `lower_bound`, …). This is where "OCL that is
  worth evaluating" currently gets implemented by hand.
- **`query.py`** — `walk`/`find`/`exists` over instance graphs; the natural
  `allInstances()`/scope substrate.

So the premise "we would need a parser" is already half-built: there is a v0
translator that speaks the generated hierarchy. What does not exist is an
**AST**, a **type system**, an **operation library**, and an **extent**.

## 2. What the v0 translator is, and why it is not the platform

Measured limits (probed, not assumed):

- It emits Python source, so there is nothing to type-check, nothing to
  attach a source span to, and no place to implement OCL's `invalid`
  (it maps `invalid` to `None`; `x = invalid` becomes `x is None`).
- Navigation is untyped and positional: `a.b` becomes `_dot(a,'b')` with
  implicit collect, and `->at(1)` becomes `_nav(x)[1-1]` — the single-vs-
  collection distinction is decided at run time by `isinstance(v,(list,tuple))`,
  which cannot distinguish a multi-valued navigable end from a single one that
  happens to hold a list, and cannot report "no such feature" as a typing
  error.
- Operations are a closed whitelist inside the parser (`->select`,
  `->forAll`, …); anything else raises `UnmappedFeature('operation X(...)')`.
- `T.allInstances()` returns `[]` by design ("extent unknown outside a
  resource"), and `@pre` is a hard tokenizer error.
- Evaluation environment is `eval(src, globals)`, so comprehension variables
  have to ride in globals; debugging a failing body means reading generated
  Python.

Coverage, measured over the 633 translatable bodies and the suite's sample
model: `check_ocl.py` reports 117 bodies actually evaluated. Most of the
remainder translate but raise on navigation into ends the generated runtime
does not carry (`eval-unmapped: <attr>`), which is the "wave-2" bucket.

## 3. Gap inventory (classified)

### (a) Grammar gaps — parser work

Measured over the 1215 bodies (`uml25` + `sysml2` + `sysml`):

| construct | bodies using it | v0 status |
|---|---:|---|
| `->closure(x \| …)` | 24 | unmapped |
| `->iterate(x; acc : T = v \| …)` | 2 | unmapped |
| `oclAsType(T)` | 150 | mapped, but a kind mismatch returns `None` (invalid ≡ null) |
| `selectByKind` / `selectAsKind` / `oclIsType` | 196 / 3 / 3 | unmapped |
| `specializesFromLibrary('…')` | 165 | unmapped |
| String ops (`concat`, …) | 1 | unmapped |
| `Tuple{…}`, `@pre`, `->isUnique`, `->sortedBy`, `->collectNested` | 0 | absent from the corpus — needed only for user-authored OCL |
| `Set{}` / `OrderedSet{}` / `Sequence{}` / `Bag{}` literals | 17 | mapped (element typing is unchecked) |

So the generated corpus exercises a narrower grammar than "full OCL"; the
missing pieces that matter *now* are `closure`, `iterate`, `selectByKind` and
`specializesFromLibrary`. `Tuple`, `@pre` and the ordering ops are
future-proofing for user OCL, not coverage debt.

### (b) KerML OCL extensions — the biggest single lever

`sysml2` bodies lean on two operations that don't exist in the v0 whitelist:

- `selectByKind(X)` / `selectAsKind(X)` / `oclIsType(T)` — 196 + 3 + 3 bodies.
  These need only the metaclass registry: `umlmeta.sysml2.metaclass(name)`
  already exists, so `selectByKind` is `isinstance` filtering.
- `specializesFromLibrary('Base::Anything')`, `redefinesFromLibrary`,
  `libraryNamespace` — 165 bodies. These need a **library index**:
  the library elements the string names are resolved against
  (`Base::Anything`, `Performances::…`, `Requirements::…`). `v2_library.py`
  already builds a name-only stub package for the transform's carries; the
  evaluator needs the reverse direction — resolve a qualified name to a real
  object (or to a stub that satisfies `specializes`).

### (c) Helper operations — bodies are NOT machine-readable

The metamodel's own operations (e.g. `RedefinableElement::isConsistentWith`,
`Namespace::membersAreDistinguishable`, `Action::sourceNodes`,
`Type::output`, `Class::maySpecializeType`) are the second blocker:

- UML.xmi (OMG, `~/Downloads/UML.xmi`) carries 205 operations and **0
  `bodyCondition` elements** — the operation bodies are only in the spec PDF.
- The generated modules keep operation *signatures* as docstring metadata
  only ("[Element operation (query); params: none; returns: bool; …]"), so
  even a signature table has to be produced by a generator change.
- 22 distinct helper operations block 41 `uml25` bodies; ~30 more block
  `sysml2` bodies (`inputParameter`, `argument`, `directionOf`, `redefines`,
  `isSubactionUsage`, …).

This is `derived.py`'s job today, and deliberately so: implementing them means
transcribing normative OCL from the formal text (clean-room, quoted per
clause) and pinning it with oracles — the same discipline as the mapping
waves. Machine-readable source does not exist for these.

### (d) Type system — required, not optional

A real OCL evaluator needs, per metaclass: property type, multiplicity
(collection vs single), derived/union status, subsetting/redefinition. All of
it exists in the generated descriptors (`_props[name].type_name`,
`.upper`, `.derived`, `.subsets`, `.redefines`, `_UNIONS`, `_OPPOSITES`), plus
`_STEREO` for stereotypes. So the type table can be **derived from the
runtime**, not hand-written — which is exactly why the engine should speak the
class hierarchy rather than a separate metamodel object model.

### (e) Extent / scope

`allInstances()`, `->allInstances()` and `specializesFromLibrary` need a
resource: a root object (or a set of roots) plus a containment walk. The
runtime has `walk` (query.py), `_owner` chains and composite descriptors, so an
`Extent` is a thin object — but it must be passed explicitly (the v0 global
function cannot see a model).

### (f) Semantics

`invalid` / `null` distinction (three-valued logic), `OclVoid`/`OclAny`
conformance, `oclAsType` failure vs `invalid`, ordered-set vs bag result types
(`select` preserves collection kind; `collect` flattens; `asSet` dedupes).
The v0 collapses all of this; a plan that keeps collecting bodies without
fixing it accumulates subtly wrong answers.

## 4. Proposed waves (O-series)

Each wave: oracles first (RED), then implementation, then REPORT part;
`check_ocl.py` stays the gate and grows per wave. Baseline to freeze: 633
translated / 117 evaluated, and the exact `translate()` output for every body
(so a source-level change is visible as a diff, not a mystery).

- **O0 — corpus + oracle freeze.** Emit the 1215 bodies to a JSON corpus in the
  repo (`scripts/export_ocl_corpus.py` → `ocl_corpus.json` with class, name,
  body, module) so coverage is measurable without importing 8 modules; pin the
  current pass/skip sets. *Exit:* coverage table reproducible in one command.
- **O1 — AST + parser.** `ocl_ast.py` (nodes with `span`) + `ocl_parse.py`
  (tokenizer moved out, parser returns nodes). Keep `translate()` as a shim
  emitting Python from the AST so `check_ocl.py` stays green. *Exit:* all 633
  bodies parse; AST round-trips; `Tuple{}`, `@pre` parse.
- **O2 — type system.** `ocl_types.py`: build the type table from the
  generated descriptors; static-check each body (navigation vs feature,
  arithmetic operand types, collection element types). *Exit:* every
  translatable body type-checks; untypable ones are itemized by reason.
- **O3 — interpreter + collection library.** `ocl_eval.py` over the AST with
  proper collection kinds and `invalid`; `ocl_ops.py` for the collection,
  String/Integer ops, `Tuple`, literals, `->iterate`/`->closure`/`->isUnique`/
  `->sortedBy`. *Exit:* value-parity against the source-emitting path on every
  body that both can run; the parser whitelist is gone.
- **O4 — helper-operation library.** The 22 UML (+~30 SysML) operations,
  transcribed from the formal text with anchors, replacing their `derived.py`
  counterparts one at a time (derived stays as the fast path). *Exit:* the 41
  `uml25` unmapped bodies drop to the 24 no-spec ones.
- **O5 — extent and library resolution.** `Extent` (roots → `allInstances`),
  qualified-name lookup, `selectByKind`, `specializesFromLibrary` against a
  library model or its stub. *Exit:* `sysml2` translation/evaluation coverage
  moves off the 27% floor; the AS the v1→v2 transformer emits validates.
- **O6 — v2 validation leg.** Run the engine as a conformance gate on
  transformed models (`check_v1_to_v2_as.py` already builds them) and report
  violations. *Exit:* a v2 model failing a normative KerML constraint is a
  failing check, not a silent pass.

Ordering rationale: O1/O2 unblock everything and are pure-repo work; O3/O4 are
where the 41 UML bodies close; O5 is the only wave that needs an external
artifact (a library model) and therefore the one to schedule last.

## 5. Decisions to pin

| # | Decision | Why |
|---|---|---|
| O-d1 | AST interpreter, with `translate()` kept as a compatibility shim for one release | the source-emitting path is good enough to be an oracle for the new one, then it should die |
| O-d2 | Type table derived from the generated `_props` descriptors | the hierarchy is the single source of truth; a second hand-kept table would drift |
| O-d3 | `invalid` ≠ `null`; three-valued logic from the start (O2) | retrofitting `invalid` after 600 bodies are green means re-baselining everything |
| O-d4 | Helper-operation bodies are transcribed from the formal text, one anchor per operation | UML.xmi carries none (measured); guessing them is the honesty-gate violation |
| O-d5 | Extent passed explicitly (never a process-global) | two models in one process is the normal case here (v1 + v2 pair) |
| O-d6 | Evaluation never mutates the model | constraints are checks; mutations belong to a transform |

## 6. What this unlocks (why it is worth the waves)

1. **Validate any loaded model** — Cameo XMI instances, DoDAF/UAF libraries,
   the vehicle example — against the 449 UML bodies, with spans and reasons.
2. **Validate the v1→v2 output** against the 623 KerML/SysML bodies: the
   transformer currently has no semantic gate at all, only shape oracles.
3. **Replace hand-coded derivations** where the spec already has OCL
   (`derived.py` becomes a cache, not a second specification).
4. **Evaluate user OCL** carried in models (`Constraint.specification` bodies
   read by `xmi21.py`), which is what a v1→v2 "constraint carries" mapping
   would need before it can even be attempted.
