#!/usr/bin/env python3
"""Single-point AST mutants for every task, each confirmed non-equivalent (or
not) against the reference by Hypothesis (Section 3). Output goes to
mutants.jsonl; only equivalent=false rows are ever scored."""
import argparse
import ast
import copy
import json
import subprocess
import sys

from pyveri_lib import load_tasks, parse_signature, strategy_for_param


class MutantEnumerator(ast.NodeTransformer):
    # One visitor does both jobs: with target_site=None it just counts the
    # mutation sites, with target_site=k it applies the k-th one. Sites are
    # numbered in visit order, so adding an operator changes the numbering.
    CMP_SWAP = {ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE,
                ast.GtE: ast.Gt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
                ast.In: ast.NotIn, ast.NotIn: ast.In}
    BIN_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add}

    def visit_AugAssign(self, node):
        self.generic_visit(node)
        if type(node.op) in self.BIN_SWAP:
            if self._hit():
                node.op = self.BIN_SWAP[type(node.op)]()
        return node

    def visit_FunctionDef(self, node):
        # statement deletion (never the only statement)
        self.generic_visit(node)
        if len(node.body) > 1:
            for i in range(len(node.body)):
                if self._hit():
                    node.body = list(node.body)
                    node.body[i] = ast.Pass()
        return node

    def __init__(self, target_site=None):
        self.site = -1
        self.target = target_site
        self.n_sites = 0

    def _hit(self):
        self.site += 1
        self.n_sites += 1
        return self.target is not None and self.site == self.target

    def visit_Compare(self, node):
        self.generic_visit(node)
        for i, op in enumerate(node.ops):
            if type(op) in self.CMP_SWAP:
                if self._hit():
                    node.ops = list(node.ops)
                    node.ops[i] = self.CMP_SWAP[type(op)]()
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if type(node.op) in self.BIN_SWAP:
            if self._hit():
                node.op = self.BIN_SWAP[type(node.op)]()
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        if self._hit():
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return node

    def visit_Constant(self, node):
        # constant perturbation; bool is an int subclass, skip it
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            if self._hit():
                node.value = node.value + 1
        return node

    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Name):
            swap = {"max": "min", "min": "max", "sorted": "list",
                    "abs": "int", "reversed": "iter"}
            if node.func.id in swap:
                if self._hit():
                    node.func = ast.Name(id=swap[node.func.id], ctx=ast.Load())
        return node

    def visit_Subscript(self, node):
        # index shift. This also fires inside type annotations
        # (list[int] -> list[int + 1]); those die with a TypeError at import
        # in diff_test and are stored with equivalent=None. 70 of the 493
        # rows in mutants.jsonl are that. Harmless for scoring, but it eats
        # into the per-task cap.
        self.generic_visit(node)
        if isinstance(node.slice, (ast.Name, ast.UnaryOp)):
            if self._hit():
                node.slice = ast.BinOp(left=node.slice, op=ast.Add(),
                                       right=ast.Constant(value=1))
        return node


def count_sites(code):
    e = MutantEnumerator(target_site=None)
    e.visit(ast.parse(code))
    return e.n_sites


def make_mutant(code, k):
    e = MutantEnumerator(target_site=k)
    tree = e.visit(ast.parse(code))
    return ast.unparse(ast.fix_missing_locations(tree))


DIFF_TEMPLATE = '''
import json, copy
{ref_src}
__ref = {func_name}

{mut_src_renamed}

from hypothesis import given, settings, strategies as st, HealthCheck

_witness = []

@settings(max_examples={max_examples}, deadline=None,
          suppress_health_check=list(HealthCheck))
@given(st.data())
def _diff(data):
    args = {{}}
{draw_lines}
    if not ({pre_expr}):
        return
    a1 = copy.deepcopy(args); a2 = copy.deepcopy(args)
    try:
        r1 = __ref(**a1)
    except Exception:
        return
    try:
        r2 = __mut(**a2)
    except Exception as e:
        _witness.append(dict(args=repr(args), ref=repr(r1)[:100], mut="EXC:"+repr(e)[:100]))
        raise AssertionError("mutant crashed")
    if r1 != r2:
        _witness.append(dict(args=repr(args), ref=repr(r1)[:100], mut=repr(r2)[:100]))
        raise AssertionError("outputs differ")

try:
    _diff()
    print("DIFF_RESULT " + json.dumps(dict(equivalent=True)))
except Exception:
    w = _witness[-1] if _witness else {{}}
    print("DIFF_RESULT " + json.dumps(dict(equivalent=False, witness=w)))
'''


def rename_func(code, old, new):
    tree = ast.parse(code)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == old:
            node.name = new
    return ast.unparse(tree)


def diff_test(task, mutant_code, max_examples=200, timeout=60):
    # equivalent=True: on 200 precondition-satisfying inputs the mutant
    # returned what the reference returned. False comes with a witness (a
    # differing value, or the mutant raising). Inputs on which the reference
    # itself raises are skipped.
    func_name, args = parse_signature(task["signature"])
    draw_lines = "\n".join(
        f"    args[{name!r}] = data.draw({strategy_for_param(task, name, ann)})"
        for name, ann in args)
    bind = "\n".join(f"    {name} = args[{name!r}]" for name, _ in args)
    pre_expr = " and ".join(f"({p})" for p in task["pre"]) or "True"
    prog = DIFF_TEMPLATE.format(
        ref_src=task["ref_impl"], func_name=func_name,
        mut_src_renamed=rename_func(mutant_code, func_name, "__mut"),
        max_examples=max_examples, draw_lines=draw_lines + "\n" + bind,
        pre_expr=pre_expr)
    try:
        r = subprocess.run([sys.executable, "-c", prog], capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "diff timeout"
    for line in r.stdout.splitlines():
        if line.startswith("DIFF_RESULT "):
            d = json.loads(line[len("DIFF_RESULT "):])
            return d["equivalent"], d.get("witness")
    return None, (r.stderr.strip().splitlines() or ["?"])[-1][:200]


def mutants_for_task(task, cap):
    code = task["ref_impl"]
    n = count_sites(code)
    out = []
    seen = {code.strip()}
    for k in range(n):
        try:
            m = make_mutant(code, k)
        except Exception:
            continue
        if m.strip() in seen:
            continue
        seen.add(m.strip())
        out.append(m)
        if len(out) >= cap:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="tasks.jsonl")
    ap.add_argument("--out", default="mutants.jsonl")
    ap.add_argument("--per-task", type=int, default=20)
    args = ap.parse_args()

    tasks = load_tasks(args.tasks)
    with open(args.out, "w") as f:
        for t in tasks:
            muts = mutants_for_task(t, args.per_task)
            n_noneq = 0
            for j, m in enumerate(muts):
                eq, wit = diff_test(t, m)
                rec = dict(task_id=t["task_id"], mutant_id=j, code=m,
                           equivalent=eq, witness=wit)
                if eq is False:
                    n_noneq += 1
                f.write(json.dumps(rec) + "\n")
            print(f"{t['task_id']} {t['name']:20s} sites->{len(muts):3d} mutants, "
                  f"{n_noneq} non-equivalent")


if __name__ == "__main__":
    main()
