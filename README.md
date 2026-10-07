# PyVeriBench

Code, data and logs for *Toward Verification for the 99%: Benchmarking
Contract-Based Verifiable Code Generation in Pure Python* (NeurIPS 2026
Workshop on AI for Verifiable Coding). MIT license.

```bibtex
@inproceedings{chen2026pyveribench,
  title     = {Toward Verification for the 99\%: Benchmarking Contract-Based
               Verifiable Code Generation in Pure Python},
  author    = {Chen, Tianze},
  booktitle = {NeurIPS 2026 Workshop on AI for Verifiable Coding},
  year      = {2026}
}
```

## Contents

```
benchmark/
  tasks.jsonl                    59 tasks (descriptions are verbatim what the models saw;
                                 fully_determining is derived, see build_tasks.py)
  mutants.jsonl                  493 candidate mutants; scoring uses equivalent=false (391)
  build_tasks.py                 builds tasks.jsonl
  mutants.py                     builds mutants.jsonl
harness/
  pyveri_lib.py                  shared code
  generate.py                    code generation
  verify.py                      verification
  spec_gen.py                    specification generation
  spec_score.py                  specification scoring
  spec_eval.py                   one contract against the mutants
  repair.py                      repair loop
  regression_replay.py           repair regression check
  paper_stats.py                 Tables 1-3 and the S3 tests
  extra_stats.py                 every other number in the paper
  differential.py                comparison with the reference code
  version_probe.py               re-verification with another CrossHair
  salvage_verify.py              salvage extractor (DeepSeek)
  merge_salvaged.py              puts salvage_verify output back into a results file
  lenient_parse.py               fence-tolerant reparse of a specs file (DeepSeek)
  contamination.py               HumanEval/MBPP overlap
  cost.py                        timing
  bpe_decode.py                  byte-level BPE decoding
  analyze.py                     per-task report
logs/
  completions_*, results_*       code generation (results8_*: 8 s budget)
  specs_*                        specification generation, raw model output
  spec_results_*                 specification generation, scored
  repair_*                       repair
  regression_s3.jsonl            repair regression check
  reference_contract_qa.jsonl    reference contracts against the mutants (run serially, see Notes)
  probe_crosshair_0_0_100.jsonl  CrossHair 0.0.100
  *ds67b*                        DeepSeek-Coder-6.7B (_salvaged, _lenient: see Notes)
  contamination_report.json      overlap report
```

## Setup

Python 3.10+, run from the repository root.

```
pip install -r requirements.txt
```

Generation expects an OpenAI-compatible server at `http://localhost:8000/v1`.
WSL2 with vLLM: `VLLM_USE_V2_MODEL_RUNNER=0 HF_HUB_OFFLINE=1`.

## Main results

```
python harness/paper_stats.py
python harness/extra_stats.py
```

## Pipeline

```
python harness/generate.py --n 5 --temperature 0.7 --out completions.jsonl
python harness/verify.py --completions completions.jsonl --out results.jsonl
python harness/spec_gen.py --n 3 --out specs.jsonl
python harness/spec_score.py --specs specs.jsonl --out spec_results.jsonl
python harness/repair.py --mode cex --completions completions.jsonl \
    --results results.jsonl --out repair_cex.jsonl
```

## Audits

```
python harness/regression_replay.py
python harness/spec_eval.py --symbolic --workers 1 --out logs/reference_contract_qa.jsonl
python harness/differential.py --completions logs/completions_7b.jsonl \
    --results logs/results_7b.jsonl
python harness/cost.py
PATH=/path/to/crosshair-0.0.100/bin:$PATH python harness/version_probe.py --out probe.jsonl
python harness/contamination.py --humaneval HumanEval.jsonl --mbpp mbpp.jsonl
```

DeepSeek extras:

```
python harness/salvage_verify.py logs/completions_ds67b.jsonl logs/results_ds67b.jsonl salvaged_rows.jsonl
python harness/merge_salvaged.py logs/results_ds67b.jsonl salvaged_rows.jsonl results_ds67b_salvaged.jsonl
python harness/lenient_parse.py --specs logs/specs_ds67b.jsonl --out specs_lenient.jsonl
python harness/spec_score.py --specs specs_lenient.jsonl --out spec_results_ds67b_lenient.jsonl
```

## Notes

- Logs come from crosshair-tool 0.0.110 with unseeded Hypothesis; re-runs
  may differ on a few verdicts.
- `paper_stats.py` applies `logs/regression_s3.jsonl`.
- DeepSeek outputs in `logs/` are decoded with `bpe_decode.py`.
- `model` fields in `logs/` hold Hugging Face IDs instead of local paths.
- `mutants.jsonl`: `equivalent` is true, false or null. null means the
  differential test could not run: 70 mutants only changed a type
  annotation (`list[int]` -> `list[int + 1]`) and fail at import, 8 timed
  out. Only `equivalent=false` mutants are scored.
- Run `spec_eval.py --symbolic` with `--workers 1`. With several workers
  CrossHair can hit the harness time limit, and `spec_eval.py` records
  that as `sound_symbolic: false` even though no counterexample was
  found. `logs/reference_contract_qa.jsonl` was produced serially (59/59
  true); the kill results do not depend on this.
- The task descriptions in `tasks.jsonl` are the prompts the models saw,
  including the clumsy sentence in `word_lengths`. Editing them breaks
  the correspondence with `logs/`.
- `repair.py` changed after the logged runs in two ways. (1) It now records
  the exact feedback string in each `trail` entry (`feedback`) and the
  pre-repair verdict (`pre_repair`); the shipped `repair_*` logs have
  neither, so what the model was told has to be reconstructed from the
  verdict that preceded each round (extra_stats.py does this for the
  counterexample condition). (2) A replay-refuted counterexample now also
  has its `detail` cleared, so it can no longer reach the feedback message.
  By the S1 verdicts this happened once in the logged runs: 1.5B `pv_047`
  sample 0, round 1 of the counterexample condition, whose message would
  have carried the spurious CrossHair line. The pre-repair re-verification
  was not logged, so this is an inference, not an observation.
- The counterexample-condition message forwards CrossHair's report line as
  is. For a violated postcondition CrossHair 0.0.110 prints `error: false
  when calling f(...) (which returns ...)` with a `path:line` into the
  temporary file; the condition text is not in the message.
- `fully_determining` in `tasks.jsonl` is true when some postcondition is
  `__return__ == e` with `e` not mentioning `__return__` (24 tasks).
- The pilot runs (21 tasks, prompt without the common-mistakes list) are
  not part of this release.
