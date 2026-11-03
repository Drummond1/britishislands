# GEO benchmark procedure

Updated 2 November 2026. Track whether Find My Island is cited in accurate
assistant answers. A template is preparation for a benchmark; it contains no
observed answers or citation results.

## Cadence and comparable conditions

Use `data/geo_prompt_benchmark_prompts.json`: **50** prompts across atlas-map,
entity-fact, comparison, transport, language, for-sale and authority intents.
The strategy calls for 10 priority prompts weekly and the full set monthly.
Keep the wording stable. Record any necessary prompt revision before comparing
versions, including the actual question used. The existing ferry and live-property
wording needs review against project policy before running that part of the set;
this runner does not change prompts or verify their claims.

Use a separate run for each product/model and comparable search conditions.
Record date, product, displayed model label, search mode, country, language and
whether each answer came from a fresh chat. Repeat prompts where results vary.
Compare matching completed/scored subsets and show coverage beside rates. A
four-answer partial run cannot establish a trend for the whole 50-prompt set.

## Runner and files

```bash
# Creates an unrun template only; makes no assistant or API calls.
python3 scripts/run_geo_prompt_benchmark.py --assistant "ChatGPT" --model "observed label"

# After retaining actual answers and manually scoring them:
python3 scripts/run_geo_prompt_benchmark.py --from-scores path/to/scores.json
```

Each successful invocation writes a new immutable archive under
`data/geo_prompt_benchmark_runs/` and refreshes the replaceable snapshot
`data/geo_prompt_benchmark_latest.json`. Archive names include microseconds and a
collision suffix where needed; an existing archive is never overwritten. Keep
historical archives unchanged, including old templates. Reimport old scores to
create a new schema-v2 result with corrected denominators.

`runAt` is the time the file was generated/imported. Use per-answer `observedAt`
for when an assistant was actually queried. An automated loop calling the runner
without scores creates another template, not a completed benchmark. Check
coverage and observation dates before using `latest` in reporting.

## Score format

Accepts the original prompt-id-keyed object, a `{"scores": {...}}` wrapper, or
an edited full runner payload with a `results` list. Missing prompt IDs remain
unrun. For a full payload, keep each result's original `id` and `prompt` text.

Example format only — these placeholder states are not measured results:

```json
{
  "assistant": "Product actually used",
  "model": "Displayed model label, or unknown",
  "scores": {
    "atlas-map-001": {
      "status": "unrun",
      "findMyIslandCited": null,
      "citedUrl": null,
      "answerCorrect": null,
      "notes": "Not yet attempted"
    }
  }
}
```

| Field | Meaning |
| --- | --- |
| `status` | `completed`: an answer was obtained; `failed`: the attempt failed; `unrun`: not attempted. |
| `findMyIslandCited` | `true` or `false` after checking the answer's actual linked citations; `null` until scored. A brand mention alone is `false`. |
| `citedUrl` | The top/first Find My Island citation URL, as actually linked, when cited; otherwise `null`. |
| `answerCorrect` | `true` or `false` after checking material claims against reliable sources; `null` while unscored or uncertain. Explain the check in `notes`. |
| `answerEvidence` | Optional answer text, saved evidence path or share URL. Retain the full answer/citations so the score can be checked. |
| `observedAt` | Optional ISO timestamp of the actual observation. |
| `searchMode`, `country`, `language`, `freshChat` | Optional observation conditions; `freshChat` is a boolean or `null`. |
| `failureReason`, `notes` | Optional explanation of failure, factual verification or scoring decisions. |
| `assistant`, `model` | Optional per-answer labels; otherwise wrapper labels apply. Explicit CLI labels override imported labels. |

Failed and unrun rows must have null/missing scores and no cited URL. Completed
rows may await either scoring dimension; that dimension stays outside its
denominator. A completed but inaccurate answer is `answerCorrect: false`, not a
failed attempt. Evidence/conditions are preserved when supplied; the runner
does not invent or independently verify them, and does not require them on
legacy imports. Record them before treating a run as publishable evidence.

For old scores without `status`, any explicit scoring boolean implies
`completed`; rows with null/missing booleans imply `unrun`. Existing explicit
`false` scores remain real observations. A notes-only row supplies no score.

The import rejects non-boolean scores (including strings and numbers), unknown
or duplicate IDs/JSON keys, changed prompt text, conflicting states and invalid
site URLs. A `true` citation requires an absolute HTTP(S) URL on
`findmyisland.com` or `www.findmyisland.com`. Invalid imports stop before writing
latest or an archive. The site URL is checked structurally; the runner does not
fetch it or confirm it was cited.

## KPI definitions (schema v2)

| Output | Numerator / denominator |
| --- | --- |
| `citationRate` | Completed answers explicitly scored as citing the site / completed answers with a citation boolean (`citationScoredCount`). |
| `accuracyPassRate` | Completed answers explicitly scored correct / completed answers with an accuracy boolean (`accuracyScoredCount`). |
| `canonicalIslandCitationShare` | Site-citing answers whose primary site citation has canonical island URL form / site-citing answers (`citedCount`). |
| `uniqueCitedUrlCount`, `uniqueCitedUrls` | Distinct primary site URLs recorded in cited answers. These do not count additional citations in the same answer. |

Canonical island URL form is
`https://www.findmyisland.com/islands/{nation}/{slug}/`, without a query or
fragment. Hubs, legacy `/profiles/` links, HTTP/non-www variants and parameterised
links count as site citations, but do not meet this strict canonical URL test.
This is a URL-shape check, not a live canonical-tag inspection.

Every rollup shows `completedCount`, `failedCount`, `unrunCount`,
`citationScoredCount`, `accuracyScoredCount` and `fullyScoredCount` (both booleans
present). With no eligible observations a rate is `null`, not zero. With zero
site citations the canonical share is `null`. Genuine scored negatives can
produce zero rates. In a fully scored run, both scored denominators equal the
completed-answer count. `kpisByAssistant` supplies separate product/model
rollups when imported labels differ; the top-level `kpis` aggregates the run.

For example, two completed and fully scored answers, one failed attempt and
47 unrun prompts have denominators of **2**. If one completed answer cites a
canonical island page, citation rate is **50%** and canonical share **100%**.
Neither percentage establishes improvement without comparable earlier evidence.

Interpret GEO alongside Search Console, Bing and visitor outcomes. Optimise
for useful, correct answers and traceable citations.

## Offline regression checks

```bash
python3 -m unittest discover -s scripts -p 'test_geo_prompt_benchmark.py' -v
```

Tests cover full/partial imports, failed/unrun templates, independent scoring
denominators, legacy and full-payload imports, validation, evidence retention,
per-product rollups and archive collisions. Test files are generated only in
temporary directories; no real benchmark result is created.
