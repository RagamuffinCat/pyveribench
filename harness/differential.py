#!/usr/bin/env python3
"""How far CEF is from reference equivalence (5.1): run every CEF-validated
completion and the reference on fresh strategy-drawn inputs and count the
ones that disagree somewhere. Disagreement is not necessarily a bug, 35 of
the contracts admit more than one behavior."""
import argparse
import copy
import json
import multiprocessing as mp
import sys

from pyveri_lib import (load_tasks, extract_code, sanitize_and_inject,
                        contract_docstring, parse_signature, strategy_for_param)


def gen_inputs(task, n_examples):
    # draw up to 3n and keep the first n that satisfy the preconditions
    from hypothesis import given, settings, HealthCheck, strategies as st

    fn, params = parse_signature(task["signature"])
    strats = [eval(strategy_for_param(task, p, ann), {"st": st})
              for p, ann in params]
    collected = []

    @settings(max_examples=n_examples * 3, deadline=None, derandomize=True,
              suppress_health_check=list(HealthCheck))
    @given(st.data())
    def _collect(data):
        if len(collected) >= n_examples:
            return
        args = [data.draw(sgy) for sgy in strats]
        ns = {p: a for (p, _), a in zip(params, args)}
        try:
            if all(eval(pre, dict(ns)) for pre in task["pre"]):
                collected.append(copy.deepcopy(args))
        except Exception:
            pass

    try:
        _collect()
    except Exception:
        pass
    return collected


def behavior(module_src, fn, inputs, timeout=30):
    # runs in-process, timeout is unused; these completions already passed
    # all three oracles so a hang would be a surprise
    ns = {}
    try:
        exec(module_src, ns)
    except Exception as e:
        return None
    f = ns.get(fn)
    if f is None:
        return None
    out = []
    for args in inputs:
        try:
            out.append(("ok", f(*copy.deepcopy(args))))
        except Exception as e:
            out.append(("exc", type(e).__name__))
    return out


def check_one(job):
    task, comp_raw, inputs, ref_out = job
    fn, _ = parse_signature(task["signature"])
    try:
        src = sanitize_and_inject(extract_code(comp_raw), fn,
                                  contract_docstring(task))
    except Exception:
        return task["task_id"], None
    cand = behavior(src, fn, inputs)
    if cand is None:
        return task["task_id"], None
    diffs = sum(1 for a, b in zip(ref_out, cand) if a != b)
    return task["task_id"], diffs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="benchmark/tasks.jsonl")
    ap.add_argument("--completions", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--examples", type=int, default=200)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    tasks = {t["task_id"]: t for t in load_tasks(args.tasks)}
    comps = {}
    with open(args.completions) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                comps[(r["task_id"], r["sample_id"])] = r["raw"]

    def cef(r):
        ch = r["crosshair"]
        cex_real = (ch["status"] == "counterexample"
                    and ch.get("validated", "confirmed") != "spurious")
        return (r.get("syntax_ok") and not cex_real
                and r["dynamic"]["status"] == "pass")

    cef_keys = []
    with open(args.results) as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                if cef(r):
                    cef_keys.append((r["task_id"], r["sample_id"]))
    print(f"CEF-validated completions: {len(cef_keys)}", file=sys.stderr)

    inputs_by_task, ref_by_task = {}, {}
    for tid in sorted({k[0] for k in cef_keys}):
        t = tasks[tid]
        ins = gen_inputs(t, args.examples)
        fn, _ = parse_signature(t["signature"])
        ref_src = t["ref_impl"]
        ref = behavior(ref_src, fn, ins)
        if ref is None or not ins:
            print(f"  [warn] {tid}: no inputs/ref failed", file=sys.stderr)
            continue
        inputs_by_task[tid], ref_by_task[tid] = ins, ref

    jobs = [(tasks[t], comps[(t, s)], inputs_by_task[t], ref_by_task[t])
            for (t, s) in cef_keys if t in inputs_by_task]
    with mp.Pool(args.workers) as pool:
        out = pool.map(check_one, jobs)

    n = len(out)
    err = sum(1 for _, d in out if d is None)
    agree = sum(1 for _, d in out if d == 0)
    disagree = [(t, d) for t, d in out if d and d > 0]
    print(f"\ncompared {n} CEF-validated completions "
          f"({args.examples} strategy inputs each)")
    print(f"  behaviorally identical to reference: {agree} ({agree/n:.1%})")
    print(f"  disagree on >=1 input: {len(disagree)} ({len(disagree)/n:.1%})")
    print(f"  unexecutable in differ: {err}")
    per = {}
    for t, d in disagree:
        per[t] = per.get(t, 0) + 1
    for t, c in sorted(per.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c} disagreeing completions")


if __name__ == "__main__":
    main()
