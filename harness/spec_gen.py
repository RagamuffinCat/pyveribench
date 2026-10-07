#!/usr/bin/env python3
"""S2 generation: ask for the contract as JSON pre/post lists, no code."""
import argparse
import json
import re
import sys
import time

from pyveri_lib import load_tasks, parse_signature
from generate import http_json, http_json_patient, detect_model

# The "Common mistakes" block is what makes this the v2 prompt (Appendix C);
# the items are the recurring failure types of 5.2.
SPEC_PROMPT = """You are given a Python programming task. Do NOT implement it.
Instead, write a FORMAL CONTRACT for it: preconditions and postconditions.

Task description:
{description}

Function signature:
{signature}

Write the contract as a JSON object in a code block:
```json
{{"pre": ["<condition>", ...], "post": ["<condition>", ...]}}
```

Rules for conditions:
- Each condition is a single Python boolean EXPRESSION (no statements).
- Preconditions may refer to the parameters: {params}.
- Postconditions may refer to the parameters and `__return__` (the return value).
- Allowed: builtins like len, sorted, set, sum, all, any, abs, max, min, range,
  comparison/arithmetic/boolean operators, comprehensions, slicing, indexing.
- NOT allowed: calling `{func_name}` itself (no self-reference), imports,
  I/O, assignments.
- The contract should be STRONG: it should pin down what the function must do
  as precisely as possible, not just trivial facts. A contract that any
  function could satisfy is worthless.
- Output ONLY the JSON code block.

Common mistakes to AVOID (these make contracts invalid or wrong):
- Natural language is NOT a condition: "xs is a list of integers" is INVALID.
  Write `all(isinstance(x, int) for x in xs)` instead.
- `__return__ is sorted` / `__return__ is list` are identity checks against
  builtin objects and are always False. Use `__return__ == sorted(__return__)`
  or `isinstance(__return__, list)`.
- `.sort()` returns None; use `sorted(...)` in expressions.
- A conditional expression needs else: `a if c else b`, never `a if c`.
- Only builtins are available: no `combinations`, no imports.
- Type checks are optional; the type hints already guarantee argument types.
"""

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


def parse_spec(raw, func_name):
    # the parse layer of S2: last ```json block, must be a dict of two string
    # lists, every condition must compile as an expression, no self-reference,
    # no imports. parse_error keeps the offending condition.
    blocks = JSON_BLOCK_RE.findall(raw)
    text = blocks[-1] if blocks else raw
    try:
        obj = json.loads(text.strip(), strict=False)
    except json.JSONDecodeError as e:
        return None, f"json: {e}"
    if not isinstance(obj, dict):
        return None, "not a dict"
    pre = obj.get("pre", [])
    post = obj.get("post", [])
    if not isinstance(pre, list) or not isinstance(post, list) \
            or not all(isinstance(x, str) for x in pre + post):
        return None, "pre/post must be lists of strings"
    for cond in pre + post:
        if func_name in cond:
            return None, f"self-reference in condition: {cond!r}"
        if re.search(r"\b(import|exec|eval|open|__import__)\b", cond):
            return None, f"banned token in condition: {cond!r}"
        try:
            compile(cond, "<cond>", "eval")
        except SyntaxError as e:
            return None, f"not an expression: {cond!r} ({e})"
    return dict(pre=pre, post=post), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://localhost:8000/v1")
    ap.add_argument("--model", default=None)
    ap.add_argument("--tasks", default="benchmark/tasks.jsonl")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--max-tokens", type=int, default=768)
    ap.add_argument("--out", default="specs.jsonl")
    ap.add_argument("--resume", action="store_true",
                    help="skip tasks already in --out")
    args = ap.parse_args()

    tasks = load_tasks(args.tasks)
    done = {}
    if args.resume:
        import os, json as _json
        if os.path.exists(args.out):
            valid = []
            with open(args.out) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = _json.loads(line)
                        valid.append(line)
                        done[r["task_id"]] = done.get(r["task_id"], 0) + 1
                    except _json.JSONDecodeError:
                        pass
            with open(args.out, "w") as f:
                f.write("\n".join(valid) + ("\n" if valid else ""))
        print(f"resume: {sum(1 for v in done.values() if v >= args.n)} tasks "
              f"already complete, skipping", file=sys.stderr)
    model = args.model or http_json_patient(
        args.endpoint.rstrip("/") + "/models")["data"][0]["id"]
    print(f"using model: {model}", file=sys.stderr)
    url = args.endpoint.rstrip("/") + "/chat/completions"
    out = open(args.out, "a" if done else "w")
    for i, t in enumerate(tasks):
        if done.get(t["task_id"], 0) >= args.n:
            continue
        func_name, sig_args = parse_signature(t["signature"])
        prompt = SPEC_PROMPT.format(description=t["description"],
                                    signature=t["signature"],
                                    params=", ".join(a for a, _ in sig_args),
                                    func_name=func_name)
        t0 = time.time()
        resp = http_json_patient(url, dict(model=model,
                                   messages=[{"role": "user", "content": prompt}],
                                   temperature=args.temperature,
                                   max_tokens=args.max_tokens, n=args.n))
        for k, ch in enumerate(resp["choices"]):
            raw = ch["message"]["content"]
            parsed, err = parse_spec(raw, func_name)
            rec = dict(task_id=t["task_id"], sample_id=k, model=model,
                       raw=raw, parsed=parsed, parse_error=err)
            out.write(json.dumps(rec) + "\n")
        out.flush()
        print(f"[{i+1}/{len(tasks)}] {t['task_id']} {t['name']}: "
              f"{args.n} specs in {time.time()-t0:.1f}s", file=sys.stderr)
    out.close()


if __name__ == "__main__":
    main()
