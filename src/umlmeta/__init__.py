"""umlmeta — clean-room UML 2.5.1 / SysML v1 metamodel and the SysML v1 -> v2
transformation, generated from OMG-published documents.

The generated metamodel modules (:mod:`umlmeta.uml25`, :mod:`umlmeta.sysml`,
:mod:`umlmeta.sysml2`, :mod:`umlmeta.uaf`, :mod:`umlmeta.uaf13`,
:mod:`umlmeta.standard_profile`, :mod:`umlmeta.bpmn`) are pure stdlib and
self-contained.  The library modules around them (XMI/CMOF/EMOF readers and
writers, the textual and abstract-syntax v1->v2 transformers, normative
derivations, query helpers) are importable as ``umlmeta.<module>``.

Clean-room discipline: every semantic is traceable to an OMG document.
"""

__version__ = "0.1.0"

__all__ = [
    "bpmn",
    "boxes_view",
    "canon",
    "derived",
    "mdzip",
    "mdzip_diff",
    "mdzip_import",
    "mm_write",
    "ocl_translator",
    "query",
    "standard_profile",
    "sysml",
    "sysml2",
    "uaf",
    "uaf13",
    "uml25",
    "v1_to_v2",
    "v1_to_v2_as",
    "xmi21",
    "xmi_write",
]
