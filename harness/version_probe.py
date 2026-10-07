#!/usr/bin/env python3
"""Re-verify completions with whatever `crosshair` is first on PATH. Used for
the 0.0.100 probe in Section 6 (README shows the PATH trick)."""
import argparse
import json
import multiprocessing as mp
import sys

from pyveri_lib import (load_tasks, extract_code, sanitize_and_inject,
                        contract_docstring, parse_signature, run_crosshair,
                        validate_counterexample)

TASKS = {t["task_id"]: t for t in load_tasks("benchmark/tasks.jsonl")}


def probe_one(rec):
    task = TASKS[rec["task_id"]]
    fn, _ = parse_signature(task["signature"])
    out = dict(task_id=rec["task_id"], sample_id=rec["sample_id"],
               model=rec.get("model", ""))
    try:
        src = sanitize_and_inject(extract_code(rec["raw"]), fn,
                                  contract_docstring(task))
    except Exception as e:
        out.update(status="syntax_error", detail=str(e)[:200])
        return out
    ch = run_crosshair(src, per_condition_timeout=10)
    out.update(status=ch["status"], detail=ch.get("detail", "")[:400])
    if ch["status"] == "counterexample":
        val = validate_counterexample(src, task, ch.get("detail", ""))
        out["validated"] = val["status"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--completions", nargs="+",
                    default=["logs/completions_1p5b.jsonl", "logs/completions_3b.jsonl",
                             "logs/completions_7b.jsonl"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    recs = []
    for path in args.completions:
        with open(path) as f:
            for line in f:
                if line.strip():
                    recs.append(json.loads(line))
    print(f"probing {len(recs)} completions", file=sys.stderr)

    with open(args.out, "w") as out, mp.Pool(args.workers) as pool:
        for i, r in enumerate(pool.imap_unordered(probe_one, recs)):
            out.write(json.dumps(r) + "\n")
            out.flush()
            if (i + 1) % 50 == 0:
                print(f"[{i+1}/{len(recs)}]", file=sys.stderr)


if __name__ == "__main__":
    main()
