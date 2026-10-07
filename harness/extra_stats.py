#!/usr/bin/env python3
"""The numbers in the paper that paper_stats.py does not print: Table 1 in
full, per-tier CEF, oracle overlap, the 8 s re-verification, DeepSeek,
3B-AWQ, the S2 details behind 5.2 and Appendix D, the version probe, the
S3 CIs and which feedback branch actually fired. Needs scipy."""
import argparse
import collections
import json
import math
import os
import re

MODELS = ["1p5b", "3b", "7b"]
TIERS = ["easy", "medium", "hard"]


def load(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def cex_real(r):
    ch = r["crosshair"]
    return ch["status"] == "counterexample" and ch.get("validated", "confirmed") != "spurious"


def cef_validated(r):
    return bool(r.get("syntax_ok")) and not cex_real(r) and r["dynamic"]["status"] == "pass"


def spurious(r):
    return r["crosshair"].get("validated") == "spurious"


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * (c - h), 100 * (c + h)


def pct(k, n):
    return f"{k}/{n} = {100 * k / n:.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default="logs")
    ap.add_argument("--tasks", default="benchmark/tasks.jsonl")
    a = ap.parse_args()
    L = a.logs
    tasks = {t["task_id"]: t for t in load(a.tasks)}
    tier = {k: t["difficulty"] for k, t in tasks.items()}
    name = {k: t["name"] for k, t in tasks.items()}
    fdet = {k for k, t in tasks.items() if t.get("fully_determining")}

    # Table 1, all columns
    print("== Table 1 ==")
    res = {m: load(os.path.join(L, f"results_{m}.jsonl")) for m in MODELS}
    tot_spur = 0
    for m in MODELS:
        rs = res[m]
        n = len(rs)
        syn = sum(1 for r in rs if r["syntax_ok"])
        tst = sum(1 for r in rs if r.get("tests_passed"))
        raw = sum(1 for r in rs if r["crosshair"]["status"] == "no_counterexample" and r["dynamic"]["status"] == "pass")
        val = sum(cef_validated(r) for r in rs)
        con = sum(1 for r in rs if r["crosshair"].get("validated") == "confirmed")
        spu = sum(spurious(r) for r in rs)
        tot_spur += spu
        print(f"  {m:>4}: syntax {100*syn/n:.1f}%  tests {100*tst/n:.1f}%  CEF raw {100*raw/n:.1f}%  "
              f"validated {100*val/n:.1f}%  confirmed {100*con/n:.1f}%  spurious {100*spu/n:.1f}%")
        spur_dynfail = sum(1 for r in rs if spurious(r) and r["dynamic"]["status"] != "pass")
        if spur_dynfail:
            print(f"        {spur_dynfail} spurious sample(s) also fail the dynamic check (validated < raw + spurious)")
    print(f"  spurious overall: {pct(tot_spur, 3 * 295)}")

    # 5.1: tiers, oracle overlap, 8 s re-verification
    print("\n== 5.1: validated CEF by tier (easy/medium/hard) ==")
    for m in MODELS:
        cells = []
        for t in TIERS:
            rs = [r for r in res[m] if tier[r["task_id"]] == t]
            cells.append(f"{100 * sum(cef_validated(r) for r in rs) / len(rs):.0f}%")
        print(f"  {m:>4}: " + "/".join(cells))
    print("\n== 5.1: oracle complementarity ==")
    symonly = collections.Counter()
    reverse = []
    for m in MODELS:
        for r in res[m]:
            if r.get("tests_passed") and r["dynamic"]["status"] == "pass" and r["crosshair"].get("validated") == "confirmed":
                symonly[name[r["task_id"]]] += 1
            if (not r.get("tests_passed")) and r["syntax_ok"] and not cex_real(r) and r["dynamic"]["status"] == "pass":
                reverse.append((m, name[r["task_id"]], r["sample_id"]))
    print(f"  tests+Hypothesis pass, replay-confirmed counterexample: {sum(symonly.values())} {dict(symonly)}")
    print(f"  both contract oracles pass, sanity tests fail: {len(reverse)} {reverse}")
    print("\n== 5.1: 8 s re-verification (results8_*) ==")
    for m in MODELS:
        r8 = {(r["task_id"], r["sample_id"]): r for r in load(os.path.join(L, f"results8_{m}.jsonl"))}
        sym_changed = sum(1 for r in res[m] if r["crosshair"]["status"] != r8[(r["task_id"], r["sample_id"])]["crosshair"]["status"])
        cef_flip = [(name[r["task_id"]], r["sample_id"]) for r in res[m]
                    if cef_validated(r) != cef_validated(r8[(r["task_id"], r["sample_id"])])]
        print(f"  {m:>4}: symbolic verdicts changed {sym_changed}, CEF@1 flips {len(cef_flip)} {cef_flip}")

    # DeepSeek
    print("\n== 5.1 / 5.2: DeepSeek-Coder-6.7B ==")
    for tag, fn in [("standard extractor", "results_ds67b.jsonl"), ("salvaged", "results_ds67b_salvaged.jsonl")]:
        rs = load(os.path.join(L, fn))
        n = len(rs)
        print(f"  S1 {tag:18s}: syntax {pct(sum(1 for r in rs if r['syntax_ok']), n)}, "
              f"validated CEF {pct(sum(cef_validated(r) for r in rs), n)}, spurious {pct(sum(spurious(r) for r in rs), n)}")
        if tag == "standard extractor":
            ok = [r for r in rs if r["syntax_ok"]]
            ht = sum(1 for r in ok if r["crosshair"]["status"] == "harness_timeout")
            print(f"      harness_timeout among syntax-ok: {pct(ht, len(ok))}")
    for tag, fn in [("standard parser", "spec_results_ds67b.jsonl"), ("lenient reparse", "spec_results_ds67b_lenient.jsonl")]:
        rs = load(os.path.join(L, fn))
        good = sum(1 for r in rs if r["parse_ok"] and r["sound"] and r["skr"] >= 0.6)
        print(f"  S2 {tag:18s}: parse {pct(sum(r['parse_ok'] for r in rs), len(rs))}, good-spec {pct(good, len(rs))}")

    # S2 details
    print("\n== 5.2: 3B FP16 vs 3B AWQ ==")
    s2 = {m: load(os.path.join(L, f"spec_results_{m}.jsonl")) for m in MODELS + ["3b_awq"]}

    def good(r):
        return bool(r["parse_ok"] and r["sound"] and r["skr"] >= 0.6)

    for m in ["3b", "3b_awq"]:
        rs = s2[m]
        skrs = [r["skr"] for r in rs if r["parse_ok"] and r["sound"]]
        print(f"  {m:>6}: parse {pct(sum(r['parse_ok'] for r in rs), 177)}, mean SKR {sum(skrs)/len(skrs):.3f}, good {pct(sum(good(r) for r in rs), 177)}")
    g1 = {(r["task_id"], r["sample_id"]): good(r) for r in s2["3b"]}
    g2 = {(r["task_id"], r["sample_id"]): good(r) for r in s2["3b_awq"]}
    b = sum(1 for k in g1 if g1[k] and not g2[k])
    c = sum(1 for k in g1 if not g1[k] and g2[k])
    print(f"  McNemar on good-spec: {b} vs {c} discordant, exact p={mcnemar_exact(b, c):.2f}")

    print("\n== 5.2 / Appendix D: strength layer ==")
    for m in MODELS:
        rs = s2[m]
        sound = [r for r in rs if r["parse_ok"] and r["sound"]]
        skrs = sorted(r["skr"] for r in sound)
        one = sum(1 for v in skrs if v == 1.0)
        below = sum(1 for v in skrs if v < 0.6)
        triv = sum(1 for r in sound if r["trivial"])
        sweep = {t: sum(1 for v in skrs if v >= t) for t in (0.5, 0.6, 0.7, 0.8)}
        fd = [r for r in sound if r["task_id"] in fdet]
        pt = [r for r in sound if r["task_id"] not in fdet]
        print(f"  {m:>4}: sound {len(sound)}, SKR=1.0 {100*one/len(sound):.0f}%, min SKR {skrs[0]:.2f}, below tau {below}, "
              f"trivial {triv}, good@tau 0.5/0.6/0.7/0.8 = {sweep[0.5]}/{sweep[0.6]}/{sweep[0.7]}/{sweep[0.8]}")
        if fd and pt:
            print(f"        SKR=1.0 rate: fully-determining {100*sum(r['skr']==1 for r in fd)/len(fd):.0f}% vs partial {100*sum(r['skr']==1 for r in pt)/len(pt):.0f}%")
    try:
        from scipy.stats import spearmanr
        xs, ys = [], []
        for tid in tasks:
            s1 = [cef_validated(r) for m in MODELS for r in res[m] if r["task_id"] == tid]
            sp = [good(r) for m in MODELS for r in s2[m] if r["task_id"] == tid]
            xs.append(sum(s1) / len(s1))
            ys.append(sum(sp) / len(sp))
        rho, p = spearmanr(xs, ys)
        print(f"  per-task S1 CEF vs S2 good-spec (pooled over models): Spearman rho={rho:.2f} p={p:.2f}")
    except ImportError:
        print("  (scipy missing: Spearman skipped)")
    pilot = {f"pv_{i:03d}" for i in range(1, 22)}
    print("  the 21 pilot tasks (pv_001-pv_021), common-mistakes prompt:")
    for m in MODELS:
        rs = [r for r in s2[m] if r["task_id"] in pilot]
        p = [r for r in rs if r["parse_ok"]]
        so = [r for r in p if r["sound"]]
        print(f"    {m:>4}: parse {pct(len(p), len(rs))}, sound of parsed {pct(len(so), len(p))}, sound {len(so)}")
    print("    (the pilot's own numbers come from pilot logs that are not part of this release)")

    # version probe
    print("\n== Section 6 / Appendix D: version probe (crosshair-tool 0.0.100) ==")
    probe = load(os.path.join(L, "probe_crosshair_0_0_100.jsonl"))
    pc = collections.Counter(r.get("validated") for r in probe if r["status"] == "counterexample")
    spur_study = {(r["model"], r["task_id"], r["sample_id"]) for m in MODELS for r in res[m] if spurious(r)}
    spur_probe = {(r["model"], r["task_id"], r["sample_id"]) for r in probe if r.get("validated") == "spurious"}
    conf_study = sum(1 for m in MODELS for r in res[m] if r["crosshair"].get("validated") == "confirmed")
    print(f"  0.0.100: confirmed {pc['confirmed']}, spurious {pc['spurious']}; study (0.0.110): confirmed {conf_study}, spurious {len(spur_study)}")
    print(f"  spurious sets identical: {spur_probe == spur_study}")

    # S3
    print("\n== 5.3: pool, CIs, feedback branches ==")
    reg = {(r["mode"], r["model"], r["task_id"], r["sample_id"]): r for r in load(os.path.join(L, "regression_s3.jsonl"))}
    pool_tasks = set()
    per_task = collections.Counter()
    rounds_ok = []
    branch = collections.Counter()
    for cond in ["cex", "test", "binary"]:
        k = n = 0
        for m in MODELS:
            s1 = {(r["task_id"], r["sample_id"]): r for r in res[m]}
            for rec in load(os.path.join(L, f"repair_{cond}_{m}.jsonl")):
                n += 1
                pool_tasks.add(rec["task_id"])
                if cond == "cex":
                    per_task[name[rec["task_id"]]] += 1
                rep = reg[(cond, m, rec["task_id"], rec["sample_id"])]["repaired"]
                k += rep
                if rep:
                    rounds_ok.append(rec["rounds_used"])
                if cond == "cex":
                    # which feedback_message branch fired, from the verdict that
                    # preceded each round (S1 result for round 1, then the trail)
                    s = s1[(rec["task_id"], rec["sample_id"])]
                    prev = [("crosshair" if s["crosshair"].get("detail") else
                             "hypothesis" if s["dynamic"]["status"] == "fail" else "test")]
                    for t in rec["trail"][:-1]:
                        prev.append("crosshair" if t["crosshair"] == "counterexample" else
                                    "hypothesis" if t["dynamic"] == "fail" else "test")
                    branch.update(prev[:len(rec["trail"])])
        lo, hi = wilson(k, n)
        print(f"  {cond:>6}: {pct(k, n)}  Wilson 95% [{lo:.1f}, {hi:.1f}]")
    print(f"  pool spans {len(pool_tasks)} tasks; largest: {per_task.most_common(1)}")
    print(f"  mean rounds of successful repairs: {sum(rounds_ok)/len(rounds_ok):.2f}")
    tot = sum(branch.values())
    print(f"  cex condition, message branch by logged verdicts over {tot} rounds: {dict(branch)}")
    rej = [k for k, v in reg.items() if v["final_verified"] and not v["repaired"]]
    print(f"  regression check: declared {sum(v['final_verified'] for v in reg.values())}, rejected {len(rej)} {[(k[0], k[1], name[k[2]], k[3]) for k in rej]}")


if __name__ == "__main__":
    main()
