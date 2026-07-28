# GEO Benchmark Cadence

This document defines a repeatable benchmark for AI-surfaced island answers
and citations.

## Goal

Track whether Find My Island is becoming a cited, accurate source in
assistant-style answers (not just whether it is mentioned).

## Cadence

- Run weekly.
- Keep each run append-only in `data/geo_prompt_benchmark_latest.json`.
- Compare against prior run for trend deltas.

## Prompt set

Use `data/geo_prompt_benchmark_prompts.json`:

- 50 prompts across maps, entity facts, comparisons, and transport intent.
- Keep prompt wording stable to preserve comparability over time.

## Record per prompt

- Assistant and model used.
- Whether Find My Island was cited.
- Which URL was cited.
- Whether the answer was factually correct.
- Query intent bucket.

## KPI rollup

- Citation rate for Find My Island.
- Unique cited URLs.
- Accuracy pass rate.
- Share of prompts where top cited page is a canonical island URL.

## Notes

- GEO gains should be interpreted alongside standard SEO metrics from GSC and
  Bing Webmaster tools.
- Do not optimize for mention spam; optimize for useful, correct answers.
