#!/usr/bin/env python
"""cli.py — the `umlmeta` command: transform | link | diff | sync.

Pathway: docs/v1-v2-linkage-pathway.md, milestone M5 ("so the loop is
scriptable"). Every verb is a thin shell over the library functions that the
check suite already gates; nothing here re-implements a mapping.

Exit codes: 0 success · 1 failure or unresolved conflicts · 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _fail(msg):
    print(f"umlmeta: {msg}", file=sys.stderr)
    return 1


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, doc):
    Path(path).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")


def cmd_transform(args):
    from . import link as L
    from . import v1_to_v2_as as A
    from . import v2_json as J
    from . import v2_library as LIB
    from . import v2_text as T

    outs = A.transform_xmi_files(args.v1, side_channel=args.side_channel)
    if not outs:
        return _fail(f"no transformable root package in {args.v1}")
    root = outs[0]
    ids = L.assign_element_ids(root)
    if args.library_stub:
        LIB.resolve([root])
    out = Path(args.output or (Path(args.v1[0]).stem + ".v2.json"))
    if out.suffix == ".sysml":
        out.write_text(T.emit_model([root]) + "\n", encoding="utf-8")
    else:
        _write_json(out, J.to_json(root, ids=ids))
    if args.text:
        Path(args.text).write_text(T.emit_model([root]) + "\n",
                                   encoding="utf-8")
    if args.sidecar:
        L.write_sidecar(args.sidecar, L.sidecar(root))
    print(f"wrote {out}" + (f" + {args.sidecar}" if args.sidecar else ""))
    return 0


def cmd_link(args):
    """Re-assert identities and refresh the graph hash for a saved model.

    A JSON model carries no v1 provenance, so a sidecar rebuilt from it has no
    records; when one already exists its pair records (and elision ledger) are
    carried through rather than destroyed - dropping them would silently cut
    the link the file exists to hold.
    """
    from . import link as L
    from . import v2_json as J

    root = J.from_json_text(Path(args.model).read_text(encoding="utf-8"))
    ids = L.assign_element_ids(root)
    prev = None
    if Path(args.sidecar).exists():
        try:
            prev = L.read_sidecar(args.sidecar)
        except ValueError:
            prev = None
    doc = L.sidecar(root)
    if prev and not doc["records"]:
        doc["records"] = prev.get("records", [])
        doc["elisions"] = prev.get("elisions", [])
    L.write_sidecar(args.sidecar, doc)
    print(f"wrote {args.sidecar} ({len(ids)} identities, "
          f"{len(doc['records'])} records)")
    return 0


def cmd_diff(args):
    from . import link as L
    from . import sync as S
    from . import v2_json as J

    a = J.from_json_text(Path(args.old).read_text(encoding="utf-8"))
    b = J.from_json_text(Path(args.new).read_text(encoding="utf-8"))
    d = S.diff_graph(a, b)
    for kind in ("added", "removed", "changed"):
        for eid, tn in sorted(d[kind].items()):
            print(f"{kind:8} {tn:22} {eid}")
    total = sum(len(v) for v in d.values())
    print(f"-- {total} change(s)")
    return 0 if total == 0 else 1


def cmd_sync(args):
    from . import link as L
    from . import sync as S
    from . import v2_json as J

    side = L.read_sidecar(args.sidecar)
    model = J.from_json_text(Path(args.model).read_text(encoding="utf-8"))
    from . import xmi21
    v1_roots = []
    scopes = xmi21.read_xmi21_files(args.v1)
    for root in scopes.roots:
        v1_roots.append(root)
    if len(v1_roots) != 1:
        return _fail("sync expects exactly one v1 root package "
                     f"(found {len(v1_roots)})")
    result = S.merge(v1_roots[0], side, model)
    out = Path(args.output or args.model)
    _write_json(out, J.to_json(result.root,
                                ids=L.assign_element_ids(result.root)))
    if args.sidecar_out:
        L.write_sidecar(args.sidecar_out, L.sidecar(result.root))
    print(f"merged -> {out}: {result.report}")
    for c in result.conflicts:
        print(f"CONFLICT {c['kind']} {c.get('path')} ({c['element_id']})",
              file=sys.stderr)
    return 0 if not result.conflicts else 1


def build_parser():
    p = argparse.ArgumentParser(prog="umlmeta", description=(
        "UML/SysML metamodels, the SysML v1 -> v2 transformation, and the "
        "v1 <-> v2 link (transform | link | diff | sync)."))
    sub = p.add_subparsers(dest="command", required=True)

    t = sub.add_parser("transform", help="v1 XMI -> v2 model (+ sidecar)")
    t.add_argument("v1", nargs="+", help="v1 XMI file(s) - read as one scope")
    t.add_argument("-o", "--output", help="output .json (default) or .sysml")
    t.add_argument("--text", help="also write the textual notation here")
    t.add_argument("--sidecar", help="write the v1<->v2 link sidecar here")
    t.add_argument("--side-channel", action="store_true",
                   help="carry elided v1 content into the v2 model as metadata")
    t.add_argument("--library-stub", action="store_true",
                   help="build the resolvable SysMLv1Library stub package")
    t.set_defaults(func=cmd_transform)

    lk = sub.add_parser("link", help="(re)write the sidecar for a v2 model")
    lk.add_argument("model", help="v2 model JSON (umlmeta.v2json/1)")
    lk.add_argument("--sidecar", required=True)
    lk.set_defaults(func=cmd_link)

    d = sub.add_parser("diff", help="element-level diff of two v2 models")
    d.add_argument("old")
    d.add_argument("new")
    d.set_defaults(func=cmd_diff)

    s = sub.add_parser("sync", help="three-way merge v1 + sidecar + v2 model")
    s.add_argument("--v1", nargs="+", required=True,
                   help="the NEW v1 snapshot (XMI)")
    s.add_argument("--sidecar", required=True, help="the link sidecar")
    s.add_argument("--model", required=True, help="the existing v2 model JSON")
    s.add_argument("-o", "--output", help="merged model (default: in place)")
    s.add_argument("--sidecar-out", help="write the refreshed sidecar here")
    s.set_defaults(func=cmd_sync)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":              # pragma: no cover
    sys.exit(main())
