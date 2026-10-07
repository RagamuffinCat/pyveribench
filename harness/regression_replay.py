#!/usr/bin/env python3
"""Regression check for S3, added late in the study (5.3).

A repair declared verified by repair.py is re-checked against the concrete
failure evidence S1 recorded for that sample: its replay-confirmed
counterexample and its Hypothesis witness. If either still violates the
contract on the final code, the repair was verifier noise (unseeded
search under a budget) and gets repaired=False. paper_stats.py applies
the output.
"""
import argparse
import glob
import json
import multiprocessing as mp
import os
import re
import sys

from pyveri_lib import (load_tasks, extract_code, sanitize_and_inject,
                        contract_docstring, parse_signature,
                        validate_counterexample)

TASKS = {}


def final_src(task, rec, s1_raw):
    fn, _ = parse_signature(task["signature"])
    raw = rec["trail"][-1]["raw"] if rec["trail"] else s1_raw
    return sanitize_and_inject(extract_code(raw), fn, contract_docstring(task))


def replay_cex(src, task, detail):
    v = validate_counterexample(src, task, detail)
    return v["status"]


def replay_dynamic(src, task, violation):
    # dress the Hypothesis witness up as a CrossHair line so the same replay
    # code can handle it
    if not violation or "args" not in violation:
        return "none"
    fn, _ = parse_signature(task["signature"])
    try:
        args = eval(violation["args"], {})
    except Exception:
        return "unknown"
    call = fn + "(" + ", ".join(f"{k}={v!r}" for k, v in args.items()) + ")"
    v = validate_counterexample(src, task, "error: regression when calling " + call)
    return v["status"]


def one(job):
    mode, model, rec, s1, s1_raw = job
    task = TASKS[rec["task_id"]]
    out = dict(mode=mode, model=model, task_id=rec["task_id"],
               sample_id=rec["sample_id"], final_verified=rec["final_verified"],
               rounds_used=rec["rounds_used"])
    if not rec["final_verified"]:
        out.update(cex_regress="n/a", dyn_regress="n/a", repaired=False)
        return out
    try:
        src = final_src(task, rec, s1_raw)
    except Exception as e:
        out.update(cex_regress="unknown", dyn_regress="unknown", repaired=False,
                   note="final code unparsable: " + str(e)[:100])
        return out
    ch = s1["crosshair"]
    if ch["status"] == "counterexample" and ch.get("validated") == "confirmed":
        out["cex_regress"] = replay_cex(src, task, ch["detail"])
    else:
        out["cex_regress"] = "none"
    dyn = s1["dynamic"]
    if dyn["status"] in ("fail", "exception") and dyn.get("violation"):
        out["dyn_regress"] = replay_dynamic(src, task, dyn["violation"])
    else:
        out["dyn_regress"] = "none"
    out["repaired"] = (out["cex_regress"] != "confirmed"
                       and out["dyn_regress"] != "confirmed")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="benchmark/tasks.jsonl")
    ap.add_argument("--logs", default="logs")
    ap.add_argument("--out", default="logs/regression_s3.jsonl")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    TASKS.update({t["task_id"]: t for t in load_tasks(a.tasks)})

    s1, raws = {}, {}
    for m in ("1p5b", "3b", "7b"):
        for line in open(os.path.join(a.logs, f"results_{m}.jsonl")):
            if line.strip():
                r = json.loads(line)
                s1[(m, r["task_id"], r["sample_id"])] = r
        for line in open(os.path.join(a.logs, f"completions_{m}.jsonl")):
            if line.strip():
                r = json.loads(line)
                raws[(m, r["task_id"], r["sample_id"])] = r["raw"]

    jobs = []
    pat = re.compile(r"repair_(cex|test|binary)_(1p5b|3b|7b)(_mustchange)?\.jsonl$")
    for path in sorted(glob.glob(os.path.join(a.logs, "repair_*.jsonl"))):
        m = pat.search(path)
        if not m:
            continue
        mode = m.group(1) + ("_mustchange" if m.group(3) else "")
        model = m.group(2)
        for line in open(path):
            if line.strip():
                rec = json.loads(line)
                key = (model, rec["task_id"], rec["sample_id"])
                jobs.append((mode, model, rec, s1[key], raws[key]))
    print(f"{len(jobs)} repair samples", file=sys.stderr)
    with mp.Pool(a.workers) as pool, open(a.out, "w") as f:
        for r in pool.imap(one, jobs, chunksize=4):
            f.write(json.dumps(r) + "\n")
    rows = [json.loads(l) for l in open(a.out)]
    ok = [r for r in rows if r["final_verified"]]
    flipped = [r for r in ok if not r["repaired"]]
    print(f"declared repaired: {len(ok)}; fail regression: {len(flipped)}")
    for r in flipped:
        print("  ", r["mode"], r["model"], r["task_id"], r["sample_id"],
              "cex:", r["cex_regress"], "dyn:", r["dyn_regress"], r.get("note", ""))


if __name__ == "__main__":
    main()
