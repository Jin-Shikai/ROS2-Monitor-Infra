#!/usr/bin/env python3
"""Compare two verdict JSONL streams field-by-field.

Used for distribution-transparency checks: the same property evaluated in
two places (e.g. in-process vs. across MQTT) must yield the same verdict
sequence. Compared per line (in order): the fields given by --keys
(default: property_id, result, input_record_ids). Timestamps and session
ids are intentionally excluded — they differ between runtimes by design.

Usage:
    python3 eval/common/compare_verdicts.py \
        --a local_verdicts.jsonl --b remote_verdicts.jsonl \
        [--keys property_id,result,input_record_ids] [--out compare.json]

Exit code 0 when the streams are identical under the selected keys, 1
otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def load_jsonl(path: str) -> list[dict[str, Any]]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a", required=True, help="Reference verdict stream")
    parser.add_argument("--b", required=True, help="Stream compared against --a")
    parser.add_argument("--keys", default="property_id,result,input_record_ids")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    a_rows = load_jsonl(args.a)
    b_rows = load_jsonl(args.b)

    mismatches = []
    for index, (a, b) in enumerate(zip(a_rows, b_rows)):
        diff = {
            k: {"a": a.get(k), "b": b.get(k)}
            for k in keys
            if a.get(k) != b.get(k)
        }
        if diff:
            mismatches.append({"index": index, "diff": diff})

    compared = min(len(a_rows), len(b_rows))
    report = {
        "keys": keys,
        "a_count": len(a_rows),
        "b_count": len(b_rows),
        "compared": compared,
        "matched": compared - len(mismatches),
        "mismatches": mismatches[:10],
        "identical": len(a_rows) == len(b_rows) and not mismatches,
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0 if report["identical"] else 1


if __name__ == "__main__":
    sys.exit(main())
