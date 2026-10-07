#!/usr/bin/env python3
"""S3 repair loop. --mode picks the feedback condition (Section 4, Appendix C).

Input is an S1 completions file plus its results file; every sample that
failed any oracle gets up to --rounds more tries with the previous attempts
kept in the conversation.
"""
import argparse
import json
import os
import sys
import time

from pyveri_lib import (load_tasks, contract_docstring, extract_code,
                        sanitize_and_inject, parse_signature, render_prompt,
                        run_sanity_tests, run_crosshair,
                        run_dynamic_contract_test, validate_counterexample)
from generate import http_json, detect_model


def http_json_patient(url, payload=None, retry_wait=20, max_wait=7200):
    t0 = time.time()
    while True:
        try:
            return http_json(url, payload)
        except Exception as e:
            if time.time() - t0 > max_wait:
                raise
            print(f"server unreachable ({type(e).__name__}), retrying in "
                  f"{retry_wait}s", file=sys.stderr)
            time.sleep(retry_wait)


def verify_module(task, module_src, ch_timeout=10):
    # same three oracles as verify.py; a replay-refuted counterexample is
    # treated as no counterexample so the model is never fed a spurious one
    ok, msg = run_sanity_tests(module_src, task["tests"])
    ch = run_crosshair(module_src, per_condition_timeout=ch_timeout)
    if ch["status"] == "counterexample":
        val = validate_counterexample(module_src, task, ch.get("detail", ""))
        ch["validated"] = val["status"]
        ch["replays"] = val["replays"]
        if val["status"] == "spurious":
            ch["status"] = "no_counterexample"
            # feedback_message keys on detail, so clear it too. The logged
            # runs predate this line; by the S1 verdicts it would have
            # mattered once (1.5B pv_047#0, round 1), see README.
            ch["spurious_detail"] = ch.get("detail", "")
            ch["detail"] = ""
    dyn = run_dynamic_contract_test(module_src, task)
    verified = ok and ch["status"] == "no_counterexample" and dyn["status"] == "pass"
    return verified, dict(tests_passed=ok, test_error=msg,
                          crosshair=ch, dynamic=dyn)


