#!/usr/bin/env python
"""D1 checks: dialect acceptance in the XMI reader.

Oracles (each a document we must read, or must refuse, with a reason):
  1. OMG-published wrapper form: <xmi:XMI> document element holding a
     <uml:Package> root, XMI 2.1 schema.omg URI                     -> reads
  2. same, XMI 2.5 omg.org 20131001 URI                             -> reads
  3. Eclipse UML2 5.0.0: the UML root IS the document element
     (`<uml:Package .../>`), no xmi:type on it                      -> reads
  4. Eclipse UML2 4.0.0 with the 20110701 XMI attribute URI on the
     document element (xmi:id/xmi:version only there)               -> reads
  5. <uml:Profile> as document element                             -> reads
  6. feature-named child with no xmi:type (`<elementImport>`)      -> reads
  7. XMI 1.x document model (`<XMI><XMI.content>`)                 -> REFUSED
  8. non-model XML (`<Diagram>`)                                   -> REFUSED
  9. an empty but valid UML document is an EMPTY MODEL, not an error.

The refusal path matters as much as the acceptance path: a reader that
returns an empty model for input it cannot read turns every downstream
check into a vacuous pass.

Standard library only. Run: .venv/bin/python check_xmi_dialects.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from umlmeta import xmi21  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def read(text):
    with tempfile.NamedTemporaryFile("w", suffix=".xmi", delete=False) as fh:
        fh.write(text)
        path = fh.name
    try:
        return xmi21.read_xmi21(path)
    finally:
        Path(path).unlink(missing_ok=True)


OMG_2_1 = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
         xmlns:uml="http://www.omg.org/spec/UML/20090901">
  <uml:Package xmi:id="p1" xmi:type="uml:Package" name="P">
    <packagedElement xmi:id="c1" xmi:type="uml:Class" name="C"/>
  </uml:Package>
</xmi:XMI>
"""

OMG_20131001 = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmlns:xmi="http://www.omg.org/spec/XMI/20131001"
         xmlns:uml="http://www.omg.org/spec/UML/20131001">
  <uml:Model xmi:id="m1" name="M">
    <packagedElement xmi:id="p1" xmi:type="uml:Package" name="P"/>
  </uml:Model>
</xmi:XMI>
"""

# Eclipse UML2 5.0.0: root is the document element, children unprefixed
ECLIPSE_5 = """<?xml version="1.0" encoding="UTF-8"?>
<uml:Package xmi:version="20131001" xmlns:xmi="http://www.omg.org/spec/XMI/20131001"
            xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML" xmi:id="_pkg" name="domain">
  <packagedElement xmi:type="uml:Class" xmi:id="_c1" name="A"/>
  <packagedElement xmi:type="uml:Class" xmi:id="_c2" name="B"/>
</uml:Package>
"""

# Eclipse UML2 4.0.0: the XMI attributes live in the 20110701 URI
ECLIPSE_4 = """<?xml version="1.0" encoding="UTF-8"?>
<uml:Model xmlns:uml="http://www.eclipse.org/uml2/4.0.0/UML"
           xmlns:xmi="http://www.omg.org/spec/XMI/20110701"
           xmi:id="_m1" xmi:version="20110701" name="M">
  <packagedElement xmi:type="uml:Package" xmi:id="_p1" name="P">
    <packagedElement xmi:type="uml:Class" xmi:id="_c1" name="C"/>
  </packagedElement>
</uml:Model>
"""

ECLIPSE_PROFILE = """<?xml version="1.0" encoding="UTF-8"?>
<uml:Profile xmi:version="20131001" xmlns:xmi="http://www.omg.org/spec/XMI/20131001"
             xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML" xmi:id="_prof" name="SysML">
  <elementImport xmi:id="_ei1" importedPackage="_x"/>
  <packagedElement xmi:type="uml:Stereotype" xmi:id="_st1" name="Block"/>
</uml:Profile>
"""

EMPTY_OK = """<?xml version="1.0" encoding="UTF-8"?>
<uml:Package xmi:version="20131001" xmlns:xmi="http://www.omg.org/spec/XMI/20131001"
            xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML" xmi:id="_empty"/>
"""

XMI_1X = """<?xml version="1.0" encoding="UTF-8"?>
<XMI xmi.version="1.2" xmlns:UML="org.omg.UML2_1">
  <XMI.header><XMI.documentation><XMI.exporter>ArgoUML</XMI.exporter></XMI.documentation></XMI.header>
  <XMI.content><UML:Package xmi.id="_1" name="P"/></XMI.content>
</XMI>
"""

DIAGRAM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Diagram><ID>JAVA</ID><OriginalElement/><nodes/><notes/><edges/></Diagram>
"""

print("== accepted dialects ==")
m = read(OMG_2_1)
check("OMG wrapper, XMI 2.1 schema URI constructs a root and a child",
      len(m.objects) == 2 and len(m.roots) == 1, f"{len(m.objects)} objects")

m = read(OMG_20131001)
check("OMG wrapper, XMI 2.5 20131001 URI constructs a root and a child",
      len(m.objects) == 2 and len(m.roots) == 1, f"{len(m.objects)} objects")

m = read(ECLIPSE_5)
check("Eclipse UML2 5.0.0 document-element root is read",
      len(m.objects) == 3 and len(m.roots) == 1, f"{len(m.objects)} objects")

m = read(ECLIPSE_4)
check("Eclipse UML2 4.0.0 with the 20110701 XMI attribute URI is read",
      len(m.objects) == 3, f"{len(m.objects)} objects, ids found via 20110701")

m = read(ECLIPSE_PROFILE)
check("an Eclipse <uml:Profile> document element is read",
      len(m.objects) >= 2 and any(type(o).__name__ == "Profile" for o in m.objects.values()),
      f"{len(m.objects)} objects")

m = read(ECLIPSE_PROFILE)
check("a feature-named child with no xmi:type is constructed, not dropped",
      len(m.unmapped) == 0, f"unmapped={m.unmapped}")

print("\n== refusals (no silent empty model) ==")
try:
    read(XMI_1X)
    check("XMI 1.x is refused", False, "returned a model")
except xmi21.UnsupportedDialect as e:
    check("XMI 1.x is refused with a diagnostic naming the document element",
          "<XMI>" in str(e) and "eclipse.org/uml2/" in str(e), str(e).split(":")[1].strip())

try:
    read(DIAGRAM_XML)
    check("a non-model XML document is refused", False, "returned a model")
except xmi21.UnsupportedDialect as e:
    check("a non-model XML document is refused", "<Diagram>" in str(e))

print("\n== empty is empty, not an error ==")
m = read(EMPTY_OK)
check("a valid UML document with no content yields an empty model, root still counted",
      len(m.objects) == 1 and len(m.roots) == 1, f"{len(m.objects)} objects")

print(f"\nRESULT: {len(PASS)} passed, {len(FAIL)} failed")
sys.exit(1 if FAIL else 0)
