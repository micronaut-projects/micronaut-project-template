#!/usr/bin/env python3
"""Unit tests for risk-tier.py. Run with: python3 .github/scripts/test_risk_tier.py"""
import importlib.util
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True

_spec = importlib.util.spec_from_file_location(
    "risk_tier", os.path.join(os.path.dirname(os.path.abspath(__file__)), "risk-tier.py"))
rt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rt)

_GLOBAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "risk-tiers.global.toml")
EMPTY = rt.load_rules(_GLOBAL, None)
CORE = rt.merge_rules(EMPTY, {"tiers": {"T2": {
    "paths": ["inject/src/main/**", "core-processor/src/main/**", "http*/src/main/**"]}}})

_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PULL_REQUEST_TEMPLATE.md")
TEMPLATE_BODY = open(_TEMPLATE, encoding="utf-8").read() if os.path.exists(_TEMPLATE) else None


def body(ai="assisted", tool="Claude Code", tier="T1", api="no"):
    return f"Some text\n\n## Review declaration\n\nAI use: {ai}\nAI tool: {tool}\nRisk tier: {tier}\nAPI or behaviour change: {api}\n"


class GlobTest(unittest.TestCase):
    def test_double_star(self):
        self.assertTrue(rt.matches_any("inject/src/test/java/A.java", ["**/src/test/**"]))
        self.assertTrue(rt.matches_any("src/test/java/A.java", ["**/src/test/**"]))
        self.assertFalse(rt.matches_any("inject/src/main/java/A.java", ["**/src/test/**"]))

    def test_unanchored_matches_any_depth(self):
        self.assertTrue(rt.matches_any("README.md", ["*.md"]))
        self.assertTrue(rt.matches_any("docs/notes/README.md", ["*.md"]))
        self.assertFalse(rt.matches_any("README.mdx", ["*.md"]))

    def test_anchored_does_not_match_nested(self):
        self.assertTrue(rt.matches_any("gradle/wrapper/gradle-wrapper.jar", ["gradle/**"]))
        self.assertFalse(rt.matches_any("inject/gradle/x", ["gradle/**"]))

    def test_single_star_does_not_cross_directories(self):
        self.assertTrue(rt.matches_any("http-client/src/main/A.java", ["http*/src/main/**"]))
        self.assertFalse(rt.matches_any("x/http/src/main/A.java", ["http*/src/main/**"]))

    def test_trailing_slash(self):
        self.assertTrue(rt.matches_any("buildSrc/a/b.gradle", ["buildSrc/"]))