def feedback_message(mode, task, vres):
    # binary < test < cex in what they reveal; none of them shows reference
    # output. Verbatim skeletons are in Appendix C.
    if mode == "binary":
        return ("Verification FAILED: your implementation violates the formal "
                "contract. Please fix your implementation. Output ONLY the "
                "corrected function in a single Python code block.")
    if mode == "cex":
        # CrossHair's line gives the call and the return value (or the
        # exception) but NOT the condition: 0.0.110 prints "error: false"
        # plus a path:line into the temp file. Left exactly as the logged
        # runs had it. Fallbacks: Hypothesis witness, then the test error.
        det = vres["crosshair"].get("detail", "")
        if det:
            body = f"CrossHair found a concrete counterexample:\n{det}"
        elif vres["dynamic"].get("violation"):
            v = vres["dynamic"]["violation"]
            body = (f"A contract violation was found. Input: {v.get('args')} "
                    f"Return: {v.get('ret')} Violated condition: {v.get('cond')}")
        else:
            body = f"A test failed: {vres.get('test_error', 'unknown')}"
        return (f"Verification FAILED. {body}\n"
                "Please fix your implementation so the contract holds for ALL "
                "valid inputs. Output ONLY the corrected function in a single "
                "Python code block.")
    if mode == "test":
        # never leaks anything the symbolic layer found: if only CrossHair
        # failed, the model just hears that a hidden test failed
        if not vres["tests_passed"]:
            body = f"A test failed: {vres.get('test_error', 'unknown')}"
        elif vres["dynamic"].get("violation"):
            v = vres["dynamic"]["violation"]
            body = (f"A randomized test failed. Input: {v.get('args')} "
                    f"Return: {v.get('ret')}")
        else:
            body = "A hidden test failed."
        return (f"Verification FAILED. {body}\n"
                "Please fix your implementation. Output ONLY the corrected "
                "function in a single Python code block.")
    raise ValueError(mode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://localhost:8000/v1")
    ap.add_argument("--model", default=None)
    ap.add_argument("--tasks", default="benchmark/tasks.jsonl")
    ap.add_argument("--completions", default="completions.jsonl")
    ap.add_argument("--results", default="results.jsonl")
    ap.add_argument("--mode", choices=["binary", "test", "cex"], required=True)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--out", required=True)
    ap.add_argument("--must-change", action="store_true",
                    help="append the must-differ instruction")
    ap.add_argument("--resume", action="store_true",
                    help="skip samples already in --out")
    args = ap.parse_args()

    tasks = {t["task_id"]: t for t in load_tasks(args.tasks)}
    with open(args.completions) as f:
        comps = {}
        for line in f:
            if line.strip():
                r = json.loads(line)
                comps[(r["task_id"], r["sample_id"])] = r
    with open(args.results) as f:
        # failure pool: anything that failed any oracle in S1. A spurious
        # counterexample on its own does not put a sample in the pool.
        fails = []
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            ch = r["crosshair"]
            cex_real = (ch["status"] == "counterexample"
                        and ch.get("validated", "confirmed") != "spurious")
            failed = (not r.get("tests_passed")
                      or cex_real
                      or r["dynamic"]["status"] == "fail"
                      or not r.get("syntax_ok"))
            if failed:
                fails.append(r)
    print(f"repairing {len(fails)} failed completions, mode={args.mode}",
          file=sys.stderr)

    done = set()
    if args.resume and os.path.exists(args.out):
        valid = []
        with open(args.out) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    valid.append(line)
                    done.add((r["task_id"], r["sample_id"]))
                except json.JSONDecodeError:
                    pass
        with open(args.out, "w") as f:
            f.write("\n".join(valid) + ("\n" if valid else ""))
        print(f"resume: {len(done)} samples already done, skipping",
              file=sys.stderr)

    if args.model:
        model = args.model
    else:
        models = http_json_patient(args.endpoint.rstrip("/") + "/models")
        model = models["data"][0]["id"]
    url = args.endpoint.rstrip("/") + "/chat/completions"
    out = open(args.out, "a" if done else "w")

    for i, res in enumerate(fails):
        if (res["task_id"], res["sample_id"]) in done:
            continue
        task = tasks[res["task_id"]]
        comp = comps[(res["task_id"], res["sample_id"])]
        fn, _ = parse_signature(task["signature"])
        messages = [
            {"role": "user", "content": render_prompt(task)},
            {"role": "assistant", "content": comp["raw"]},
        ]
        try:
            src = sanitize_and_inject(extract_code(comp["raw"]), fn,
                                      contract_docstring(task))
            verified, vres = verify_module(task, src)
        except Exception as e:
            verified, vres = False, dict(tests_passed=False,
                                         test_error=f"syntax: {e}",
                                         crosshair=dict(status="not_run"),
                                         dynamic=dict(status="not_run"))
        pre_repair = dict(verified=verified, tests=vres["tests_passed"],
                          crosshair=vres["crosshair"]["status"],
                          dynamic=vres["dynamic"]["status"])
        trail = []
        rnd = 0
        while not verified and rnd < args.rounds:
            rnd += 1
            fb = feedback_message(args.mode, task, vres)
            if args.must_change:
                # the must-differ ablation (5.3)
                fb += ("\nIMPORTANT: your revision MUST be different from your "
                       "previous attempt. Do NOT resubmit the same code.")
            messages.append({"role": "user", "content": fb})
            t0 = time.time()
            resp = http_json_patient(url, dict(model=model, messages=messages,
                                               temperature=args.temperature,
                                               max_tokens=args.max_tokens))
            raw = resp["choices"][0]["message"]["content"]
            # no_change: code block identical to any earlier attempt, including
            # the S1 one. This is the "verbatim resubmission" count in 5.3.
            no_change = any(extract_code(raw).strip() ==
                            extract_code(m["content"]).strip()
                            for m in messages if m["role"] == "assistant")
            messages.append({"role": "assistant", "content": raw})
            try:
                src = sanitize_and_inject(extract_code(raw), fn,
                                          contract_docstring(task))
                verified, vres = verify_module(task, src)
            except Exception as e:
                verified, vres = False, dict(tests_passed=False,
                                             test_error=f"syntax: {e}",
                                             crosshair=dict(status="not_run"),
                                             dynamic=dict(status="not_run"))
            # feedback = the exact message the model got this round; the
            # shipped logs were written before this field existed
            trail.append(dict(round=rnd, verified=verified, no_change=no_change,
                              crosshair=vres["crosshair"]["status"],
                              dynamic=vres["dynamic"]["status"],
                              tests=vres["tests_passed"],
                              gen_seconds=round(time.time() - t0, 1),
                              feedback=fb, raw=raw))
        rec = dict(task_id=res["task_id"], sample_id=res["sample_id"],
                   mode=args.mode, rounds_used=rnd, final_verified=verified,
                   pre_repair=pre_repair, trail=trail)
        out.write(json.dumps(rec) + "\n")
        out.flush()
        print(f"[{i+1}/{len(fails)}] {res['task_id']}#{res['sample_id']} "
              f"-> {'VERIFIED' if verified else 'still failing'} "
              f"after {rnd} round(s)", file=sys.stderr)
    out.close()


if __name__ == "__main__":
    main()
