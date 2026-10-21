#!/usr/bin/env python3
"""umlmeta boxes_view — render v1 data (UML 2.5.1 / SysML v1 model
objects) as SysML v1 diagrams through the sibling diagramboxes package,
the same pattern as sysmlpy's boxes_view adapters.

Supported views (this commit): Block Definition Diagram (bdd).
- A block = a Class (or DataType) carrying the Block stereotype (or any
  Class under the walked scope when the model is plain UML).
- Part properties (aggregation == 'composite') / value properties
  (ValueProperty stereotype) / plain properties render as rows in the
  block's parts / values compartments — Delligatti §3.4/Fig 3.5:
  properties are COMPARTMENT STRINGS, not nested boxes.
- Ports render on the block's boundary (§4.12); flow specs on a port
  surface the port's items as its label.
- Generalizations render as open-triangle edges to the general class.
- Reference properties (ReferenceProperty stereotype) render as rows in
  a 'references' compartment (§3.4).
- Packages render as folder-tab views (§10.4) holding their owned
  packages and blocks.

Rendering = diagramboxes (diagramboxes on the path); the caller renders
braille (`Diagram.render()`) or SVG (`render_svg()`).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

try:
    from diagramboxes import Diagram
except ImportError:
    if os.path.isdir(os.path.expanduser('~/proj/diagramboxes')):
        sys.path.insert(0, os.path.expanduser('~/proj/diagramboxes'))
        from diagramboxes import Diagram
    else:
        raise

def _stereo_name(obj):
    """The stereotype name for an element's `_applied_stereotypes`
    list of (profile, stereo, app_id) tuples."""
    apps = getattr(obj, '_applied_stereotypes', None) or []
    if not apps:
        return None
    return apps[0][1]


def _block_sides(n):
    """Alternate left/right for boundary ports (the BDD port spread)."""
    return 'left' if n % 2 == 0 else 'right'


def as_bdd_boxes(scope, frame_kind='bdd', element_kind=None,
                 element_name=None, diagram_name=None):
    """Build a Block Definition Diagram from umlmeta data.

    Parameters
    ----------
    scope : a Package / Model / Namespace object (umlmeta generated
        metaclasses), or a list of elements.
    frame_* : the diagram-kind frame strings (Delligatti §2.4).

    Returns
    -------
    diagramboxes.Diagram
    """
    d = Diagram()
    if frame_kind:
        d.add_frame(frame_kind, element_kind, element_name,
                    diagram_name)

    pkg_views = {}      # package id -> View (folder tab)
    block_nodes = {}    # class id -> Node
    ports_seen = {}     # class id -> count (for side spreading)

    def _walk_pkg(pkg, parent_view=None):
        el = pkg

        view = None
        pname = getattr(el, 'name', None)
        if pname is not None and type(el).__name__ in (
                'Package', 'Model', 'Profile'):
            view = parent_view or d.add_view(
                pname, stereotypes=['package'])
            pkg_views[id(el)] = view

        blocks = []
        for child in (getattr(el, 'packagedElement', None) or []):
            if type(child).__name__ == 'Package':
                _walk_pkg(child, view)
                continue
            if type(child).__name__ in ('Class', 'DataType', 'Signal',
                                        'Enumeration', 'Interface'):
                blocks.append(child)

        # two passes: every block draws BEFORE any generalization edge
        # resolves its target (a generalization to a later sibling must
        # not mint a duplicate node)
        for b in blocks:
            _draw_block(b, view, draw_edges=False)
        for b in blocks:
            _block_edges(b)

    def _draw_block(b, view, draw_edges=True):
        shape = _block_shape(b, view)
        if draw_edges:
            _block_edges(b)
        return shape

    def _block_shape(b, view):
        kind = type(b).__name__
        stereo = _stereo_name(b)
        # the frame's block context suppresses a bare «block»; anything
        # else (Signal, Interface, «value type», «enumeration»…) prints
        st_lines = None if stereo in (None, 'Block') else [stereo]
        node = d.add_node(getattr(b, 'name', None) or 'unnamed',
                          stereotypes=st_lines)
        if view is not None:
            view.add_child(node)
        block_nodes[id(b)] = node

        # ports on the boundary (flow-qualified labels, §4.12)
        n = 0
        for p in list(getattr(b, 'ownedAttribute', None) or []):
            if type(p).__name__ != 'Port':
                continue
            lab = getattr(p, 'name', None) or ''
            t = getattr(p, 'type', None)
            if t is not None and getattr(t, 'name', None):
                lab = '%s : %s' % (lab, t.name)
            node.add_port(lab, side=_block_sides(n), direction=None)
            n += 1
        ports_seen[id(b)] = n

        # compartment rows: parts / values / references / plain
        parts, values, refs, plain = [], [], [], []
        for p in (getattr(b, 'ownedAttribute', None) or []):
            if type(p).__name__ == 'Port':
                continue
            tname = getattr(getattr(p, 'type', None), 'name', None)
            mult = _end_multiplicity(b, p)
            nm = getattr(p, 'name', None)
            if not nm:
                continue
            stereo = _stereo_name(p)
            s = (p.aggregation if isinstance(p.aggregation, str) else None) \
                if hasattr(p, 'aggregation') else None
            is_part = (s == 'composite')
            is_ref = stereo in ('ReferenceProperty',) or s == 'shared'
            if stereo == 'ValueProperty' or stereo == 'Measurement':
                values.append((nm, tname, mult))
            elif is_ref:
                refs.append((nm, tname, mult))
            elif is_part:
                parts.append((nm, tname, mult))
            else:
                plain.append((nm, tname, mult))

        def _row(nm, tname, mult):
            s = '%s : %s' % (nm, tname) if tname else nm
            if mult:
                s += ' [%s]' % mult
            return s

        if values:
            node.compartments = list(getattr(node, 'compartments', None) or [])
            node.compartments.append(
                ('values', [_row(*r) for r in values]))
        if parts:
            node.compartments = list(getattr(node, 'compartments', None) or [])
            node.compartments.append(
                ('parts', [_row(*r) for r in parts]))
        if refs:
            node.compartments = list(getattr(node, 'compartments', None) or [])
            node.compartments.append(
                ('references', [_row(*r) for r in refs]))
        if plain:
            node.attributes = [_row(*r) for r in plain]

    def _block_edges(b):
        # generalizations: open triangle at the general class
        for g in (getattr(b, 'generalization', None) or []):
            gcls = getattr(g, 'general', None)
            if gcls is None:
                continue
            node = block_nodes.get(id(b))
            target_node = block_nodes.get(id(gcls))
            if node is None or target_node is None:
                continue   # target outside the walked scope
            d.add_edge(node, target_node, target_style='triangle')
            node._calc_size(); target_node._calc_size()

    def _end_multiplicity(owner, prop):
        # the multiplicity of the end that OWNS this property is the
        # property's own lower/upper
        lo = getattr(prop, 'lower', None)
        up = getattr(prop, 'upper', None)
        if lo is None and up is None:
            return None
        if (lo or '0') == '1' and (up or '1') == '1':
            return None       # 1..1 = default, omitted (Delligatti §3.4)
        if (up or lo) == (lo or up):
            return lo or up
        return '%s..%s' % (lo, up)

    if isinstance(scope, (list, tuple)):
        for el in scope:
            if type(el).__name__ in ('Package', 'Model'):
                _walk_pkg(el)
            else:
                _draw_block(el)
    else:
        _walk_pkg(scope)

    return d


def as_deployment_boxes(scope, frame_kind='deployment',
                        element_kind=None, element_name=None):
    """Build a UML 2.5.1 deployment diagram (ch19) from umlmeta data.

    - Node, Device, ExecutionEnvironment, or an InstanceSpecification
      of one = a perspective cube (instance labels are the ':name'
      string); the deployment's elements connect in.
    - Artifact = a Class rectangle + the keyword artifact.
    - Deployment.deployedArtifact x location/deployment's owner = the
      dashed 'deploy' dependency arrow (19.2.4).
    - Artifact.manifestation[] = dashed 'manifest' lines (19.3.x).
    - CommunicationPath memberEnds = plain association links (19.4.4).
    """
    d = Diagram()
    if frame_kind:
        d.add_frame(frame_kind, element_kind, element_name, None)

    def _name(el, default='unnamed'):
        return getattr(el, 'name', None) or default

    def _node_of(el, inst=False):
        kinds = []
        st = getattr(el, '_applied_stereotypes', None)
        if st:
            kinds = [s[1] for s in st]
        return d.node(_name(el), kinds=kinds)

    node_map = {}

    def _add(el, cube):
        cube_ = d.node(_name(el), kinds=[]) if cube else d.add_node(
            _name(el), stereotypes=['artifact'])
        node_map[id(el)] = cube_
        d.nodes.append(cube_)
        return cube_

    def _walk(pkg):
        for child in (getattr(pkg, 'packagedElement', None) or []):
            tn = type(child).__name__
            if tn == 'Package':
                _walk(child)
            elif tn == 'Node':
                node_map[id(child)] = _node_of(child)
            elif tn == 'Artifact':
                node_map[id(child)] = d.artifact(_name(child))
            elif tn == 'InstanceSpecification':
                node_map[id(child)] = d.node(_name(child))
            elif tn == 'Component':
                node_map[id(child)] = d.add_node(_name(child))
        # CommunicationPath (19.4.4): a plain association link between
        # its endpoint types
        for child in (getattr(pkg, 'packagedElement', None) or []):
            if type(child).__name__ != 'CommunicationPath':
                continue
            ends = [p for p in (getattr(child, 'memberEnd', None) or [])
                    if getattr(p, 'type', None) is not None]
            if len(ends) == 2:
                d.add_edge(node_map.get(id(ends[0].type)),
                           node_map.get(id(ends[1].type)))
        # deployments owned by each element
        for child in (getattr(pkg, 'packagedElement', None) or []):
            for dep in (getattr(child, 'deployment', None) or []):
                for art in (getattr(dep, 'deployedArtifact', None) or []):
                    if isinstance(art, (str, int)):
                        continue
                    if id(art) not in node_map:
                        node_map[id(art)] = d.artifact(_name(art))
                    d.deploy(node_map[id(art)], node_map[id(child)])
            for man in (getattr(child, 'manifestation', None) or []):
                util = getattr(man, 'utilizedElement', None)
                if util is None:
                    continue
                if id(util) not in node_map:
                    node_map[id(util)] = d.add_node(_name(util))
                d.manifest(node_map[id(child)], node_map[id(util)])

    if isinstance(scope, (list, tuple)):
        for el in scope:
            _walk(el)
    else:
        _walk(scope)

    d.render()
    return d


def render_bdd_boxes(scope, routing='orthogonal', **layout_kw) -> str:
    d = as_bdd_boxes(scope)
    d.render()
    return d.render()


def render_bdd_boxes_svg(scope, routing='orthogonal', **layout_kw) -> str:
    d = as_bdd_boxes(scope)
    return d.render_svg(routing=routing)