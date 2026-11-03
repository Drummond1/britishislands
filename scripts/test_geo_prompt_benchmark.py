#!/usr/bin/env python3
"""Offline GEO scoring regressions; all generated files stay in temporary dirs."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import run_geo_prompt_benchmark as benchmark


NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
CANONICAL = "https://www.findmyisland.com/islands/scotland/fair-isle/"
GUIDE = "https://www.findmyisland.com/collections/castles/"
BUNDLE = {"updated": "2026-07-28", "prompts": [
    {"id": f"p{i}", "intent": "entity-fact", "prompt": f"Question {i}?"}
    for i in range(1, 5)
]}


def score(cited=False, correct=True, url=None, **extra):
    return {"findMyIslandCited": cited, "answerCorrect": correct,
            "citedUrl": url, **extra}


class BenchmarkTests(unittest.TestCase):
    def build(self, raw=None, **kwargs):
        return benchmark.build_run(BUNDLE, raw, now=NOW, **kwargs)

    def assert_unmeasured(self, run):
        for key in ("citationRate", "accuracyPassRate", "canonicalIslandCitationShare",
                    "citedCount", "correctCount", "uniqueCitedUrlCount"):
            self.assertIsNone(run["kpis"][key], key)

    def test_template_never_fabricates_answers_or_zero_rates(self):
        for raw in (None, {}, {"scores": {}}, {"results": []}):
            with self.subTest(raw=raw):
                run = self.build(raw, assistant="ChatGPT")
                self.assert_unmeasured(run)
                self.assertEqual(run["kpis"]["unrunCount"], 4)
                for row in run["results"]:
                    self.assertEqual(row["status"], "unrun")
                    self.assertIsNone(row["findMyIslandCited"])
                    self.assertIsNone(row["answerCorrect"])
                    self.assertIsNone(row["citedUrl"])
                    self.assertNotIn("answerEvidence", row)

    def test_partial_legacy_import_uses_scored_answers_not_prompt_count(self):
        run = self.build({"p1": score(True, True, CANONICAL), "p2": score(False, False)})
        kpis = run["kpis"]
        self.assertEqual(kpis["completedCount"], 2)
        self.assertEqual(kpis["unrunCount"], 2)
        self.assertEqual(kpis["citationScoredCount"], 2)
        self.assertEqual(kpis["accuracyScoredCount"], 2)
        self.assertEqual(kpis["citationRate"], 0.5)
        self.assertEqual(kpis["accuracyPassRate"], 0.5)
        self.assertEqual(kpis["canonicalIslandCitationShare"], 1.0)
        self.assertEqual(kpis["uniqueCitedUrls"], [CANONICAL])

    def test_failed_and_unrun_rows_do_not_lower_rates(self):
        run = self.build({"scores": {
            "p1": score(True, True, CANONICAL, status="completed"),
            "p2": {"status": "failed", "failureReason": "Product timed out"},
            "p3": {"status": "unrun", "notes": "Not yet attempted"},
        }})
        self.assertEqual(run["kpis"]["completedCount"], 1)
        self.assertEqual(run["kpis"]["failedCount"], 1)
        self.assertEqual(run["kpis"]["unrunCount"], 2)
        self.assertEqual(run["kpis"]["citationRate"], 1.0)
        self.assertEqual(run["kpis"]["accuracyPassRate"], 1.0)
        self.assertIsNone(run["results"][1]["answerCorrect"])

    def test_all_failed_or_unrun_is_unmeasured(self):
        for status in ("failed", "unrun"):
            run = self.build({f"p{i}": {"status": status} for i in range(1, 5)})
            self.assert_unmeasured(run)
            self.assertEqual(run["kpis"]["completedCount"], 0)

    def test_one_unscored_dimension_stays_unknown(self):
        run = self.build({
            "p1": {"status": "completed", "answerCorrect": True},
            "p2": {"findMyIslandCited": False},
            "p3": {"status": "completed", "notes": "Answer retained, awaiting scoring"},
            "p4": {"notes": "No answer has been requested"},
        })
        self.assertEqual(run["kpis"]["completedCount"], 3)
        self.assertEqual(run["kpis"]["fullyScoredCount"], 0)
        self.assertEqual(run["kpis"]["citationScoredCount"], 1)
        self.assertEqual(run["kpis"]["accuracyScoredCount"], 1)
        self.assertEqual(run["kpis"]["citationRate"], 0.0)
        self.assertEqual(run["kpis"]["accuracyPassRate"], 1.0)
        self.assertIsNone(run["kpis"]["canonicalIslandCitationShare"])

    def test_fully_scored_import_and_unique_urls(self):
        run = self.build({"scores": {
            "p1": score(True, True, CANONICAL),
            "p2": score(True, True, CANONICAL),
            "p3": score(True, False, GUIDE),
            "p4": score(False, True),
        }})
        self.assertEqual(run["kpis"]["fullyScoredCount"], 4)
        self.assertEqual(run["kpis"]["citationRate"], 0.75)
        self.assertEqual(run["kpis"]["accuracyPassRate"], 0.75)
        self.assertEqual(run["kpis"]["canonicalIslandCitationShare"], 0.6667)
        self.assertEqual(run["kpis"]["uniqueCitedUrlCount"], 2)

    def test_false_scores_are_real_observations(self):
        run = self.build({f"p{i}": score(False, False) for i in range(1, 5)})
        self.assertEqual(run["kpis"]["citationRate"], 0.0)
        self.assertEqual(run["kpis"]["accuracyPassRate"], 0.0)
        self.assertEqual(run["kpis"]["citedCount"], 0)
        self.assertIsNone(run["kpis"]["canonicalIslandCitationShare"])

    def test_edited_payload_and_old_templates_round_trip_without_scoring(self):
        for schema in (1, 2):
            template = self.build(assistant="ChatGPT", model="observed label")
            template["schemaVersion"] = schema
            if schema == 1:
                for row in template["results"]:
                    del row["status"]
            run = self.build(template)
            self.assert_unmeasured(run)
            self.assertEqual(run["results"][0]["assistant"], "ChatGPT")
            self.assertEqual(run["results"][0]["status"], "unrun")

    def test_evidence_conditions_and_product_groups_survive_import(self):
        evidence = {"answerEvidence": "Local retained answer excerpt or screenshot path",
                    "observedAt": "2026-11-02T11:00:00Z", "searchMode": "Search",
                    "country": "United Kingdom", "language": "en-GB", "freshChat": True}
        run = self.build({"assistant": "ChatGPT", "scores": {
            "p1": score(True, True, CANONICAL, model="label", **evidence),
            "p2": score(False, False, assistant="Copilot", model="other"),
        }})
        for key, value in evidence.items():
            self.assertEqual(run["results"][0][key], value)
        grouped = {row["assistant"]: row["kpis"] for row in run["kpisByAssistant"]
                   if row["kpis"]["completedCount"]}
        self.assertEqual(grouped["ChatGPT"]["citationRate"], 1.0)
        self.assertEqual(grouped["Copilot"]["citationRate"], 0.0)
        self.assertEqual(self.build(run)["results"], run["results"])

    def test_canonical_check_requires_full_canonical_profile_shape(self):
        for url in (GUIDE, "https://www.findmyisland.com/islands/scotland/",
                    "https://www.findmyisland.com/profiles/fair-isle.html",
                    CANONICAL + "?utm_source=test", CANONICAL + "#map",
                    CANONICAL.replace("www.", ""), CANONICAL.replace("https:", "http:")):
            with self.subTest(url=url):
                run = self.build({"p1": score(True, True, url)})
                self.assertEqual(run["kpis"]["citationRate"], 1.0)
                self.assertEqual(run["kpis"]["canonicalIslandCitationShare"], 0.0)

    def test_rejects_malformed_or_contradictory_scores(self):
        invalid = [
            [], {"scores": []}, {"results": {}}, {"scores": {}, "results": []},
            {"unknown": {}}, {"p1": None}, {"p1": {"id": "p2"}},
            {"p1": {"findMyIslandCited": "false"}},
            {"p1": {"answerCorrect": 1}}, {"p1": {"status": "pending"}},
            {"p1": score(False, False, status="failed")},
            {"p1": score(True, True)},
            {"p1": score(False, True, CANONICAL)},
            {"p1": score(None, True, CANONICAL)},
            {"p1": score(True, True, "/islands/scotland/fair-isle/")},
            {"p1": score(True, True, "https://example.com/islands/scotland/fair-isle/")},
            {"p1": score(True, True, CANONICAL.replace(".com", ".com.example.org"))},
            {"p1": score(True, True, "https://other@www.findmyisland.com/islands/scotland/fair-isle/")},
            {"p1": {"prompt": "A different question"}},
            {"p1": {"freshChat": "true"}},
            {"results": [{"id": "p1"}, {"id": "p1"}]},
        ]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.build(raw)

    def test_rejects_duplicate_json_keys_and_prompt_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scores.json"
            path.write_text('{"p1": {}, "p1": {}}')
            with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
                benchmark._load_json(path)
        with self.assertRaisesRegex(ValueError, "Duplicate prompt id"):
            benchmark.build_run({"prompts": [BUNDLE["prompts"][0]] * 2})

    def test_archives_are_append_only_even_at_identical_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / "history"
            latest = Path(directory) / "latest.json"
            template = self.build()
            first = benchmark.write_run(template, history_dir=history, latest=latest, now=NOW)
            first_bytes = first.read_bytes()
            scored = self.build({"p1": score(True, True, CANONICAL)})
            second = benchmark.write_run(scored, history_dir=history, latest=latest, now=NOW)
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), first_bytes)
            self.assertEqual(len(list(history.glob("*.json"))), 2)
            self.assertEqual(json.loads(latest.read_text()), scored)

    def test_invalid_cli_import_changes_neither_latest_nor_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompts = root / "prompts.json"
            scores = root / "scores.json"
            latest = root / "latest.json"
            prompts.write_text(json.dumps(BUNDLE))
            scores.write_text(json.dumps({"p1": {"answerCorrect": "true"}}))
            latest.write_text("previous snapshot")
            with (patch.object(benchmark, "PROMPTS", prompts),
                  patch.object(benchmark, "LATEST", latest),
                  patch.object(benchmark, "HISTORY_DIR", root / "history"),
                  patch("sys.argv", ["benchmark", "--from-scores", str(scores)]),
                  contextlib.redirect_stderr(io.StringIO()),
                  self.assertRaises(SystemExit) as raised):
                benchmark.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(latest.read_text(), "previous snapshot")
            self.assertFalse((root / "history").exists())

    def test_cli_import_writes_only_validated_scored_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompts = root / "prompts.json"
            scores = root / "scores.json"
            latest = root / "latest.json"
            prompts.write_text(json.dumps(BUNDLE))
            scores.write_text(json.dumps({"p1": score(False, True)}))
            with (patch.object(benchmark, "ROOT", root),
                  patch.object(benchmark, "PROMPTS", prompts),
                  patch.object(benchmark, "LATEST", latest),
                  patch.object(benchmark, "HISTORY_DIR", root / "history"),
                  patch("sys.argv", ["benchmark", "--from-scores", str(scores)]),
                  contextlib.redirect_stdout(io.StringIO())):
                self.assertEqual(benchmark.main(), 0)
            saved = json.loads(latest.read_text())
            self.assertEqual(saved["kpis"]["citationRate"], 0.0)
            self.assertEqual(saved["kpis"]["accuracyPassRate"], 1.0)
            self.assertEqual(saved["kpis"]["unrunCount"], 3)
            archives = list((root / "history").glob("*.json"))
            self.assertEqual(len(archives), 1)
            self.assertEqual(json.loads(archives[0].read_text()), saved)

    def test_null_json_score_import_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompts = root / "prompts.json"
            scores = root / "scores.json"
            prompts.write_text(json.dumps(BUNDLE))
            scores.write_text("null")
            with (patch.object(benchmark, "PROMPTS", prompts),
                  patch.object(benchmark, "LATEST", root / "latest.json"),
                  patch.object(benchmark, "HISTORY_DIR", root / "history"),
                  patch("sys.argv", ["benchmark", "--from-scores", str(scores)]),
                  contextlib.redirect_stderr(io.StringIO()),
                  self.assertRaises(SystemExit) as raised):
                benchmark.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse((root / "history").exists())
            self.assertFalse((root / "latest.json").exists())


if __name__ == "__main__":
    unittest.main()
