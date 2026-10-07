#!/usr/bin/env python3
"""Per-task markdown report from a results file. Pilot-era; nothing in the
paper is computed here."""
import argparse
import json
from collections import defaultdict

from pyveri_lib import load_tasks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="benchmark/tasks.jsonl")
    ap.add_argument("--results", default="results.jsonl")
    ap.add_argument("--completions", default="completions.jsonl")
    ap.add_argument("--out", default="analysis.md")
    args = ap.parse_args()

    tasks = {t["task_id"]: t for t in load_tasks(args.tasks)}
    with open(args.results) as f:
        res = [json.loads(l) for l in f if l.strip()]
    comps = {}
    try:
        with open(args.completions) as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    comps[(r["task_id"], r["sample_id"])] = r
    except FileNotFoundError:
        pass

    lines = []
    P = lines.append
    n = len(res)
    P("# Pilot analysis\n")
    P(f"completions: {n}\n")

    P("## Oracle agreement (tests vs CrossHair vs dynamic-contract)\n")
    combos = defaultdict(list)
    for r in res:
        key = (bool(r.get("tests_passed")),
               r["crosshair"]["status"],
               r["dynamic"]["status"])
        combos[key].append(r)
    P("| tests | crosshair | dynamic | count | share |")
    P("|---|---|---|---|---|")
    for key, rs in sorted(combos.items(), key=lambda kv: -len(kv[1])):
        P(f"| {key[0]} | {key[1]} | {key[2]} | {len(rs)} | {len(rs)/n:.1%} |")
    P("")

    silent = [r for r in res if r.get("tests_passed")
              and r["dynamic"]["status"] == "pass"
              and r["crosshair"]["status"] == "counterexample"]
    P(f"**Tests+dynamic pass but CrossHair finds cex (symbolic-only catch): "
      f"{len(silent)}**\n")
    for r in silent:
        t = tasks[r["task_id"]]
        P(f"- `{r['task_id']}#{r['sample_id']}` **{t['name']}**")
        P(f"  - cex: `{r['crosshair'].get('detail','')[:300]}`")
    P("")

    dyn_only = [r for r in res if r.get("tests_passed")
                and r["dynamic"]["status"] == "fail"]
    P(f"**Tests pass but dynamic contract fails: {len(dyn_only)}**\n")
    for r in dyn_only:
        v = r["dynamic"].get("violation", {})
        P(f"- `{r['task_id']}#{r['sample_id']}` {tasks[r['task_id']]['name']}: "
          f"args={v.get('args')} ret={v.get('ret')} cond=`{v.get('cond')}`")
    P("")

    P("## Per-task\n")
    P("| task | n | tests | CEF | cex | dyn pass | avg verify s |")
    P("|---|---|---|---|---|---|---|")
    by_task = defaultdict(list)
    for r in res:
        by_task[r["task_id"]].append(r)
    for tid in sorted(by_task):
        rs = by_task[tid]
        m = len(rs)
        P(f"| {tid} {tasks[tid]['name']} | {m} "
          f"| {sum(1 for r in rs if r.get('tests_passed'))/m:.0%} "
          f"| {sum(1 for r in rs if r['crosshair']['status']=='no_counterexample')/m:.0%} "
          f"| {sum(1 for r in rs if r['crosshair']['status']=='counterexample')/m:.0%} "
          f"| {sum(1 for r in rs if r['dynamic']['status']=='pass')/m:.0%} "
          f"| {sum(r.get('verify_seconds',0) for r in rs)/m:.1f} |")
    P("")

    P("## All verification failures (detail)\n")
    for r in res:
        bad = (not r.get("tests_passed")
               or r["crosshair"]["status"] != "no_counterexample"
               or r["dynamic"]["status"] != "pass")
        if not bad:
            continue
        t = tasks[r["task_id"]]
        P(f"### {r['task_id']}#{r['sample_id']} {t['name']}")
        P(f"- tests={r.get('tests_passed')} err=`{r.get('test_error','')}`")
        P(f"- crosshair={r['crosshair']['status']} "
          f"`{r['crosshair'].get('detail','')[:400]}`")
        v = r["dynamic"].get("violation")
        P(f"- dynamic={r['dynamic']['status']} {json.dumps(v) if v else ''}")
        c = comps.get((r["task_id"], r["sample_id"]))
        if c:
            P("\n```python")
            P(c["raw"][:1500])
            P("```")
        P("")

    text = "\n".join(lines)
    with open(args.out, "w") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
