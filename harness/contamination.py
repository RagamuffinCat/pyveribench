#!/usr/bin/env python3
"""HumanEval/MBPP overlap for the Limitations paragraph: 8-gram overlap and
difflib ratio, on task descriptions and on lexed reference code (strings
and comments stripped). Needs the two corpus files, not shipped."""
import argparse
import difflib
import io
import json
import re
import tokenize


def norm_text(s):
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()


def norm_code(s):
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(s).readline):
            if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                            tokenize.INDENT, tokenize.DEDENT,
                            tokenize.ENCODING, tokenize.ENDMARKER):
                continue
            if tok.type == tokenize.STRING:
                continue
            out.append(tok.string)
    except (tokenize.TokenError, IndentationError):
        out = s.split()
    return out


def ngrams(toks, n):
    return {tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def max_overlap(toks, corpus_tok_lists, n):
    mine = ngrams(toks, n)
    if not mine:
        return 0, 0.0, None
    best, best_id = 0, None
    union_hit = set()
    for cid, ctoks in corpus_tok_lists:
        cg = ngrams(ctoks, n)
        inter = mine & cg
        union_hit |= inter
        if len(inter) > best:
            best, best_id = len(inter), cid
    return best, len(union_hit) / len(mine), best_id


def max_sim(s, corpus_strings):
    best, best_id = 0.0, None
    for cid, c in corpus_strings:
        r = difflib.SequenceMatcher(None, s, c).ratio()
        if r > best:
            best, best_id = r, cid
    return best, best_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="benchmark/tasks.jsonl")
    ap.add_argument("--humaneval", required=True)
    ap.add_argument("--mbpp", required=True)
    ap.add_argument("--ngram-text", type=int, default=8)
    ap.add_argument("--ngram-code", type=int, default=8)
    ap.add_argument("--out", default="contamination_report.json")
    args = ap.parse_args()

    tasks = [json.loads(l) for l in open(args.tasks) if l.strip()]
    he = [json.loads(l) for l in open(args.humaneval) if l.strip()]
    mb = [json.loads(l) for l in open(args.mbpp) if l.strip()]

    corpus_text = ([(r["task_id"], r["prompt"]) for r in he]
                   + [(str(r["task_id"]), r["text"]) for r in mb])
    corpus_code = ([(r["task_id"], r["canonical_solution"]) for r in he]
                   + [(str(r["task_id"]), r["code"]) for r in mb])
    ct_tok = [(cid, norm_text(s)) for cid, s in corpus_text]
    cc_tok = [(cid, norm_code(s)) for cid, s in corpus_code]

    rows = []
    for t in tasks:
        desc = t["description"]
        ref = t["ref_impl"]
        tn, tshare, tid_ = max_overlap(norm_text(desc), ct_tok, args.ngram_text)
        cn, cshare, cid_ = max_overlap(norm_code(ref), cc_tok, args.ngram_code)
        tsim, tsim_id = max_sim(desc, corpus_text)
        csim, csim_id = max_sim(ref, corpus_code)
        rows.append(dict(task_id=t["task_id"], name=t["name"],
                         text_ngram_max=tn, text_ngram_share=round(tshare, 3),
                         text_ngram_nn=tid_,
                         code_ngram_max=cn, code_ngram_share=round(cshare, 3),
                         code_ngram_nn=cid_,
                         text_sim_max=round(tsim, 3), text_sim_nn=tsim_id,
                         code_sim_max=round(csim, 3), code_sim_nn=csim_id))

    json.dump(dict(ngram_text=args.ngram_text, ngram_code=args.ngram_code,
                   n_humaneval=len(he), n_mbpp=len(mb), rows=rows),
              open(args.out, "w"), indent=1)

    def top(key, k=8):
        return sorted(rows, key=lambda r: -r[key])[:k]

    n_t = sum(1 for r in rows if r["text_ngram_max"] > 0)
    n_c = sum(1 for r in rows if r["code_ngram_max"] > 0)
    print(f"corpus: {len(he)} HumanEval + {len(mb)} MBPP")
    print(f"tasks with ANY shared text {args.ngram_text}-gram: {n_t}/{len(rows)}")
    print(f"tasks with ANY shared code {args.ngram_code}-gram: {n_c}/{len(rows)}")
    print("\ntop text similarity (difflib):")
    for r in top("text_sim_max"):
        print(f"  {r['task_id']} {r['name']:<24} sim={r['text_sim_max']:.2f} "
              f"nn={r['text_sim_nn']} ngram_max={r['text_ngram_max']}")
    print("\ntop code similarity (difflib, lexed):")
    for r in top("code_sim_max"):
        print(f"  {r['task_id']} {r['name']:<24} sim={r['code_sim_max']:.2f} "
              f"nn={r['code_sim_nn']} ngram_max={r['code_ngram_max']}")


if __name__ == "__main__":
    main()
