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
