#!/usr/bin/env python3
"""Unit tests for risk-tier.py. Run with: python3 .github/scripts/test_risk_tier.py"""
import importlib.util
import os
import sys
import unittest

sys.dont_write_bytecode = True

_spec = importlib.util.spec_from_file_location(
    "risk_tier", os.path.join(os.path.dirname(os.path.abspath(__file__)), "risk-tier.py"))
rt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rt)

EMPTY = {"t0": [], "t2": []}
CORE = {"t0": [], "t2": ["inject/src/main/**", "core-processor/src/main/**", "http*/src/main/**"]}

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


class TiersFileTest(unittest.TestCase):
    def test_parse(self):
        text = """# T2 paths for micronaut-core
t2:
  - "inject/src/main/**"   # the DI container
  - 'core-processor/src/main/**'
  - http/src/main/**
t0:
  - benchmarks/**
"""
        self.assertEqual(rt.parse_tiers_file(text), {
            "t2": ["inject/src/main/**", "core-processor/src/main/**", "http/src/main/**"],
            "t0": ["benchmarks/**"]})

    def test_empty_list(self):
        self.assertEqual(rt.parse_tiers_file("t0: []\nt2:\n  - a/**\n"), {"t0": [], "t2": ["a/**"]})

    def test_unknown_key(self):
        with self.assertRaises(ValueError):
            rt.parse_tiers_file("t1:\n  - a/**\n")


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
        self.assertEqual(rt.file_tier("benchmarks/A.java", {"t0": ["benchmarks/**"], "t2": []}), "T0")


class DeclarationTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(rt.parse_declaration(body()), {
            "ai_use": "assisted", "ai_tool": "Claude Code", "risk_tier": "T1", "api_change": "no"})

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


def labeled(name, login):
    return {"event": "labeled", "label": {"name": name}, "actor": {"login": login}}


class ToolFooterTest(unittest.TestCase):
    def test_detects_footers(self):
        for line in ("_Generated by [Claude Code](https://claude.ai/code)_",
                     "\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)",
                     "https://claude.ai/code/session_011abc",
                     "Co-Authored-By: Claude Opus <noreply@anthropic.com>",
                     "Made with Cursor",
                     "Generated with Copilot"):
            self.assertEqual(rt.tool_footers("Fixes #1\n\n" + line), [line], line)

    def test_ignores_declaration_and_comments(self):
        text = body(ai="agent-generated", tool="Claude Code") + "<!-- Generated by Claude Code -->\nGenerated the docs with Gradle\n"
        self.assertEqual(rt.tool_footers(text), [])

    def test_template_has_none(self):
        self.assertEqual(rt.tool_footers(TEMPLATE_BODY), [])

    def test_compute_reports_footers(self):
        self.assertEqual(len(rt.compute([], set(), "x\n---\n_Generated by [Claude Code](https://claude.ai/code)_", EMPTY)["footers"]), 1)


class OverrideTierTest(unittest.TestCase):
    def test_reviewer_label_is_an_override(self):
        events = [labeled("tier: T1", "github-actions[bot]"), labeled("tier: T2", "micronaut-reviewer[bot]")]
        self.assertEqual(rt.override_tier(events, {"tier: T1", "tier: T2"}), "T2")

    def test_own_label_is_not_an_override(self):
        self.assertIsNone(rt.override_tier([labeled("tier: T2", "github-actions[bot]")], {"tier: T2"}))

    def test_last_labeled_event_wins(self):
        events = [labeled("tier: T2", "alvarosanchez"), labeled("tier: T2", "github-actions[bot]")]
        self.assertIsNone(rt.override_tier(events, {"tier: T2"}))

    def test_removed_label_is_ignored(self):
        self.assertIsNone(rt.override_tier([labeled("tier: T2", "alvarosanchez")], set()))

    def test_highest_override(self):
        events = [labeled("tier: T0", "alvarosanchez"), labeled("tier: T2", "alvarosanchez")]
        self.assertEqual(rt.override_tier(events, {"tier: T0", "tier: T2"}), "T2")


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
    MANAGED = {"tier: T0", "tier: T1", "tier: T2"}

    def test_replaces_tier(self):
        github = FakeGitHub(self.MANAGED)
        warnings = rt.sync_labels(github, 1, {"tier: T0", "type: bug"}, {"tier: T2"}, self.MANAGED)
        self.assertEqual((github.added, github.removed, warnings), (["tier: T2"], ["tier: T0"], []))

    def test_missing_label_is_not_created(self):
        github = FakeGitHub(set())
        warnings = rt.sync_labels(github, 1, set(), {"tier: T1"}, self.MANAGED)
        self.assertEqual(github.added, [])
        self.assertEqual(len(warnings), 1)

    def test_no_change(self):
        github = FakeGitHub(self.MANAGED)
        rt.sync_labels(github, 1, {"tier: T1"}, {"tier: T1"}, self.MANAGED)
        self.assertEqual((github.added, github.removed), ([], []))


if __name__ == "__main__":
    unittest.main()
