# Resume generation experiments

## Objective

Select a provisional local textbook-answering pipeline without changing frozen retrieval or benchmark inputs.

## Frozen invariants

- Retrieval Baseline v1 and Generation Benchmark v1 checksums are verified before every run.
- Development decisions use 16 fixed questions; the 24-question holdout is never used for tuning.
- Local llama.cpp CPU inference only; no hosted answer or judge calls.

## Current checkpoint

- Phase: complete
- Completed configurations in this matrix invocation: 23
- Exact next action: Complete blinded human review packet.

## Current leaders

- `qwen3_14b_q4_k_m__holdout__gold__P1__gold_separate_full__d7742c81bc`: coverage 0.5215, citation 1.0, p95 186.9131s
- `qwen3_8b_q4_k_m__holdout__retrieved__P1__retrieved_top5_page_order_compact__6c1d5ef407`: coverage 0.4903, citation 0.9583, p95 351.7045s
- `qwen3_8b_q4_k_m__all__gold__P1__gold_separate_full__899356a39f`: coverage 0.4654, citation 0.975, p95 85.7361s

## Resume command

Re-run the same matrix command. Completed question and run files are reused.
