#!/usr/bin/env python3
"""uml2py boxes_view — render v1 data (UML 2.5.1 / SysML v1 model
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
    """Build a Block Definition Diagram from uml2py data.

    Parameters
    ----------
    scope : a Package / Model / Namespace object (uml2py generated
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


def render_bdd_boxes(scope, routing='orthogonal', **layout_kw) -> str:
    d = as_bdd_boxes(scope)
    d.render()
    return d.render()


def render_bdd_boxes_svg(scope, routing='orthogonal', **layout_kw) -> str:
    d = as_bdd_boxes(scope)
    return d.render_svg(routing=routing)