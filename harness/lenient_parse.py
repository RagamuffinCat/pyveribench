#!/usr/bin/env python3
"""Fence-tolerant reparse of a specs file (the DeepSeek 21.5% in 5.2).

DeepSeek-Coder likes "```json{...}```" with no newline after the fence,
and often tacks a second, junk fenced block on the end. Take the FIRST
fenced block, allow a missing newline, then run the normal parse_spec.
Reproduces logs/spec_results_ds67b_lenient.jsonl row for row when the
output is scored with spec_score.py.
usage: lenient_parse.py --specs logs/specs_ds67b.jsonl --out specs_lenient.jsonl
"""
import argparse
import json
import re

from pyveri_lib import load_tasks, parse_signature
from spec_gen import parse_spec

FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def lenient_parse(raw, func_name):
    blocks = FENCE_RE.findall(raw)
    text = blocks[0] if blocks else raw
    return parse_spec("```json\n" + text.strip() + "\n```", func_name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="benchmark/tasks.jsonl")
    ap.add_argument("--specs", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    tasks = {t["task_id"]: t for t in load_tasks(args.tasks)}
    n = ok = 0
    with open(args.specs) as f, open(args.out, "w") as out:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            fn, _ = parse_signature(tasks[r["task_id"]]["signature"])
            r["parsed"], r["parse_error"] = lenient_parse(r["raw"], fn)
            n += 1
            ok += bool(r["parsed"])
            out.write(json.dumps(r) + "\n")
    print(f"{ok}/{n} parsed -> {args.out}")


if __name__ == "__main__":
    main()
