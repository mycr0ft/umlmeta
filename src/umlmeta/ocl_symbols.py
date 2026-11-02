"""ocl_symbols.py — the OCL operation tables shared by the parser and emitter.

Pure data, standard library only. These were inline in `ocl_translator.py`
while the parser emitted Python source directly; the AST parser and the
emitter both need them, so they live here (the translator re-exports them
for compatibility).

Three namespaces matter:

- `COLLECTION_OPS` — operations that take the receiver as a collection
  (`->select`, `.size()`): OCL treats a single-valued property as a
  one-element collection, so the emitter wraps the receiver in `_nav`.
- `CLASSIFY_OPS` — the type-test family; their argument is a *type name*,
  not an expression.
- `DERIVED_FUNCS` — operations the repo implements itself, either through
  `derived.py` ("derived", looked up with `_d('fn', self)`) or as local
  helpers in `ocl_translator` ("local", emitted as a bare call). The
  second element is always the emitted Python callable name.
"""

COLLECTION_OPS = {
    "size", "isEmpty", "notEmpty", "includes", "excludes", "includesAll",
    "excludesAll", "exists", "forAll", "select", "reject", "one", "any",
    "asSet", "asSequence", "asOrderedSet", "asBag", "collect", "union",
    "intersection", "flatten", "first", "last", "at", "indexOf", "excluding",
    "closure",
}

CLASSIFY_OPS = {"oclIsKindOf", "oclIsTypeOf", "oclAsType", "oclIsUndefined",
                "oclType"}

# OCL extension operations the AST understands but the emitter has no
# Python lowering for yet (O3): they parse, and evaluation raises.
PENDING_OPS = {"collectNested", "isUnique", "sortedBy", "iterate"}

DERIVED_FUNCS = {
    "allNamespaces": ("derived", "all_namespaces"),
    "allOwnedElements": ("derived", "all_owned_elements"),
    "allParents": ("derived", "all_parents"),
    "parents": ("derived", "parents"),
    "conformsTo": ("derived", "conforms_to"),
    "qualifiedName": ("derived", "qualified_name"),
    "separator": ("derived", "separator"),
    "allFeatures": ("derived", "all_features"),
    "allAttributes": ("derived", "all_attributes"),
    "inheritedMember": ("derived", "inherited_member"),
    "member": ("derived", "member"),
    "visibleMembers": ("derived", "visible_members"),
    "importedMember": ("derived", "imported_member"),
    "getNamesOfMember": ("derived", "get_names_of_member"),
    "lowerBound": ("derived", "lower_bound"),
    "upperBound": ("derived", "upper_bound"),
    "subsettingContext": ("derived", "subsetting_context"),
    "opposite": ("derived", "opposite"),
    "isComposite": ("derived", "is_composite"),
    "isDistinguishableFrom": ("derived", "is_distinguishable_from"),
    "mustBeOwned": ("local", "must_be_owned"),
    "isMultivalued": ("local", "is_multivalued"),
    "isNavigable": ("local", "is_navigable"),
    "isAttribute": ("local", "is_attribute"),
    "containingActivity": ("local", "containing_activity"),
    "containingStateMachine": ("local", "containing_state_machine"),
    "containingBehavior": ("local", "containing_behavior"),
    "endType": ("local", "end_type"),
    "allActions": ("local", "all_actions"),
    "allPins": ("local", "all_pins"),
    "allOwnedNodes": ("local", "all_owned_nodes"),
    "allIncludedUseCases": ("local", "all_included_use_cases"),
    "allRoles": ("local", "all_roles"),
    "allSlottableFeatures": ("local", "all_slottable_features"),
    "allInstances": ("local", "all_instances"),
    "is": ("local", "is_mult"),
    "association": ("local", "association"),
    "inputParameters": ("local", "input_parameters"),
    "outputParameters": ("local", "output_parameters"),
    "integerValue": ("local", "integer_value"),
    "unlimitedValue": ("local", "unlimited_value"),
    "compatibleWith": ("local", "ocl_compatible_with"),
    "incoming": ("local", "vertex_incoming"),
    "outgoing": ("local", "vertex_outgoing"),
    # derived.py implementations that were never wired: a body using one
    # lowered to an attribute read on an element that has no such attribute
    "owner": ("derived", "owner"),
    "inherit": ("derived", "inherit"),
    "inheritableMembers": ("derived", "inheritable_members"),
    "importMembers": ("derived", "import_members"),
    "hasVisibilityOf": ("derived", "has_visibility_of"),
    "makesVisible": ("derived", "makes_visible"),
    "excludeCollisions": ("derived", "exclude_collisions"),
}

# bare (receiver-less) names that are computed, not stored: emitted as a
# call on self rather than a property read
LOCAL_BARE = {"incoming": "vertex_incoming", "outgoing": "vertex_outgoing"}

# operations whose argument list is an iterator expression
LAMBDA_OPS = {"exists", "forAll", "select", "reject", "one", "any", "collect"}

# collection kinds accepted as literal prefixes
COLLECTION_TYPES = ("Sequence", "Set", "OrderedSet", "Bag", "Collection")

CONSTANTS = {"true": "True", "false": "False",
             "null": "None", "invalid": "None",
             "OclInvalid": "None", "oclInvalid": "None"}


# --------------------------------------------------------------------------
# derived-only properties
# --------------------------------------------------------------------------
#
# Some OCL properties have no stored carrier in the generated runtimes: the
# generator drops derived ends it cannot compute, and `derived.py` implements
# them as functions. A bare read (`self.owner`) must lower to the function
# call, not to `getattr`, or the evaluator hits an attribute that does not
# exist. The set is computed, not hand-listed: every `derived.py` function
# whose camelCase name is a property of NO generated class.

_DENY = {"union", "union_contributors", "union_names", "subsetting_context",
         "parents", "inherit", "inheritable_members"}


def camel(snake):
    """snake_case -> the OCL camelCase name."""
    head, *rest = snake.split("_")
    return head + "".join(w[:1].upper() + w[1:] for w in rest)


_DERIVED_ONLY = None


def derived_only_props():
    """{ocl name: derived.py function name} for carrier-less derived props."""
    global _DERIVED_ONLY
    if _DERIVED_ONLY is not None:
        return _DERIVED_ONLY
    import importlib
    import inspect

    from . import derived

    stored = set()
    for modname in ("uml25", "sysml2", "sysml"):
        mod = importlib.import_module("umlmeta." + modname)
        classes = getattr(mod, "_CLASSES", None) or [
            v for v in vars(mod).values() if isinstance(v, type)]
        for cls in classes:
            stored.update(getattr(cls, "_props", {}) or {})
    out = {}
    for fname, fn in inspect.getmembers(derived, inspect.isfunction):
        if fname.startswith("_") or fname in _DENY:
            continue
        ocl = camel(fname)
        if ocl and ocl not in stored:
            out[ocl] = fname
    _DERIVED_ONLY = out
    return out