class RulesTest(unittest.TestCase):
    def test_global_rules_are_valid(self):
        self.assertEqual(EMPTY["default_tier"], "T1")
        self.assertIn("type: breaking", EMPTY["tiers"]["T2"]["labels"])
        self.assertEqual(EMPTY["sources"], [_GLOBAL])

    def test_repository_values_overwrite_global_ones(self):
        merged = rt.merge_rules(EMPTY, {"jev": {"diff_t2_at": 0.7}, "tiers": {"T2": {"paths": ["a/**"], "labels": ["x"]}}})
        self.assertEqual(merged["jev"]["diff_t2_at"], 0.7)
        self.assertEqual(merged["jev"]["model"], EMPTY["jev"]["model"])
        self.assertEqual(merged["tiers"]["T2"]["paths"], ["a/**"])
        self.assertEqual(merged["tiers"]["T2"]["labels"], ["x"])
        self.assertEqual(merged["tiers"]["T2"]["description"], EMPTY["tiers"]["T2"]["description"])
        self.assertEqual(merged["tiers"]["T0"]["paths"], EMPTY["tiers"]["T0"]["paths"])

    def test_repository_can_loosen_global_rules(self):
        merged = rt.merge_rules(EMPTY, {"tiers": {"T0": {"paths": ["docs/**"]}, "T2": {"labels": []}}})
        self.assertEqual(merged["tiers"]["T0"]["paths"], ["docs/**"])
        self.assertEqual(merged["tiers"]["T2"]["labels"], [])

    def test_global_rules_name_no_module_areas(self):
        description = EMPTY["tiers"]["T2"]["description"].lower()
        for area in ("inject", "http", "security", "serialization"):
            self.assertNotIn(area, description)

    def test_description_replaces(self):
        merged = rt.merge_rules(EMPTY, {"tiers": {"T1": {"description": "Anything else."}}})
        self.assertEqual(merged["tiers"]["T1"]["description"], "Anything else.")

    def test_repository_file_is_merged(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as repo:
            repo.write('[tiers.T2]\npaths = ["inject/src/main/**"]\n')
        try:
            rules = rt.load_rules(_GLOBAL, repo.name)
        finally:
            os.unlink(repo.name)
        self.assertEqual(rules["tiers"]["T2"]["paths"], ["inject/src/main/**"])
        self.assertEqual(rules["sources"], [_GLOBAL, repo.name])
        self.assertEqual(rt.load_rules(_GLOBAL, "/nonexistent.toml")["sources"], [_GLOBAL])

    def test_invalid_rules_fail(self):
        with self.assertRaisesRegex(ValueError, "round_up_at"):
            rt.validate_rules(rt.merge_rules(EMPTY, {"jev": {"round_up_at": 2}}))
        with self.assertRaisesRegex(ValueError, "unknown tiers T3"):
            rt.validate_rules(rt.merge_rules(EMPTY, {"tiers": {"T3": {"description": "x"}}}))
        with self.assertRaisesRegex(ValueError, "default_tier"):
            rt.validate_rules(rt.merge_rules(EMPTY, {"default_tier": "T5"}))

    def test_questions_use_the_descriptions(self):
        rules = rt.merge_rules(EMPTY, {"tiers": {"T0": {"description": "Docs only."}}})
        questions = rt.jev_questions(rules)
        self.assertEqual(questions["tier"]["criteria"]["T0"], "Docs only.")
        self.assertIn(EMPTY["public_api"]["description"], questions["public_api"]["instructions"])
        self.assertEqual(questions["breaking"]["type"], "noul")


class FileTierTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(rt.file_tier("src/main/docs/guide/index.adoc", EMPTY), "T0")
        self.assertEqual(rt.file_tier(".github/workflows/gradle.yml", EMPTY), "T0")
        self.assertEqual(rt.file_tier("test-suite-kotlin/src/main/kotlin/A.kt", EMPTY), "T0")
        self.assertEqual(rt.file_tier("gradlew", EMPTY), "T0")
        self.assertEqual(rt.file_tier("module/src/main/java/A.java", EMPTY), "T1")
        self.assertEqual(rt.file_tier("module/build.gradle", EMPTY), "T1")

    def test_version_catalog_is_t1(self):
        self.assertEqual(rt.file_tier("gradle/libs.versions.toml", EMPTY), "T1")
        self.assertEqual(rt.file_tier("gradle/wrapper/gradle-wrapper.properties", EMPTY), "T0")

    def test_repository_t2_wins(self):
        self.assertEqual(rt.file_tier("inject/src/main/java/A.java", CORE), "T2")
        self.assertEqual(rt.file_tier("inject/src/test/java/A.java", CORE), "T0")

    def test_repository_t0(self):
        self.assertEqual(rt.file_tier("benchmarks/A.java", rt.merge_rules(EMPTY, {"tiers": {"T0": {"paths": ["benchmarks/**"]}}})), "T0")


class DeclarationTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(rt.parse_declaration(body()), {
            "ai_use": "assisted", "ai_tool": "Claude Code", "risk_tier": "T1", "api_change": "no"})

    def test_table(self):
        text = """| Field | Value |
|---|---|
| AI use | agent-generated |
| **AI tool** | Claude Code |
| Risk tier | `T2` |
| API or behaviour change | yes |
"""
        self.assertEqual(rt.parse_declaration(text), {
            "ai_use": "agent-generated", "ai_tool": "Claude Code", "risk_tier": "T2", "api_change": "yes"})

    def test_unedited_table_row(self):
        self.assertIsNone(rt.parse_declaration("| Risk tier | T0 / T1 / T2 |")["risk_tier"])

    def test_case_insensitive_and_decorated(self):
        text = "ai use: Agent-Generated\n**AI tool:** Codex\n- RISK TIER: `t2`\nApi or behaviour change: YES\n"
        self.assertEqual(rt.parse_declaration(text), {
            "ai_use": "agent-generated", "ai_tool": "Codex", "risk_tier": "T2", "api_change": "yes"})

    def test_unedited_template_is_not_declared(self):
        self.assertIsNotNone(TEMPLATE_BODY, "the pull request template should exist")
        self.assertEqual(rt.parse_declaration(TEMPLATE_BODY), {
            "ai_use": None, "ai_tool": None, "risk_tier": None, "api_change": None})

    def test_comments_ignored(self):
        self.assertEqual(rt.parse_declaration("<!--\nRisk tier: T0\n-->\nRisk tier: T2\n")["risk_tier"], "T2")

    def test_missing_body(self):
        self.assertEqual(rt.parse_declaration(None)["risk_tier"], None)

    def test_na_tool(self):
        self.assertIsNone(rt.parse_declaration(body(ai="none", tool="n/a"))["ai_tool"])


class ComputeTest(unittest.TestCase):
    def test_highest_tier_wins(self):
        result = rt.compute(["README.md", "inject/src/main/java/A.java", "x/src/main/B.java"], set(), body(tier="T2"), CORE)
        self.assertEqual(result["tier"], "T2")
        self.assertFalse(result["declared_too_low"])

    def test_no_files_is_t0(self):
        self.assertEqual(rt.compute([], set(), "", EMPTY)["tier"], "T0")

    def test_breaking_label(self):
        result = rt.compute(["README.md"], {"type: breaking"}, body(tier="T0"), EMPTY)
        self.assertEqual(result["tier"], "T2")
        self.assertTrue(result["declared_too_low"])

    def test_declared_api_change(self):
        self.assertEqual(rt.compute(["a/src/main/A.java"], set(), body(api="yes", tier="T2"), EMPTY)["tier"], "T2")

    def test_declared_too_low(self):
        self.assertTrue(rt.compute(["a/src/main/A.java"], set(), body(tier="T0"), EMPTY)["declared_too_low"])

    def test_declared_higher_is_fine(self):
        self.assertFalse(rt.compute(["README.md"], set(), body(tier="T2"), EMPTY)["declared_too_low"])

    def test_undeclared_is_not_too_low(self):
        self.assertFalse(rt.compute(["a/src/main/A.java"], set(), "", EMPTY)["declared_too_low"])


def jev(choice, t0=0.0, t1=0.0, t2=0.0, confidence=0.9):
    return {"choice": choice, "probabilities": {"T0": t0, "T1": t1, "T2": t2}, "confidence": confidence,
            "model": "jev-test"}


class JevTest(unittest.TestCase):
    def test_choice_sets_tier(self):
        result = rt.compute(["a/src/main/A.java"], set(), body(tier="T0"), EMPTY, jev("T0", t0=0.9, t1=0.1))
        self.assertEqual(result["tier"], "T0")
        self.assertEqual(result["rules_tier"], "T1")
        self.assertFalse(result["declared_too_low"])

    def test_unsure_answer_rounds_up(self):
        self.assertEqual(rt.jev_tier(jev("T0", t0=0.6, t1=0.3, t2=0.1), 0.25), "T1")
        self.assertEqual(rt.jev_tier(jev("T1", t0=0.2, t1=0.5, t2=0.3), 0.25), "T2")

    def test_choice_without_probabilities(self):
        self.assertEqual(rt.jev_tier({"choice": "T1", "confidence": 0.8}, 0.25), "T1")

    def test_unknown_choice_fails(self):
        with self.assertRaises(ValueError):
            rt.jev_tier({"choice": "medium"}, 0.25)

    def test_repository_t2_area_cannot_be_lowered(self):
        result = rt.compute(["inject/src/main/java/A.java"], set(), "", CORE, jev("T0", t0=1.0))
        self.assertEqual(result["tier"], "T2")

    def test_breaking_label_cannot_be_lowered(self):
        self.assertEqual(rt.compute(["README.md"], {"type: breaking"}, "", EMPTY, jev("T0", t0=1.0))["tier"], "T2")

    def test_declared_api_change_cannot_be_lowered(self):
        self.assertEqual(rt.compute(["README.md"], set(), body(api="yes"), EMPTY, jev("T0", t0=1.0))["tier"], "T2")

    def test_state(self):
        files = [{"filename": "inject/src/main/java/A.java", "status": "modified", "additions": 3, "deletions": 1},
                 {"filename": "README.md", "status": "added", "additions": 10, "deletions": 0}]
        state = rt.jev_state("Fix A", "Body<!-- hidden -->", {"type: bug"}, files, CORE)
        self.assertEqual(state["description"], "Body")
        self.assertEqual([f["path_rule_tier"] for f in state["changed_files"]], ["T2", "T0"])
        self.assertEqual(state["t2_areas"], CORE["tiers"]["T2"]["paths"])
        self.assertNotIn("changed_files_note", state)

    def test_state_is_bounded(self):
        files = [{"filename": f"f{i}.java"} for i in range(rt.JEV_MAX_FILES + 5)]
        state = rt.jev_state("t", "x" * (rt.JEV_MAX_BODY + 10), set(), files, EMPTY)
        self.assertEqual(len(state["changed_files"]), rt.JEV_MAX_FILES)
        self.assertEqual(state["total_changed_files"], rt.JEV_MAX_FILES + 5)
        self.assertTrue(state["description"].endswith("[truncated]"))

    def test_ask_jev_request(self):
        sent = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({"model": "jev-1.14.0", "answers": {"tier": {
                    "type": "choice", "choice": "T1", "probabilities": {"T0": 0.1, "T1": 0.8, "T2": 0.1},
                    "confidence": 0.8}, "public_api": {"type": "noul", "noul": 0.1},
                    "breaking": {"type": "noul", "noul": 0.05}}}).encode()

        def opener(request, timeout):
            sent["url"] = request.full_url
            sent["auth"] = request.get_header("Authorization")
            sent["body"] = json.loads(request.data)
            return Response()

        answer = rt.ask_jev({"title": "t"}, "key", EMPTY, opener=opener)
        self.assertEqual((answer["choice"], answer["model"]), ("T1", "jev-1.14.0"))
        self.assertEqual(sent["url"], rt.JEV_URL)
        self.assertEqual(sent["auth"], "Bearer key")
        self.assertEqual(sent["body"]["questions"]["tier"]["type"], "choice")
        self.assertEqual(sorted(sent["body"]["questions"]["tier"]["criteria"]), list(rt.TIERS))
        self.assertEqual(sent["body"]["questions"]["public_api"]["type"], "noul")
        self.assertEqual((answer["public_api"], answer["breaking"]), (0.1, 0.05))

    def test_public_api_answer_raises_to_t2(self):
        answer = dict(jev("T1", t1=0.9, t0=0.1), public_api=0.8, breaking=0.1)
        result = rt.compute(["a/src/main/A.java"], set(), "", EMPTY, answer)
        self.assertEqual(result["tier"], "T2")
        self.assertIn("changes public API", result["reasons"][-1])

    def test_breaking_answer_raises_to_t2(self):
        answer = dict(jev("T0", t0=1.0), public_api=0.1, breaking=0.6)
        self.assertEqual(rt.compute(["a/src/main/A.java"], set(), "", EMPTY, answer)["tier"], "T2")

    def test_unlikely_api_change_keeps_tier(self):
        answer = dict(jev("T1", t1=0.9, t0=0.1), public_api=0.3, breaking=0.2)
        self.assertEqual(rt.compute(["a/src/main/A.java"], set(), "", EMPTY, answer)["tier"], "T1")

    def test_diff_keeps_main_sources_and_changed_lines(self):
        files = [
            {"filename": "a/src/main/java/A.java", "status": "modified", "additions": 1, "deletions": 1,
             "patch": "@@ -1,3 +1,3 @@\n context\n-public void a()\n+public void b()"},
            {"filename": "a/src/test/java/ATest.java", "status": "modified", "additions": 1, "deletions": 0,
             "patch": "@@ -1 +1,2 @@\n+test"},
            {"filename": "inject/src/main/java/B.java", "status": "added", "additions": 50, "deletions": 0,
             "patch": "@@ -0,0 +1 @@\n+class B {}"},
        ]
        diff, omitted = rt.main_source_diff(files, CORE)
        self.assertEqual(omitted, 0)
        self.assertNotIn("ATest", diff)
        self.assertNotIn("context", diff)
        self.assertLess(diff.index("inject/src/main/java/B.java"), diff.index("a/src/main/java/A.java"))
        self.assertIn("+public void b()", diff)

    def test_diff_is_bounded(self):
        big = "\n".join("+" + "x" * 99 for _ in range(rt.JEV_MAX_DIFF // 100 + 10))
        files = [{"filename": "a/src/main/A.java", "patch": big}, {"filename": "a/src/main/B.java", "patch": "+b"}]
        diff, omitted = rt.main_source_diff(files, EMPTY)
        self.assertEqual(omitted, 1)
        self.assertIn("B.java", diff)
        state = rt.jev_state("t", "", set(), files, EMPTY)
        self.assertIn("main_source_diff_note", state)

    def test_retries_rate_limit(self):
        import io
        import urllib.error
        calls = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return (b'{"answers": {"tier": {"choice": "T0"}, "public_api": {"noul": 0.0},'
                        b' "breaking": {"noul": 0.0}}}')

        def opener(request, timeout):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError(rt.JEV_URL, 429, "slow down", {"retry-after": "0"}, io.BytesIO(b""))
            return Response()

        self.assertEqual(rt.ask_jev({}, "key", EMPTY, opener=opener)["choice"], "T0")
        self.assertEqual(len(calls), 2)

    def test_error_fails(self):
        import io
        import urllib.error

        def opener(request, timeout):
            raise urllib.error.HTTPError(rt.JEV_URL, 401, "bad key", {}, io.BytesIO(b"invalid key"))

        with self.assertRaisesRegex(RuntimeError, "401"):
            rt.ask_jev({}, "key", EMPTY, opener=opener)

    def test_missing_key_fails(self):
        with self.assertRaises(RuntimeError):
            rt.ask_jev({}, None, EMPTY)

    def test_summary_names_the_model(self):
        result = rt.compute(["a/src/main/A.java"], set(), "", EMPTY, jev("T1", t1=0.9, t0=0.1))
        text = rt.summary(result, [])
        self.assertIn("jev-test", text)
        self.assertIn("path rules alone give T1", text)


def labeled(name, login):
    return {"event": "labeled", "label": {"name": name}, "actor": {"login": login}}


class ToolFooterTest(unittest.TestCase):
    def test_detects_footers(self):
        for line in ("_Generated by [Claude Code](https://claude.ai/code)_",
                     "\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)",
                     "https://claude.ai/code/session_011abc",
                     "Co-Authored-By: Claude Opus <noreply@anthropic.com>",
                     "Made with Cursor",
                     "Generated with Copilot",
                     "_Requested by **Someone** \u00b7 [project thread](https://claude.ai/code/project/x)_",
                     '<!-- claude-projects-attribution: {"github_login":"someone"} -->'):
            self.assertEqual(rt.tool_footers("Fixes #1\n\n" + line), [line], line)

    def test_ignores_declaration_and_comments(self):
        text = (body(ai="agent-generated", tool="Claude Code") + "<!-- Generated by Claude Code -->\nGenerated the docs with Gradle\n"
                "- The check rejects AI `Co-Authored-By` lines, session links and Claude project attribution.\n"
                "- Footers such as \"Made with Cursor\" or \"Generated by Claude Code\" fail the check.\n")
        self.assertEqual(rt.tool_footers(text), [])

    def test_template_has_none(self):
        self.assertEqual(rt.tool_footers(TEMPLATE_BODY), [])

    def test_compute_reports_footers(self):
        self.assertEqual(len(rt.compute([], set(), "x\n---\n_Generated by [Claude Code](https://claude.ai/code)_", EMPTY)["footers"]), 1)


class RelabelledTest(unittest.TestCase):
    def test_reviewer_label_wins(self):
        events = [labeled("risk-tier: T1", "github-actions[bot]"), labeled("risk-tier: T2", "micronaut-reviewer[bot]")]
        self.assertEqual(rt.relabelled(events, {"risk-tier: T1", "risk-tier: T2"}, rt.TIER_LABELS), "T2")

    def test_lowering_is_allowed(self):
        events = [labeled("risk-tier: T2", "github-actions[bot]"), labeled("risk-tier: T1", "alvarosanchez")]
        self.assertEqual(rt.relabelled(events, {"risk-tier: T1"}, rt.TIER_LABELS), "T1")

    def test_own_label_is_not_a_relabel(self):
        self.assertIsNone(rt.relabelled([labeled("risk-tier: T2", "github-actions[bot]")], {"risk-tier: T2"},
                                        rt.TIER_LABELS))

    def test_last_labeled_event_counts(self):
        events = [labeled("risk-tier: T2", "alvarosanchez"), labeled("risk-tier: T2", "github-actions[bot]")]
        self.assertIsNone(rt.relabelled(events, {"risk-tier: T2"}, rt.TIER_LABELS))

    def test_removed_label_is_ignored(self):
        self.assertIsNone(rt.relabelled([labeled("risk-tier: T2", "alvarosanchez")], set(), rt.TIER_LABELS))

    def test_most_recent_relabel_wins(self):
        events = [labeled("risk-tier: T2", "alvarosanchez"), labeled("risk-tier: T0", "sdelamo")]
        self.assertEqual(rt.relabelled(events, {"risk-tier: T0", "risk-tier: T2"}, rt.TIER_LABELS), "T0")

    def test_ai_use_relabel(self):
        events = [labeled("ai-use: agent-generated", "graemerocher")]
        self.assertEqual(rt.relabelled(events, {"ai-use: agent-generated"}, rt.AI_LABELS), "agent-generated")

    def test_label_names(self):
        self.assertEqual(rt.TIER_LABELS["T0"], "risk-tier: T0")
        self.assertEqual(rt.AI_LABELS["agent-generated"], "ai-use: agent-generated")


class FakeGitHub:
    def __init__(self, existing):
        self.existing = existing
        self.added, self.removed = [], []

    def label_exists(self, name):
        return name in self.existing

    def add_label(self, number, name):
        self.added.append(name)

    def remove_label(self, number, name):
        self.removed.append(name)


class SyncLabelsTest(unittest.TestCase):
    MANAGED = {"risk-tier: T0", "risk-tier: T1", "risk-tier: T2"}

    def test_replaces_tier(self):
        github = FakeGitHub(self.MANAGED)
        warnings = rt.sync_labels(github, 1, {"risk-tier: T0", "type: bug"}, {"risk-tier: T2"}, self.MANAGED)
        self.assertEqual((github.added, github.removed, warnings), (["risk-tier: T2"], ["risk-tier: T0"], []))

    def test_missing_label_is_not_created(self):
        github = FakeGitHub(set())
        warnings = rt.sync_labels(github, 1, set(), {"risk-tier: T1"}, self.MANAGED)
        self.assertEqual(github.added, [])
        self.assertEqual(len(warnings), 1)

    def test_no_change(self):
        github = FakeGitHub(self.MANAGED)
        rt.sync_labels(github, 1, {"risk-tier: T1"}, {"risk-tier: T1"}, self.MANAGED)
        self.assertEqual((github.added, github.removed), ([], []))


if __name__ == "__main__":
    unittest.main()
