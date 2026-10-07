"""Shared bits: prompt, code extraction, the three oracles, counterexample replay.

Everything runs the candidate in a subprocess and talks back through a
sentinel line (TESTS_OK / REPLAY_RESULT / DYNTEST_RESULT), so a candidate
that hangs or segfaults only kills that one check.
"""
import ast
import json
import re
import subprocess
import sys
import tempfile
import os


def load_tasks(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def contract_docstring(task):
    # PEP 316 body: one "pre:"/"post:" line per condition, CrossHair reads these
    lines = []
    for p in task["pre"]:
        lines.append(f"pre: {p}")
    for p in task["post"]:
        lines.append(f"post: {p}")
    return "\n    ".join(lines)


def render_prompt(task):
    # S1 prompt (Appendix C). The contract is shown verbatim.
    ds = contract_docstring(task)
    return f"""You are given a Python programming task.

Task description:
{task['description']}

Required function signature (use it EXACTLY as given, with these type hints):
{task['signature']}

The implementation must satisfy this formal contract (CrossHair PEP-316 style;
`pre:` are preconditions on the arguments, `post:` are postconditions where
`__return__` denotes the return value):
    {ds}

Rules:
- Output ONLY a single Python code block with the complete function definition.
- Use only the Python standard library. No I/O, no printing, no randomness.
- The function must be deterministic and must not modify its arguments.
"""


CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def extract_code(text):
    # last fenced block; no fence at all -> treat the whole reply as code
    blocks = CODE_BLOCK_RE.findall(text)
    if blocks:
        return blocks[-1]
    return text


def sanitize_and_inject(code, func_name, docstring):
    # Keep imports/defs/classes only (drops demo calls and prints at module
    # level), then replace the target function's docstring with the reference
    # contract. Whatever docstring the model wrote is thrown away, so CrossHair
    # always checks our contract and never the model's own pre/post lines.
    tree = ast.parse(code)
    kept = []
    target = None
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            kept.append(node)
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                target = node
    if target is None:
        raise ValueError(f"function {func_name!r} not found in completion")
    ds_node = ast.Expr(value=ast.Constant(value="\n    " + docstring + "\n    "))
    body = target.body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    target.body = [ds_node] + body
    module = ast.Module(body=kept, type_ignores=[])
    # typing.* up front so List[int]-style hints resolve whatever the model imported
    return "from typing import *\n\n" + ast.unparse(ast.fix_missing_locations(module)) + "\n"


def run_sanity_tests(module_src, tests, timeout=10):
    # tests are plain assert lines from tasks.jsonl
    prog = module_src + "\n\n" + "\n".join(tests) + "\nprint('TESTS_OK')\n"
    try:
        r = subprocess.run([sys.executable, "-c", prog], capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "test timeout"
    if "TESTS_OK" in r.stdout:
        return True, ""
    return False, (r.stderr.strip().splitlines() or ["unknown failure"])[-1][:300]


def run_crosshair(module_src, per_condition_timeout=10, extra_timeout=30):
    # 10 s per condition in the study, 8 s in the quality gates. The subprocess
    # limit is budget x #conditions + slack; hitting *that* is "harness_timeout",
    # which is a different thing from CrossHair running out of its own budget
    # (that one returns 0 and shows up as no_counterexample). Under parallel
    # load the harness limit can get hit, see README.
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "candidate.py")
        with open(path, "w") as f:
            f.write(module_src)
        n_conditions = module_src.count("post:") + module_src.count("pre:")
        budget = per_condition_timeout * max(1, n_conditions) + extra_timeout
        try:
            r = subprocess.run(
                ["crosshair", "check", path, "--analysis_kind=PEP316",
                 f"--per_condition_timeout={per_condition_timeout}"],
                capture_output=True, text=True, timeout=budget)
        except subprocess.TimeoutExpired:
            return dict(status="harness_timeout", detail="")
    out = (r.stdout + "\n" + r.stderr).strip()
    if r.returncode == 0:
        return dict(status="no_counterexample", detail="")
    # one "path:line: error: <cond> when calling f(...) (which returns ...)" per hit
    if ": error:" in out and "when calling" in out:
        lines = [l for l in out.splitlines() if ": error:" in l]
        return dict(status="counterexample", detail="\n".join(lines)[:1000])
    return dict(status="crosshair_error", detail=out[:1000])


CEX_RE = re.compile(
    r"error: (?P<err>.+?) when calling (?P<call>.+?)(?: \(which returns .+\))?\s*$")

# Replay (Section 3). Parse the call CrossHair printed, literal_eval the
# arguments, run the candidate for real and re-check every postcondition.
# "spurious" means the executor's report does not reproduce in CPython;
# in this study that was always the negative-index / negative-step slice
# modeling bug (Section 6).
REPLAY_TEMPLATE = '''
import json, copy, ast as _ast
{module_src}

_call = _ast.parse({call_src!r}, mode="eval").body
_vals = [_ast.literal_eval(a) for a in _call.args]
_params = {params!r}
args = dict(zip(_params, _vals))
for _kw in _call.keywords:
    args[_kw.arg] = _ast.literal_eval(_kw.value)
_g = dict(globals()); _g.update(args)
_pre_ok = all(eval(p, dict(_g)) for p in {pre_list!r})
if not _pre_ok:
    print("REPLAY_RESULT " + json.dumps(dict(status="spurious",
                                             reason="input violates precondition")))
else:
    frozen = copy.deepcopy(args)
    try:
        __return__ = {func_name}(**args)
    except Exception as e:
        print("REPLAY_RESULT " + json.dumps(dict(status="confirmed",
                                                 reason="raises " + repr(e)[:200])))
    else:
        ns = dict(globals()); ns.update(frozen); ns["__return__"] = __return__
        _viol = None
        for cond in {post_list!r}:
            try:
                if not eval(cond, dict(ns)):
                    _viol = cond
                    break
            except Exception as e:
                _viol = cond + "  (eval error: " + repr(e)[:100] + ")"
                break
        if _viol:
            print("REPLAY_RESULT " + json.dumps(dict(status="confirmed",
                reason="violates: " + _viol, ret=repr(__return__)[:200])))
        else:
            print("REPLAY_RESULT " + json.dumps(dict(status="spurious",
                reason="all postconditions hold on replay",
                ret=repr(__return__)[:200])))
'''


def validate_counterexample(module_src, task, detail, timeout=20):
    func_name, sig_args = parse_signature(task["signature"])
    params = [a for a, _ in sig_args]
    replays = []
    for line in detail.splitlines():
        m = CEX_RE.search(line)
        if not m:
            continue
        call_src = m.group("call")
        prog = REPLAY_TEMPLATE.format(
            module_src=module_src, call_src=call_src, params=params,
            pre_list=task["pre"], post_list=task["post"], func_name=func_name)
        try:
            r = subprocess.run([sys.executable, "-c", prog],
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            replays.append(dict(call=call_src, status="unknown",
                                reason="replay timeout"))
            continue
        parsed = None
        for out_line in r.stdout.splitlines():
            if out_line.startswith("REPLAY_RESULT "):
                parsed = json.loads(out_line[len("REPLAY_RESULT "):])
        if parsed is None:
            parsed = dict(status="unknown",
                          reason=(r.stderr.strip().splitlines() or ["?"])[-1][:200])
        parsed["call"] = call_src
        replays.append(parsed)
    # one confirmed replay is enough to count against the model; a report is
    # only called spurious when every replay says so
    if any(x["status"] == "confirmed" for x in replays):
        status = "confirmed"
    elif replays and all(x["status"] == "spurious" for x in replays):
        status = "spurious"
    else:
        status = "unknown"
    return dict(status=status, replays=replays)


# Hypothesis oracle. derandomize=True went in after the study runs; the logs
# in logs/ are unseeded (README), which is where the handful of flips in 5.1
# and 5.3 came from.
DYNAMIC_TEST_TEMPLATE = '''
import sys, json
{module_src}

from hypothesis import given, settings, strategies as st, HealthCheck
import hypothesis.errors

_violations = []

@settings(max_examples={max_examples}, deadline=None, derandomize=True,
          suppress_health_check=list(HealthCheck))
@given(st.data())
def _contract_test(data):
    import copy
    args = {{}}
{draw_lines}
    if not ({pre_expr}):
        return
    frozen = copy.deepcopy(args)
    try:
        __return__ = {func_name}(**args)
    except Exception as e:
        _violations.append(dict(kind="exception", args=repr(frozen), err=repr(e)[:200]))
        raise AssertionError("exception")
    ns = dict(frozen)
    ns["__return__"] = __return__
    _g = dict(globals()); _g.update(ns)
    for cond in {post_list!r}:
        try:
            ok = eval(cond, _g)
        except Exception as e:
            _violations.append(dict(kind="post_eval_error", cond=cond, args=repr(frozen), err=repr(e)[:200]))
            raise AssertionError("post eval error")
        if not ok:
            _violations.append(dict(kind="post_violation", cond=cond, args=repr(frozen), ret=repr(__return__)[:200]))
            raise AssertionError("post violation")

try:
    _contract_test()
    print("DYNTEST_RESULT " + json.dumps(dict(status="pass")))
except Exception:
    v = _violations[-1] if _violations else dict(kind="unknown")
    print("DYNTEST_RESULT " + json.dumps(dict(status="fail", violation=v)))
'''


def _strategy_for(annotation):
    # default input domains (Appendix B); tasks override per parameter with
    # a "strategies" dict in tasks.jsonl. The ranges are small; CrossHair is
    # the layer that goes outside them (5.1).
    a = annotation.replace(" ", "")
    table = {
        "int": "st.integers(min_value=-50, max_value=50)",
        "bool": "st.booleans()",
        "str": "st.text(alphabet='abcxyz', max_size=6)",
        "list[int]": "st.lists(st.integers(min_value=-50, max_value=50), max_size=8)",
        "list[str]": "st.lists(st.text(alphabet='abc', max_size=4), max_size=6)",
    }
    if a not in table:
        raise ValueError(f"no strategy for annotation {annotation!r}")
    return table[a]


def strategy_for_param(task, name, annotation):
    ov = (task.get("strategies") or {}).get(name)
    return ov or _strategy_for(annotation)


def parse_signature(signature):
    node = ast.parse(signature.rstrip(": \n") + ":\n    pass").body[0]
    args = [(a.arg, ast.unparse(a.annotation)) for a in node.args.args]
    return node.name, args


def run_dynamic_contract_test(module_src, task, max_examples=150, timeout=90):
    # 150 examples in S1/S3 verification; QA, S2 scoring and the differential
    # audit pass 200
    func_name, args = parse_signature(task["signature"])
    draw_lines = "\n".join(
        f"    args[{name!r}] = data.draw({strategy_for_param(task, name, ann)})"
        for name, ann in args)
    pre_expr = " and ".join(f"({p})" for p in task["pre"]) or "True"
    bind = "\n".join(f"    {name} = args[{name!r}]" for name, _ in args)
    draw_lines = draw_lines + "\n" + bind
    prog = DYNAMIC_TEST_TEMPLATE.format(
        module_src=module_src, max_examples=max_examples,
        draw_lines=draw_lines, pre_expr=pre_expr,
        func_name=func_name, post_list=task["post"])
    try:
        r = subprocess.run([sys.executable, "-c", prog], capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return dict(status="dyn_timeout")
    for line in r.stdout.splitlines():
        if line.startswith("DYNTEST_RESULT "):
            return json.loads(line[len("DYNTEST_RESULT "):])
    return dict(status="dyn_error",
                detail=(r.stderr.strip().splitlines() or [""])[-1][:300])
