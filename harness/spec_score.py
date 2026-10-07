#!/usr/bin/env python3
"""S2 scoring (Table 2): soundness on the reference, then Spec Kill Rate over
the equivalent=false mutants. Dynamic check only unless --symbolic."""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor

from pyveri_lib import load_tasks
from spec_eval import eval_spec_on_task


def _score_one(job):
    task, spec_rec, muts, symbolic = job
    base = dict(task_id=spec_rec["task_id"], sample_id=spec_rec["sample_id"],
                model=spec_rec.get("model", "?"))
    if not spec_rec.get("parsed"):
        base.update(parse_ok=False, parse_error=spec_rec.get("parse_error"),
                    sound=None, skr=None, trivial=None)
        return base
    p = spec_rec["parsed"]
    r = eval_spec_on_task(task, p["pre"], p["post"], muts, symbolic=symbolic)
    # trivial = sound but kills nothing (the 17% at 1.5B in Table 2)
    sound = r["sound_dynamic"]
    base.update(parse_ok=True, pre=p["pre"], post=p["post"],
                sound=sound, n_mutants=r["n_mutants"],
                n_killed=r["n_killed"], skr=r["skr"],
                trivial=(sound and r["n_killed"] == 0))
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="benchmark/tasks.jsonl")
    ap.add_argument("--mutants", default="benchmark/mutants.jsonl")
    ap.add_argument("--specs", default="specs.jsonl")
    ap.add_argument("--out", default="spec_results.jsonl")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--symbolic", action="store_true")
    args = ap.parse_args()

    tasks = {t["task_id"]: t for t in load_tasks(args.tasks)}
    by_task = {}
    with open(args.mutants) as f:
        for line in f:
            m = json.loads(line)
            if m["equivalent"] is False:
                by_task.setdefault(m["task_id"], []).append(m)
    with open(args.specs) as f:
        specs = [json.loads(l) for l in f if l.strip()]

    jobs = [(tasks[s["task_id"]], s, by_task.get(s["task_id"], []),
             args.symbolic) for s in specs]
    results = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for i, r in enumerate(ex.map(_score_one, jobs)):
            results.append(r)
            print(f"[{i+1}/{len(jobs)}] {r['task_id']}#{r['sample_id']} "
                  f"parse={r['parse_ok']} sound={r.get('sound')} "
                  f"SKR={r.get('skr')}")

    with open(args.out, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    n = len(results)
    parsed = [r for r in results if r["parse_ok"]]
    sound = [r for r in parsed if r["sound"]]
    skrs = [r["skr"] for r in sound if r["skr"] is not None]
    print("\n=== S2 SUMMARY ===")
    print(f"specs:        {n}")
    print(f"parse rate:   {len(parsed)/max(1,n):.1%}")
    print(f"sound rate:   {len(sound)/max(1,len(parsed)):.1%} (of parsed)")
    print(f"trivial rate: {sum(1 for r in sound if r['trivial'])/max(1,len(sound)):.1%} (of sound)")
    if skrs:
        print(f"mean SKR:     {sum(skrs)/len(skrs):.3f} (sound specs)")
        print(f"SKR>=0.6:     {sum(1 for s in skrs if s>=0.6)/len(skrs):.1%}")


if __name__ == "__main__":
    main()
