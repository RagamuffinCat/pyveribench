#!/usr/bin/env python3
"""Salvage pass for DeepSeek (5.1): its replies often indent the whole fence
or trail off into demo code. Dedent, then drop lines from the end until the
block parses, and verify that. usage: completions results out
"""
import ast, json, re, sys, textwrap, time
from concurrent.futures import ProcessPoolExecutor
from pyveri_lib import (load_tasks, contract_docstring, sanitize_and_inject,
                        parse_signature, run_sanity_tests, run_crosshair,
                        run_dynamic_contract_test, validate_counterexample)

FENCE = re.compile(r"```(?:python)?\s*\n?(.*?)```", re.S)

def salvage_extract(raw):
    m = FENCE.findall(raw)
    code = m[0] if m else raw
    code = textwrap.dedent(code)
    lines = code.split("\n")
    while lines:
        try:
            ast.parse("\n".join(lines))
            return "\n".join(lines)
        except SyntaxError:
            lines.pop()
    raise SyntaxError("unsalvageable")

def verify_one(job):
    task, rec = job
    res = dict(task_id=rec["task_id"], sample_id=rec["sample_id"],
               model=rec.get("model","?"), salvaged=True)
    t0 = time.time()
    fn, _ = parse_signature(task["signature"])
    try:
        src = sanitize_and_inject(salvage_extract(rec["raw"]), fn,
                                  contract_docstring(task))
        res["syntax_ok"] = True
    except Exception as e:
        res.update(syntax_ok=False, error=str(e)[:200], tests_passed=False,
                   crosshair=dict(status="not_run"),
                   dynamic=dict(status="not_run"),
                   verify_seconds=round(time.time()-t0,1))
        return res
    ok, msg = run_sanity_tests(src, task["tests"])
    res["tests_passed"] = ok
    res["crosshair"] = run_crosshair(src, per_condition_timeout=10)
    if res["crosshair"]["status"] == "counterexample":
        val = validate_counterexample(src, task, res["crosshair"].get("detail",""))
        res["crosshair"]["validated"] = val["status"]
    res["dynamic"] = run_dynamic_contract_test(src, task)
    res["verify_seconds"] = round(time.time()-t0,1)
    return res

def main():
    tasks = {t["task_id"]: t for t in load_tasks("benchmark/tasks.jsonl")}
    comps = {(r["task_id"],r["sample_id"]): r
             for r in (json.loads(l) for l in open(sys.argv[1]))}
    failed = [json.loads(l) for l in open(sys.argv[2])]
    failed = [r for r in failed if not r.get("syntax_ok")]
    print(f"salvaging {len(failed)} syntax-failed samples", file=sys.stderr)
    jobs = [(tasks[r["task_id"]], comps[(r["task_id"],r["sample_id"])]) for r in failed]
    with open(sys.argv[3],"w") as out, ProcessPoolExecutor(max_workers=10) as ex:
        for i, res in enumerate(ex.map(verify_one, jobs)):
            out.write(json.dumps(res)+"\n"); out.flush()
            print(f"[{i+1}/{len(jobs)}] {res['task_id']}#{res['sample_id']} "
                  f"syn={res['syntax_ok']} tests={res.get('tests_passed')}",
                  file=sys.stderr)

if __name__ == "__main__":
    main()
