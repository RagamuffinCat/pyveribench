#!/usr/bin/env python3
"""Merge salvage_verify.py output back into a results file.
usage: merge_salvaged.py results.jsonl salvaged_rows.jsonl out.jsonl
Rows that salvage_verify re-verified replace the syntax-failed originals;
everything else is copied as is. This is how results_ds67b_salvaged.jsonl
was made from results_ds67b.jsonl."""
import json, sys

base, sal, dst = sys.argv[1:4]
rows = [json.loads(l) for l in open(base) if l.strip()]
fixed = {(r["task_id"], r["sample_id"]): r
         for r in (json.loads(l) for l in open(sal) if l.strip())}
with open(dst, "w") as out:
    for r in rows:
        out.write(json.dumps(fixed.get((r["task_id"], r["sample_id"]), r)) + "\n")
print(f"{len(fixed)} rows replaced, {len(rows)} written")
