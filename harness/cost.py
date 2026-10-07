#!/usr/bin/env python3
"""Timing numbers for Appendix A, from the gen_seconds/verify_seconds fields."""
import argparse
import json
import os
import statistics as st

MODELS = ["1p5b", "3b", "7b"]


def load(p):
    with open(p) as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default="logs")
    a = ap.parse_args()
    L = a.logs
    print("S1 (295 completions per model)")
    for m in MODELS:
        g = [r["gen_seconds"] for r in load(os.path.join(L, f"completions_{m}.jsonl"))]
        v = [r["verify_seconds"] for r in load(os.path.join(L, f"results_{m}.jsonl"))]
        print(f"  {m:>4}: generation {sum(g)/60:4.1f} min wall-clock | "
              f"verification {sum(v)/60:5.1f} CPU-min serialized "
              f"(median {st.median(v):.1f} s, max {max(v):.0f} s per completion)")
    print("S3 (per feedback condition x model)")
    for cond in ["cex", "test", "binary"]:
        for m in MODELS:
            rounds = [t["gen_seconds"]
                      for r in load(os.path.join(L, f"repair_{cond}_{m}.jsonl"))
                      for t in r["trail"]]
            # rounds over 300 s are waits on a restarting server, not generation
            kept = [x for x in rounds if x <= 300]
            note = f" ({len(rounds)-len(kept)} server-wait rounds excluded)" \
                if len(kept) < len(rounds) else ""
            print(f"  {cond:>6}/{m:<4}: {len(rounds):3d} rounds, generation "
                  f"{sum(kept)/60:4.1f} min (median {st.median(rounds):.1f} s "
                  f"per call){note}")


if __name__ == "__main__":
    main()
