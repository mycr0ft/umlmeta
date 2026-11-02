#!/usr/bin/env python
"""ocl_corpus.py — export and measure the OCL corpus frozen in the generated
modules.

The generated runtimes carry the normative constraint bodies as OCL text
(`cls.CONSTRAINTS`). This script is the O0 artifact: one command that
answers "what OCL do we have, and how much can we parse/lower?" without
hand-writing imports, and that can dump the corpus for offline work.

    python scripts/ocl_corpus.py                # coverage table
    python scripts/ocl_corpus.py --out X.json   # export the corpus
    python scripts/ocl_corpus.py --check        # assert the pinned counts

Standard library only. Run from the repo root with the project venv.
"""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from umlmeta import ocl_parse as P        # noqa: E402
from umlmeta import ocl_emit as E         # noqa: E402

MODULES = ("uml25", "sysml2", "sysml")

# pinned corpus facts (re-pin deliberately when a generator changes)
PINNED = {
    "uml25": 449,
    "sysml2": 623,
    "sysml": 143,
    "total": 1215,
    "nospec": 24,
    "parse": 1166,
    "lower": 676,
}


def collect():
    import importlib
    rows = []
    for modname in MODULES:
        mod = importlib.import_module("umlmeta." + modname)
        for cls in vars(mod).values():
            if not isinstance(cls, type):
                continue
            for name, body in cls.__dict__.get("CONSTRAINTS", ()):
                rows.append({"module": modname, "class": cls.__name__,
                             "name": name, "body": body})
    return rows


NOSPEC = "(no specification serialized)"


def measure(rows):
    stats = Counter()
    reasons = Counter()
    for row in rows:
        if row["body"].strip() == NOSPEC:
            # the generator's placeholder: the spec serialized no body
            stats["nospec"] += 1
            row["parse"] = row["lower"] = False
            row["nospec"] = True
            continue
        try:
            tree = P.parse(row["body"])
            stats["parse"] += 1
        except Exception as ex:                      # noqa: BLE001
            reasons["parse: " + type(ex).__name__] += 1
            row["parse"] = False
            row["lower"] = False
            continue
        row["parse"] = True
        try:
            E.to_python(tree)
            stats["lower"] += 1
            row["lower"] = True
        except Exception as ex:                      # noqa: BLE001
            row["lower"] = False
            reasons["lower: " + str(ex)[:60]] += 1
    return stats, reasons


def digest(rows):
    payload = "\n".join(sorted(
        f"{r['module']}|{r['class']}|{r['name']}|{r['body']}" for r in rows))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, help="write the corpus as JSON")
    ap.add_argument("--check", action="store_true",
                    help="assert the pinned counts (exit 1 on drift)")
    ap.add_argument("--reasons", type=int, default=0,
                    help="show the N most common parse/lower refusals")
    args = ap.parse_args(argv)

    rows = collect()
    stats, reasons = measure(rows)
    per_module = Counter(r["module"] for r in rows)

    print(f"OCL corpus: {len(rows)} bodies   digest {digest(rows)[:16]}")
    for mod in MODULES:
        sub = [r for r in rows if r["module"] == mod]
        p = sum(1 for r in sub if r["parse"])
        lo = sum(1 for r in sub if r["lower"])
        print(f"  {mod:8s} bodies {len(sub):4d}  parse {p:4d}  lower {lo:4d}")
    print(f"  TOTAL    bodies {len(rows):4d}  parse {stats['parse']:4d}  "
          f"lower {stats['lower']:4d}  no-spec {stats['nospec']:4d}")

    if args.reasons:
        print("\ntop refusals:")
        for reason, n in reasons.most_common(args.reasons):
            print(f"  {n:4d}  {reason}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({
            "format": "umlmeta.ocl_corpus/1",
            "digest": digest(rows),
            "counts": {**{m: per_module[m] for m in MODULES},
                       "total": len(rows), "nospec": stats["nospec"],
                       "parse": stats["parse"], "lower": stats["lower"]},
            "bodies": rows,
        }, indent=1), encoding="utf-8")
        print(f"\nwrote {args.out}")

    if args.check:
        actual = {**{m: per_module[m] for m in MODULES},
                  "total": len(rows), "nospec": stats["nospec"],
                  "parse": stats["parse"], "lower": stats["lower"]}
        drift = {k: (PINNED[k], actual[k]) for k in PINNED
                 if PINNED[k] != actual[k]}
        if drift:
            print(f"\nDRIFT (pinned, actual): {drift}")
            return 1
        print("\npinned counts hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
