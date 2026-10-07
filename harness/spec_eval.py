#!/usr/bin/env python3
"""Score one contract against a task's mutants.

Used by spec_score.py for generated specs, and run directly (--symbolic) as
the reference-contract QA that produces logs/reference_contract_qa.jsonl.
"""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor

from pyveri_lib import (load_tasks, contract_docstring, sanitize_and_inject,
                        parse_signature, run_crosshair,
                        run_dynamic_contract_test)


def eval_spec_on_task(task, pre, post, noneq_mutants, symbolic=False,
                      max_examples=200):
    spec_task = dict(task, pre=pre, post=post)
    fn, _ = parse_signature(task["signature"])
    ds = contract_docstring(spec_task)

    # sound = the reference implementation satisfies the contract
    ref_src = sanitize_and_inject(task["ref_impl"], fn, ds)
    dyn_ref = run_dynamic_contract_test(ref_src, spec_task,
                                        max_examples=max_examples)
    sound_dyn = dyn_ref["status"] == "pass"
    sound_sym = None
    if symbolic:
        # careful: this is False for a harness timeout too, not only for a
        # counterexample. Run the QA with --workers 1 (README).
        ch = run_crosshair(ref_src, per_condition_timeout=8)
        sound_sym = ch["status"] == "no_counterexample"

    kills = []
    for m in noneq_mutants:
        try:
            m_src = sanitize_and_inject(m["code"], fn, ds)
        except Exception:
            kills.append(dict(mutant_id=m["mutant_id"], killed=None))
            continue
        dyn = run_dynamic_contract_test(m_src, spec_task,
                                        max_examples=max_examples)
        killed = dyn["status"] == "fail"
        how = "dynamic" if killed else None
        if not killed and symbolic:
            # mutants the dynamic check misses get a CrossHair pass; four of
            # the 391 are only killed this way (Appendix B)
            ch = run_crosshair(m_src, per_condition_timeout=8)
            if ch["status"] == "counterexample":
                killed, how = True, "symbolic"
        kills.append(dict(mutant_id=m["mutant_id"], killed=killed, how=how))

    n = len([k for k in kills if k["killed"] is not None])
    n_killed = len([k for k in kills if k["killed"]])
    return dict(task_id=task["task_id"],
                sound_dynamic=sound_dyn, sound_symbolic=sound_sym,
                n_mutants=n, n_killed=n_killed,
                skr=round(n_killed / n, 3) if n else None,
                kills=kills)


def _qa_one(args):
    task, muts, symbolic = args
    return eval_spec_on_task(task, task["pre"], task["post"], muts,
                             symbolic=symbolic)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="benchmark/tasks.jsonl")
    ap.add_argument("--mutants", default="benchmark/mutants.jsonl")
    ap.add_argument("--out", default="spec_qa.jsonl")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--symbolic", action="store_true",
                    help="run CrossHair on mutants the dynamic check misses")
    args = ap.parse_args()

    tasks = load_tasks(args.tasks)
    by_task = {}
    with open(args.mutants) as f:
        for line in f:
            m = json.loads(line)
            if m["equivalent"] is False:
                by_task.setdefault(m["task_id"], []).append(m)

    jobs = [(t, by_task.get(t["task_id"], []), args.symbolic) for t in tasks]
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for r in ex.map(_qa_one, jobs):
            results.append(r)
            name = next(t["name"] for t in tasks if t["task_id"] == r["task_id"])
            flag = "" if (r["sound_dynamic"] and (r["skr"] or 0) >= 0.6) \
                else "   <-- WEAK/UNSOUND"
            print(f"{r['task_id']} {name:20s} sound={r['sound_dynamic']} "
                  f"SKR={r['skr']} ({r['n_killed']}/{r['n_mutants']}){flag}")

    with open(args.out, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    skrs = [r["skr"] for r in results if r["skr"] is not None]
    print(f"\nmean SKR: {sum(skrs)/len(skrs):.3f} | "
          f"all sound: {all(r['sound_dynamic'] for r in results)}")


if __name__ == "__main__":
    main()
