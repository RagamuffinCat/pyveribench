#!/usr/bin/env python3
"""Recomputes the numbers in the paper from logs/. Needs scipy for the
Wilcoxon line; everything else is stdlib. Section markers below say which
table or paragraph each block feeds."""
import argparse
import glob
import json
import os
from math import comb

MODELS = ["1p5b", "3b", "7b"]


def load(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


# regression_s3.jsonl (regression_replay.py) overrides final_verified; in the
# shipped logs that flips the four binary/1.5B strip_vowels entries of 5.3
REGRESSION = {}


def load_regression(L):
    path = os.path.join(L, "regression_s3.jsonl")
    if not os.path.exists(path):
        return
    for r in load(path):
        REGRESSION[(r["mode"], r["model"], r["task_id"], r["sample_id"])] = r


def repaired(r, cond, m):
    if REGRESSION:
        return REGRESSION[(cond, m, r["task_id"], r["sample_id"])]["repaired"]
    return r["final_verified"]


def cef_validated(r):
    # CEF (validated) as in Table 1: parses, no confirmed counterexample,
    # dynamic oracle passes. A spurious counterexample does not count.
    ch = r["crosshair"]
    cex_real = (ch["status"] == "counterexample"
                and ch.get("validated", "confirmed") != "spurious")
    return (r.get("syntax_ok") and not cex_real
            and r["dynamic"]["status"] == "pass")


def mcnemar_exact(b, c):
    # exact binomial McNemar on the discordant pairs, two-sided
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default="logs")
    args = ap.parse_args()
    L = args.logs

    # Table 1
    print("== S1: code generation (CEF-validated @1, 295 completions/model) ==")
    for m in MODELS:
        rs = load(os.path.join(L, f"results_{m}.jsonl"))
        ok = sum(cef_validated(r) for r in rs)
        spur = sum(1 for r in rs if r["crosshair"].get("validated") == "spurious")
        print(f"  {m:>4}: CEF-validated {ok}/{len(rs)} = {ok/len(rs):.1%}   "
              f"spurious (replay-refuted) {spur}/{len(rs)} = {spur/len(rs):.1%}")

    # Table 2, last column
    print("\n== S2: specification generation (good = parsed & sound & SKR>=0.6) ==")
    for m in MODELS:
        rs = load(os.path.join(L, f"spec_results_{m}.jsonl"))
        good = sum(1 for r in rs
                   if r.get("parse_ok") and r.get("sound")
                   and (r.get("skr") or 0) >= 0.6)
        print(f"  {m:>4}: good-spec {good}/{len(rs)} = {good/len(rs):.1%}")

    load_regression(L)
    if REGRESSION:
        flips = [k for k, v in REGRESSION.items()
                 if v["final_verified"] and not v["repaired"]]
        print("\n== S3: regression replay of S1 failure evidence "
              "(regression_replay.py) ==")
        print(f"  declared repairs that still violate the original "
              f"counterexample: {len(flips)}")
        for k in sorted(flips):
            print(f"    {k[0]}/{k[1]} {k[2]}#{k[3]}")
        tag = "regression-gated"
    else:
        tag = "final_verified"
    # Table 3
    print(f"\n== S3: counterexample-guided repair ({tag}, per condition) ==")
    pooled = {}
    for cond in ["cex", "test", "binary"]:
        tot = ok = 0
        cells = []
        for m in MODELS:
            rs = load(os.path.join(L, f"repair_{cond}_{m}.jsonl"))
            v = sum(repaired(r, cond, m) for r in rs)
            cells.append(f"{m} {v}/{len(rs)}={v/len(rs):.1%}")
            tot += len(rs)
            ok += v
            pooled.setdefault(cond, {}).update(
                {(r["task_id"], r["sample_id"], m): repaired(r, cond, m)
                 for r in rs})
        print(f"  {cond:>6}: {ok}/{tot} = {ok/tot:.1%}   [" + ", ".join(cells) + "]")

    # The three views of 5.3: McNemar on completions, Wilcoxon on per-task
    # rates, and a sign-flip permutation with tasks as the clusters (samples
    # of one task are not independent; add_big_digits alone is 14 of 98).
    import random
    random.seed(0)
    bytask = {}
    for k in pooled["cex"]:
        bytask.setdefault(k[0], []).append(k)
    for x, y in [("cex", "binary"), ("cex", "test"), ("test", "binary")]:
        b = sum(1 for k, v in pooled[x].items() if v and not pooled[y].get(k))
        c = sum(1 for k, v in pooled[x].items() if not v and pooled[y].get(k))
        diffs = []
        for t, ks in bytask.items():
            rx = sum(pooled[x][k] for k in ks) / len(ks)
            ry = sum(pooled[y][k] for k in ks) / len(ks)
            diffs.append(rx - ry)
        try:
            from scipy.stats import wilcoxon
            _, pw = wilcoxon(diffs, zero_method="wilcox")
            pw = f"{pw:.3f}"
        except Exception:
            pw = "scipy required"
        obs = sum(pooled[x].values()) - sum(pooled[y].values())
        cnt = 0
        iters = 20000
        for _ in range(iters):
            sdiff = 0
            for t, ks in bytask.items():
                sgn = -1 if random.random() < 0.5 else 1
                sdiff += sgn * (sum(pooled[x][k] for k in ks)
                                - sum(pooled[y][k] for k in ks))
            if abs(sdiff) >= abs(obs):
                cnt += 1
        print(f"  {x} vs {y}: McNemar {b}v{c} p={mcnemar_exact(b, c):.3f} | "
              f"task-level Wilcoxon (n={len(bytask)}) p={pw} | "
              f"task-clustered permutation p={cnt/iters:.3f}")

    # symbolic-only failures: tests and Hypothesis pass, only CrossHair fails.
    # In the test condition these samples only hear "a hidden test failed".
    symonly = set()
    for m in MODELS:
        for r in load(os.path.join(L, f"results_{m}.jsonl")):
            ch = r["crosshair"]
            if (r.get("tests_passed") and r["dynamic"]["status"] == "pass"
                    and ch["status"] == "counterexample"
                    and ch.get("validated") == "confirmed"):
                symonly.add((r["task_id"], r["sample_id"], m))
    print(f"  symbolic-only failures in pool: {len(symonly)}")
    for x, y in [("cex", "test"), ("cex", "binary"), ("test", "binary")]:
        for label, keys in [("symbolic-only", symonly),
                            ("rest", set(pooled[x]) - symonly)]:
            b = sum(1 for k in keys if pooled[x][k] and not pooled[y][k])
            c = sum(1 for k in keys if not pooled[x][k] and pooled[y][k])
            print(f"    {x} vs {y} on {label} (n={len(keys)}): "
                  f"{b}v{c} p={mcnemar_exact(b, c):.3f}")

    # failure-type strata (5.3). Crude classifier over the error text: a
    # NameError is a missing import, other exception names are runtime, the
    # rest is "semantic".
    print("\n== S3: repair success by S1 failure type (pooled attempts) ==")

    def failure_type(r):
        if not r.get("syntax_ok"):
            return "syntax"
        blob = (str(r.get("test_error") or "")
                + str(r["dynamic"].get("violation") or "")
                + str(r["dynamic"].get("error") or "")
                + str(r["crosshair"].get("detail") or ""))
        if "NameError" in blob or "is not defined" in blob:
            return "missing-import"
        for exc in ["TypeError", "IndexError", "ValueError",
                    "ZeroDivisionError", "KeyError", "AttributeError",
                    "RecursionError", "OverflowError", "UnboundLocalError"]:
            if exc in blob:
                return "runtime-exception"
        return "semantic"

    strata = {}
    for m in MODELS:
        res = {(r["task_id"], r["sample_id"]): r
               for r in load(os.path.join(L, f"results_{m}.jsonl"))}
        per_cond = {c: {(r["task_id"], r["sample_id"]): r
                        for r in load(os.path.join(L, f"repair_{c}_{m}.jsonl"))}
                    for c in ["cex", "test", "binary"]}
        for k in per_cond["cex"]:
            ft = failure_type(res[k])
            for c in ["cex", "test", "binary"]:
                a = strata.setdefault(ft, [0, 0])
                a[0] += repaired(per_cond[c][k], c, m)
                a[1] += 1
    for ft, (ok, tot) in sorted(strata.items()):
        print(f"  {ft:>17}: {ok}/{tot} = {ok/tot:.1%} ({tot//3} samples)")

    # verbatim resubmission (5.3), from the no_change flag repair.py records
    print("\n== S3: verbatim resubmission (byte-identical, all repair rounds) ==")
    rates = []
    nover = 0
    for cond in ["cex", "test", "binary"]:
        for m in MODELS:
            rs = load(os.path.join(L, f"repair_{cond}_{m}.jsonl"))
            tot = nc = 0
            for r in rs:
                for t in r["trail"]:
                    tot += 1
                    nc += bool(t.get("no_change"))
                    nover += bool(t.get("no_change")) and t["verified"]
            if tot:
                rates.append((nc / tot, cond, m))
    lo, hi = min(rates), max(rates)
    print(f"  range across model x condition: {lo[0]:.0%} ({lo[1]}/{lo[2]}) "
          f"to {hi[0]:.0%} ({hi[1]}/{hi[2]})")
    print(f"  byte-identical resubmissions that verified: {nover}")

    # must-differ ablation (5.3). The Fisher p in the paper is a 2x2 test on
    # the two resubmission counts printed here (134/196 vs 121/188).
    print("\n== S3 ablation: explicit 'must differ' instruction (1.5B, cex) ==")
    base = {(r["task_id"], r["sample_id"]): r
            for r in load(os.path.join(L, "repair_cex_1p5b.jsonl"))}
    abl = {(r["task_id"], r["sample_id"]): r
           for r in load(os.path.join(L, "repair_cex_1p5b_mustchange.jsonl"))}
    for name, rs, cond in [("baseline", base, "cex"),
                           ("must-change", abl, "cex_mustchange")]:
        ok = sum(repaired(r, cond, "1p5b") for r in rs.values())
        tot = nc = 0
        for r in rs.values():
            for t in r["trail"]:
                tot += 1
                nc += bool(t.get("no_change"))
        print(f"  {name:>11}: repaired {ok}/{len(rs)} = {ok/len(rs):.1%}, "
              f"resubmission {nc}/{tot} = {nc/tot:.1%} of rounds")
    b = sum(1 for k in abl if repaired(base[k], "cex", "1p5b")
            and not repaired(abl[k], "cex_mustchange", "1p5b"))
    c = sum(1 for k in abl if not repaired(base[k], "cex", "1p5b")
            and repaired(abl[k], "cex_mustchange", "1p5b"))
    print(f"  paired: discordant {b} vs {c}, McNemar exact "
          f"p={mcnemar_exact(b, c):.3f}")


if __name__ == "__main__":
    main()
