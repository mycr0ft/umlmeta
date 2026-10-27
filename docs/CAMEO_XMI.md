# Cameo-compatible XMI output

`umlmeta.xmi_write` supports two related XMI serialization profiles:

- `write_xmi(...)` retains the older OMG/EMF corpus dialect used by the
  published UML/SysML examples.
- `write_cameo_xmi(...)` emits the UML 2.5.1-style dialect accepted by Cameo /
  MagicDraw 2024x.

The Cameo path was calibrated against a Cameo / MagicDraw 2024x export of the
VehicleExample model and is exercised end-to-end by `check_xmi_cameo.py`
(the EMF-dialect twin of that chain is `check_xmi_vehicle.py`).

## Why a separate writer mode is needed

Cameo accepts XMI, but its importer is sensitive to conventions that differ
from the older OMG corpus files. The Cameo mode makes these conventions
explicit without changing the corpus-compatible writer.

### Namespace pair and XMI version

The output uses:

```xml
xmlns:xmi="http://www.omg.org/spec/XMI/20131001"
xmlns:uml="http://www.omg.org/spec/UML/20131001"
xmi:version="2.1"
```

The SysML application namespace is:

```xml
xmlns:sysml="http://www.omg.org/spec/SysML/20181001/SysML"
```

The applied profile reference remains the standard SysML profile URI:

```xml
http://www.omg.org/spec/SysML/20181001/SysML.xmi#SysML
```

### UML Model wrapper

A `UML::Model` is written as the document root, and the supplied model
package is retained as a child `packagedElement`:

```xml
<uml:Model xmi:type="uml:Model" xmi:id="..." name="Model">
  <packagedElement xmi:type="uml:Package" name="VehicleExample">
    ...
  </packagedElement>
</uml:Model>
```

This wrapper is important. Merely changing a `uml:Package` root to
`uml:Model` flattens the user package and can result in Cameo opening the
file without the expected model package.

### EMF/P10 attributes

With the 20131001 XMI namespace, primitive values and single-valued
references are emitted as unqualified attributes, matching Cameo exports:

```xml
<packagedElement xmi:type="uml:Class"
                 xmi:id="vehicle-id"
                 name="Vehicle">
  <ownedAttribute xmi:type="uml:Port"
                  xmi:id="port-id"
                  name="pwr"
                  aggregation="composite"
                  type="power-if-id"/>
</packagedElement>
```

Multi-valued references and cross-file `href` references retain child-element
forms where required by the metamodel and XMI representation.

### Stereotype application placement and form

Cameo exports top-level stereotype applications after the UML root. The
applications use P10 attributes such as `base_Class`, `base_Port`, and
`base_Abstraction`:

```xml
</uml:Model>
<sysml:Block xmi:id="..." base_Class="vehicle-id"/>
```

The older corpus mode instead places applications before the UML root and
uses child references such as:

```xml
<sysml:Block xmi:id="...">
  <base_Class xmi:idref="vehicle-id"/>
</sysml:Block>
```

## API

Use the dedicated helper when producing a file for Cameo:

```python
from umlmeta import xmi_write

xmi = xmi_write.write_cameo_xmi(
    [model_package],
    apps=applications,
    profile_applications=(
        "http://www.omg.org/spec/SysML/20181001/SysML.xmi#SysML",
    ),
)
open("vehicle_example_cameo.xmi", "wb").write(xmi)
```

`write_cameo_xmi` is implemented as a non-mutating wrapper around
`write_xmi`. It selects the Cameo namespace pair, `xmi:version`, P10
attribute output, post-root stereotype applications, and the UML Model
wrapper. The regular `write_xmi` behavior remains unchanged for the OMG
corpus path.

## Validation

Generate and validate both output forms with:

```bash
$SYSMLPY_PYTHON check_xmi_vehicle.py   # EMF dialect: 12 checks
$SYSMLPY_PYTHON check_xmi_cameo.py     # Cameo dialect: 15 checks
```

Both checks emit the VehicleExample model as XMI, read it back with
`umlmeta.xmi21`, rehydrate the stereotype applications (child-reference form
for EMF, P10 attribute form for Cameo), transform to SysML v2 with
`umlmeta.v1_to_v2`, and verify the result is byte-identical to
`vehicle_example_v2.sysml` and parses with `sysmlpy==0.97.1`. The Cameo check
additionally verifies the namespace pair, `xmi:version`, and the `uml:Model`
project wrapper.

The generated `vehicle_example_cameo.xmi` is an XMI interchange file, not a
Cameo `.mdzip` project. Cameo-specific diagrams, project metadata, binary
layout data, and auxiliary resources are intentionally not generated.
