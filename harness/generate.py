#!/usr/bin/env python3
"""S1 generation against an OpenAI-compatible server (vLLM, see README)."""
import argparse
import json
import sys
import time
import urllib.request

from pyveri_lib import load_tasks, render_prompt


def http_json(url, payload=None, timeout=600):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def http_json_patient(url, payload=None, retry_wait=20, max_wait=7200):
    # wait out a dead or restarting server instead of losing the run (2 h max)
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


def detect_model(endpoint):
    models = http_json(endpoint.rstrip("/") + "/models")
    return models["data"][0]["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://localhost:8000/v1")
    ap.add_argument("--model", default=None, help="default: auto-detect")
    ap.add_argument("--tasks", default="benchmark/tasks.jsonl")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--out", default="completions.jsonl")
    ap.add_argument("--mock", choices=["ref", "buggy"], default=None,
                    help="write reference or corrupted code, no server")
    ap.add_argument("--resume", action="store_true",
                    help="skip tasks already in --out")
    args = ap.parse_args()

    tasks = load_tasks(args.tasks)
    done = {}
    if args.resume:
        # drop any half-written line, count samples per task, append
        import os
        if os.path.exists(args.out):
            valid = []
            with open(args.out) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                        valid.append(line)
                        done[r["task_id"]] = done.get(r["task_id"], 0) + 1
                    except json.JSONDecodeError:
                        pass
            with open(args.out, "w") as f:
                f.write("\n".join(valid) + ("\n" if valid else ""))
        print(f"resume: {sum(1 for v in done.values() if v >= args.n)} tasks "
              f"already complete, skipping", file=sys.stderr)
    out = open(args.out, "a" if done else "w")

    if args.mock:
        # smoke-test the verifier without a model: reference code, or the
        # reference with one crude edit that should fail
        for t in tasks:
            code = t["ref_impl"]
            if args.mock == "buggy":
                head, _, body = code.partition("\n")
                for a, b in [("<=", "<"), ("<", "<="), (">=", ">"), (">", ">="),
                             ("max(", "min("), ("min(", "max("), ("+=", "-="),
                             ("+ 1", ""), ("- 1", ""), ("abs(", "-abs("),
                             ("set(", "list("), ("sorted(", "list("),
                             ("% 2 == 0", "% 2 == 1"), ("reversed(", "iter(")]:
                    if a in body:
                        body = body.replace(a, b, 1)
                        break
                code = head + "\n" + body
            for k in range(args.n):
                rec = dict(task_id=t["task_id"], sample_id=k, model="mock-" + args.mock,
                           raw=f"```python\n{code}\n```", gen_seconds=0.0)
                out.write(json.dumps(rec) + "\n")
        out.close()
        print(f"mock completions written to {args.out}")
        return

    model = args.model or http_json_patient(
        args.endpoint.rstrip("/") + "/models")["data"][0]["id"]
    print(f"using model: {model}", file=sys.stderr)
    url = args.endpoint.rstrip("/") + "/chat/completions"
    t_all = time.time()
    for i, t in enumerate(tasks):
        if done.get(t["task_id"], 0) >= args.n:
            continue
        prompt = render_prompt(t)
        t0 = time.time()
        resp = http_json_patient(url, dict(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            n=args.n,
        ))
        dt = time.time() - t0
        for k, choice in enumerate(resp["choices"]):
            # gen_seconds is the request time split evenly over the n samples
            rec = dict(task_id=t["task_id"], sample_id=k, model=model,
                       raw=choice["message"]["content"],
                       gen_seconds=round(dt / len(resp["choices"]), 2))
            out.write(json.dumps(rec) + "\n")
        out.flush()
        print(f"[{i+1}/{len(tasks)}] {t['task_id']} {t['name']}: "
              f"{len(resp['choices'])} samples in {dt:.1f}s", file=sys.stderr)
    out.close()
    print(f"done in {time.time()-t_all:.0f}s -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
