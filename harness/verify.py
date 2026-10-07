#!/usr/bin/env python3
"""S1 verification: sanity tests, CrossHair with replay, Hypothesis.

One line per completion in --out; paper_stats.py reads these as results_*.
"""
import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from pyveri_lib import (load_tasks, contract_docstring, extract_code,
                        sanitize_and_inject, parse_signature,
                        run_sanity_tests, run_crosshair,
                        run_dynamic_contract_test, validate_counterexample)


def verify_one(task, rec, ch_timeout):
    res = dict(task_id=rec["task_id"], sample_id=rec["sample_id"],
               model=rec.get("model", "?"))
    t0 = time.time()
    func_name, _ = parse_signature(task["signature"])
    try:
        code = extract_code(rec["raw"])
        module_src = sanitize_and_inject(code, func_name,
                                         contract_docstring(task))
        res["syntax_ok"] = True
    except (SyntaxError, ValueError) as e:
        # unparsable or no function with the right name: nothing else runs
        res.update(syntax_ok=False, error=str(e)[:200],
                   tests_passed=False,
                   crosshair=dict(status="not_run"),
                   dynamic=dict(status="not_run"),
                   verify_seconds=round(time.time() - t0, 1))
        return res

    ok, msg = run_sanity_tests(module_src, task["tests"])
    res["tests_passed"] = ok
    if not ok:
        res["test_error"] = msg
    res["crosshair"] = run_crosshair(module_src,
                                     per_condition_timeout=ch_timeout)
    if res["crosshair"]["status"] == "counterexample":
        # every counterexample gets replayed; keep the replays in the log so
        # the spurious ones can be inspected later
        val = validate_counterexample(module_src, task,
                                      res["crosshair"].get("detail", ""))
        res["crosshair"]["validated"] = val["status"]
        res["crosshair"]["replays"] = val["replays"]
    res["dynamic"] = run_dynamic_contract_test(module_src, task)
    res["verify_seconds"] = round(time.time() - t0, 1)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="benchmark/tasks.jsonl")
    ap.add_argument("--completions", default="completions.jsonl")
    ap.add_argument("--out", default="results.jsonl")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--crosshair-timeout", type=int, default=10,
                    help="per-condition seconds")
    args = ap.parse_args()

    tasks = {t["task_id"]: t for t in load_tasks(args.tasks)}
    with open(args.completions) as f:
        recs = [json.loads(l) for l in f if l.strip()]

    results = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(verify_one, tasks[r["task_id"]], r,
                          args.crosshair_timeout): r for r in recs}
        for i, fut in enumerate(as_completed(futs)):
            res = fut.result()
            results.append(res)
            print(f"[{i+1}/{len(recs)}] {res['task_id']}#{res['sample_id']} "
                  f"tests={res.get('tests_passed')} "
                  f"crosshair={res['crosshair']['status']} "
                  f"dyn={res['dynamic']['status']} "
                  f"({res['verify_seconds']}s)")

    results.sort(key=lambda r: (r["task_id"], r["sample_id"]))
    with open(args.out, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    # quick summary; the paper numbers come from paper_stats.py, which also
    # requires the dynamic oracle to pass for CEF
    n = len(results)
    def frac(pred):
        return sum(1 for r in results if pred(r)) / max(1, n)
    def cex_confirmed(r):
        return (r["crosshair"]["status"] == "counterexample"
                and r["crosshair"].get("validated") == "confirmed")

    def cex_spurious(r):
        return (r["crosshair"]["status"] == "counterexample"
                and r["crosshair"].get("validated") == "spurious")

    print("\n=== SUMMARY ===")
    print(f"completions: {n} | wall: {time.time()-t0:.0f}s")
    print(f"syntax_ok:            {frac(lambda r: r['syntax_ok']):.1%}")
    print(f"sanity tests passed:  {frac(lambda r: r.get('tests_passed')):.1%}")
    print(f"CEF raw:              {frac(lambda r: r['crosshair']['status']=='no_counterexample'):.1%}")
    print(f"CEF validated:        {frac(lambda r: r['crosshair']['status']=='no_counterexample' or cex_spurious(r)):.1%}"
          "   <- spurious cex replay-refuted, counted as CEF")
    print(f"cex confirmed:        {frac(cex_confirmed):.1%}")
    print(f"cex spurious:         {frac(cex_spurious):.1%}")
    print(f"cex unvalidated:      {frac(lambda r: r['crosshair']['status']=='counterexample' and r['crosshair'].get('validated') not in ('confirmed','spurious')):.1%}")
    print(f"crosshair other:      {frac(lambda r: r['crosshair']['status'] in ('crosshair_error','harness_timeout')):.1%}")
    print(f"dynamic pass:         {frac(lambda r: r['dynamic']['status']=='pass'):.1%}")


if __name__ == "__main__":
    main()
