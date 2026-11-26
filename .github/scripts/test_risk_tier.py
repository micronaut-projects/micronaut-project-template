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

    def test_state_fits_the_total_limit(self):
        files = [{"filename": f"module{i}/src/main/java/io/micronaut/some/long/package/name/Class{i}.java",
                  "status": "modified", "additions": 400, "deletions": 0,
                  "patch": "@@ -1 +1 @@\n" + "\n".join(f'+    String s{j} = "\\"quoted\\" {j}";' for j in range(400))}
                 for i in range(300)]
        state = rt.jev_state("t", "x" * 10000, set(), files, EMPTY)
        self.assertLessEqual(len(json.dumps(state)), rt.JEV_MAX_STATE)
        self.assertTrue(state["changed_files"])
        self.assertIn("main_source_diff_note", state)
        small = rt.jev_state("t", "b", set(), files[:1], EMPTY)
        self.assertNotIn("main_source_diff_note", small)
        self.assertEqual(len(small["changed_files"]), 1)

    def test_tier_rules_are_always_t2(self):
        loose = rt.merge_rules(EMPTY, {"tiers": {"T2": {"paths": []}, "T0": {"paths": [".github/**"]}}})
        for path in rt.CLASSIFIER_PATHS:
            self.assertEqual(rt.file_tier(path, loose), "T2", path)
        result = rt.compute([".github/risk-tiers.toml"], set(), "", loose, jev("T0", t0=1.0))
        self.assertEqual(result["tier"], "T2")
        self.assertEqual(rt.file_tier(".github/workflows/ci.yml", loose), "T2")
        self.assertEqual(rt.file_tier(".github/ISSUE_TEMPLATE/bug.yaml", loose), "T0")

    def test_relabelling_cannot_lower_rule_changes(self):
        def fresh(paths):
            return rt.compute(paths, set(), "", EMPTY, jev("T2", t2=1.0))
        rules_change = fresh([".github/risk-tiers.toml"])
        self.assertEqual(rt.apply_override(rules_change, "T0", [".github/risk-tiers.toml"])["tier"], "T2")
        self.assertIn("ignored", rules_change["reasons"][-1])
        other = fresh(["a/src/main/A.java"])
        self.assertEqual(rt.apply_override(other, "T0", ["a/src/main/A.java"])["tier"], "T0")
        renamed = fresh(["x.toml"])
        self.assertEqual(rt.apply_override(renamed, "T1", ["x.toml", ".github/workflows/risk-tier.yml"])["tier"], "T2")

    def test_only_write_access_may_lower(self):
        def fresh():
            return rt.compute(["a/src/main/A.java"], set(), "", EMPTY, jev("T2", t2=1.0))
        self.assertEqual(rt.apply_override(fresh(), "T0", ["a/src/main/A.java"], may_lower=False)["tier"], "T2")
        self.assertEqual(rt.apply_override(fresh(), "T0", ["a/src/main/A.java"], may_lower=True)["tier"], "T0")
        raised = rt.compute(["README.md"], set(), "", EMPTY, jev("T0", t0=1.0))
        self.assertEqual(rt.apply_override(raised, "T2", ["README.md"], may_lower=False)["tier"], "T2")
        workflow = fresh()
        self.assertEqual(rt.apply_override(workflow, "T0", [".github/workflows/ci.yml"])["tier"], "T2")

    def test_relabel_actor_and_permission(self):
        events = [{"event": "labeled", "label": {"name": "risk-tier: T0"}, "actor": {"login": "a"}},
                  {"event": "labeled", "label": {"name": "risk-tier: T0"}, "actor": {"login": "b"}}]
        self.assertEqual(rt.relabel_actor(events, {"risk-tier: T0"}, "risk-tier: T0"), "b")
        self.assertIsNone(rt.relabel_actor(events, set(), "risk-tier: T0"))

        class Fake(rt.GitHub):
            def request(self, method, path, data=None):
                if "nobody" in path:
                    raise rt.urllib.error.HTTPError(path, 404, "missing", {}, None)
                return {"permission": "write", "role_name": "maintain"}, ""
        github = Fake(None, "o/r")
        self.assertEqual(github.permission("someone"), "maintain")
        self.assertEqual(github.permission("nobody"), "none")
        self.assertEqual(github.permission(None), "none")

    def test_bot_authors(self):
        self.assertEqual(rt.bot_author({"login": "renovate[bot]", "type": "Bot"}, EMPTY), "renovate[bot]")
        self.assertEqual(rt.bot_author({"login": "dependabot[bot]"}, EMPTY), "dependabot[bot]")
        self.assertEqual(rt.bot_author({"login": "micronaut-build", "type": "User"}, EMPTY), "micronaut-build")
        self.assertIsNone(rt.bot_author({"login": "graemerocher", "type": "User"}, EMPTY))

    def test_version_update(self):
        self.assertEqual(rt.version_update("4.2.19.Final", "4.2.20.Final"), "patch")
        self.assertEqual(rt.version_update("9.7.1", "9.8.0"), "minor")
        self.assertEqual(rt.version_update("v5", "v6"), "major")
        self.assertEqual(rt.version_update("5.0.0-M1", "5.0.0-M2"), "patch")
        self.assertEqual(rt.version_update("1.2", "1.2.1"), "patch")
        self.assertEqual(rt.version_update("3e5f45b", "9000827"), "digest")
        self.assertIsNone(rt.version_update("latest", "stable"))

    RENOVATE_CHANGE = """This PR contains the following updates:

| Package | Change | [Age](https://x) | [Confidence](https://x) |
|---|---|---|---|
| [io.netty:netty-handler](https://netty.io) | `4.2.19.Final` → `4.2.20.Final` | ![age](https://x) | ![c](https://x) |
| [io.netty:netty-codec](https://netty.io) | `4.2.19.Final` -> `4.3.0.Final` | ![age](https://x) | ![c](https://x) |

---

| Not | Change |
|---|---|
| ignored | `1` → `9` |
"""
    RENOVATE_UPDATE = """This PR contains the following updates:

| Package | Type | Update | Change |
|---|---|---|---|
| [actions/setup-java](https://x) | action | major | `v5` → `v6` |
"""

    def test_renovate_tier(self):
        self.assertEqual(rt.renovate_updates(self.RENOVATE_CHANGE), ["patch", "minor"])
        self.assertEqual(rt.renovate_tier(self.RENOVATE_CHANGE, EMPTY), ("T1", "Renovate 2 updates: minor, patch"))
        self.assertEqual(rt.renovate_tier(self.RENOVATE_UPDATE, EMPTY), ("T2", "Renovate update: major"))
        digest = self.RENOVATE_UPDATE.replace("major", "digest").replace("`v5` → `v6`", "`3e5f45b` → `9000827`")
        self.assertEqual(rt.renovate_tier(digest, EMPTY)[0], "T0")
        self.assertEqual(rt.renovate_tier(self.RENOVATE_UPDATE.replace("major", "replacement"), EMPTY)[0], "T2")
        self.assertIsNone(rt.renovate_tier("Nothing to see", EMPTY))

    def test_bots_skip_jev(self):
        def fail(*args, **kwargs):
            raise AssertionError("Jev must not be asked")
        original, rt.ask_jev = rt.ask_jev, fail
        try:
            files = [{"filename": "gradle/libs.versions.toml"}]
            renovate = rt.classify({"user": {"login": "renovate[bot]", "type": "Bot"}, "body": self.RENOVATE_UPDATE.replace("major", "patch")},
                                   set(), files, EMPTY)
            self.assertEqual((renovate["tier"], renovate["bot"]), ("T0", "renovate[bot]"))
            major = rt.classify({"user": {"login": "renovate[bot]"}, "body": self.RENOVATE_UPDATE}, set(),
                                [{"filename": ".github/workflows/ci.yml"}], EMPTY)
            self.assertEqual(major["tier"], "T2")
            sync = rt.classify({"user": {"login": "micronaut-build"}, "body": "Update common files"}, set(),
                               [{"filename": ".github/workflows/ci.yml"}, {"filename": "gradlew"}], EMPTY)
            self.assertEqual(sync["tier"], "T2")
            docs = rt.classify({"user": {"login": "micronaut-build"}, "body": "Update common files"}, set(),
                               [{"filename": "MAINTAINING.md"}, {"filename": ".github/PULL_REQUEST_TEMPLATE.md"}], EMPTY)
            self.assertEqual(docs["tier"], "T0")
            unreadable = rt.classify({"user": {"login": "renovate[bot]"}, "body": "no table"}, set(), files, EMPTY)
            self.assertEqual(unreadable["tier"], "T1")
            kept = rt.classify({"user": {"login": "someone"}, "body": ""}, set(), files, EMPTY, previous="T1")
            self.assertEqual(kept["tier"], "T1")
            self.assertIn("nothing Jev reads changed", kept["reasons"][0])
        finally:
            rt.ask_jev = original

    def test_cached_answer_is_reused_while_the_fingerprint_matches(self):
        calls, sleeps = [], []
        original_ask, original_sleep = rt.ask_jev, rt.time.sleep
        rt.ask_jev = lambda *args, **kwargs: calls.append(1) or jev("T1", t1=1.0)
        rt.time.sleep = sleeps.append
        try:
            pr = {"user": {"login": "someone"}, "title": "Fix", "body": "Body <!-- hidden -->"}
            files = [{"filename": "a/src/main/java/A.java", "patch": "+x"}]
            first = rt.classify(pr, set(), files, EMPTY, wait=180)
            self.assertEqual((first["tier"], len(calls), sleeps), ("T1", 1, [180]))
            cache = first["cache"]
            pushed = [{"filename": "a/src/main/java/A.java", "patch": "+y"}]
            again = rt.classify(dict(pr, body="Body"), set(), pushed, EMPTY, cache=cache, wait=180)
            self.assertEqual((again["tier"], len(calls), sleeps), ("T1", 1, [180]))
            self.assertIn("not asked again", again["reasons"][0])
            self.assertNotIn("cache", again)
            rt.classify(pr, set(), pushed + [{"filename": "b/B.java"}], EMPTY, cache=cache)
            rt.classify(dict(pr, title="Other"), set(), pushed, EMPTY, cache=cache)
            self.assertEqual(len(calls), 3)
        finally:
            rt.ask_jev, rt.time.sleep = original_ask, original_sleep

    def test_last_state_only_trusts_this_workflow(self):
        import io as _io, zipfile as _zip
        def archive(answer):
            buffer = _io.BytesIO()
            with _zip.ZipFile(buffer, "w") as zipped:
                zipped.writestr("state.json", json.dumps({"fingerprint": "f", "answer": answer}))
            return buffer.getvalue()

        class Fake(rt.GitHub):
            def __init__(self, artifacts, runs):
                super().__init__(None, "o/r")
                self.artifacts, self.runs = artifacts, runs

            def request(self, method, path, data=None):
                if path.startswith("actions/artifacts?name=risk-tier-state-7"):
                    return {"artifacts": self.artifacts}, ""
                return self.runs[int(path.rsplit("/", 1)[1])], ""

            def download(self, url):
                return archive(url)

        artifacts = [
            {"created_at": "2026-11-26T12:00:00Z", "workflow_run": {"id": 1}, "archive_download_url": "good"},
            {"created_at": "2026-11-26T13:00:00Z", "workflow_run": {"id": 2}, "archive_download_url": "forged"},
            {"created_at": "2026-11-26T14:00:00Z", "workflow_run": {"id": 3}, "archive_download_url": "old", "expired": True},
        ]
        runs = {1: {"event": "pull_request_target", "path": ".github/workflows/risk-tier.yml"},
                2: {"event": "pull_request", "path": ".github/workflows/risk-tier.yml"},
                3: {"event": "pull_request_target", "path": ".github/workflows/risk-tier.yml"}}
        self.assertEqual(Fake(artifacts, runs).last_state(7)["answer"], "good")
        self.assertIsNone(Fake(artifacts[1:2], runs).last_state(7))
        self.assertIsNone(Fake([], runs).last_state(7))

    def test_debounce_is_validated(self):
        with self.assertRaisesRegex(ValueError, "debounce_seconds"):
            rt.validate_rules(rt.merge_rules(EMPTY, {"jev": {"debounce_seconds": -1}}))
        self.assertEqual(EMPTY["jev"]["debounce_seconds"], 180)

    def test_input_unchanged(self):
        self.assertTrue(rt.input_unchanged({"action": "labeled", "label": {"name": "risk-tier: T1"}}, EMPTY))
        self.assertFalse(rt.input_unchanged({"action": "unlabeled", "label": {"name": "type: breaking"}}, EMPTY))
        self.assertFalse(rt.input_unchanged({"action": "ready_for_review"}, EMPTY))
        self.assertTrue(rt.input_unchanged({"action": "edited", "changes": {"base": {}}}, EMPTY))
        self.assertFalse(rt.input_unchanged({"action": "edited", "changes": {"body": {}}}, EMPTY))
        self.assertFalse(rt.input_unchanged({"action": "synchronize"}, EMPTY))
        self.assertFalse(rt.input_unchanged({"action": "opened"}, EMPTY))

    def test_workflow_tier(self):
        events = [{"event": "labeled", "label": {"name": "risk-tier: T1"}, "actor": {"login": rt.WORKFLOW_ACTOR}},
                  {"event": "labeled", "label": {"name": "risk-tier: T2"}, "actor": {"login": "sdelamo"}}]
        self.assertEqual(rt.workflow_tier(events, {"risk-tier: T1"}), "T1")
        self.assertIsNone(rt.workflow_tier(events, {"risk-tier: T2"}))
        self.assertIsNone(rt.workflow_tier([], set()))

    def test_questions_use_the_descriptions(self):
        rules = rt.merge_rules(EMPTY, {"tiers": {"T0": {"description": "Docs only."}}})
        questions = rt.jev_questions(rules)
        self.assertEqual(questions["tier"]["criteria"]["T0"], "Docs only.")
        self.assertIn(EMPTY["public_api"]["description"], questions["public_api"]["instructions"])
        self.assertEqual(questions["breaking"]["type"], "noul")


class FileTierTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(rt.file_tier("src/main/docs/guide/index.adoc", EMPTY), "T0")
        self.assertEqual(rt.file_tier(".github/workflows/gradle.yml", EMPTY), "T2")
        self.assertEqual(rt.file_tier(".github/release.yml", EMPTY), "T0")
        self.assertEqual(rt.file_tier("test-suite-kotlin/src/main/kotlin/A.kt", EMPTY), "T0")
        self.assertEqual(rt.file_tier("gradlew", EMPTY), "T2")
        self.assertEqual(rt.file_tier("module/src/main/java/A.java", EMPTY), "T1")
        self.assertEqual(rt.file_tier("module/build.gradle", EMPTY), "T1")

    def test_version_catalog_is_t1(self):
        self.assertEqual(rt.file_tier("gradle/libs.versions.toml", EMPTY), "T1")
        self.assertEqual(rt.file_tier("gradle/wrapper/gradle-wrapper.properties", EMPTY), "T2")
        self.assertEqual(rt.file_tier("buildSrc/src/main/groovy/x.gradle", EMPTY), "T2")
        self.assertEqual(rt.file_tier("settings.gradle", EMPTY), "T2")

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
        result = rt.compute(["README.md"], set(), body(tier="T0"), EMPTY, jev("T0", t0=0.9, t1=0.1))
        self.assertEqual(result["tier"], "T0")

    def test_path_rules_are_a_floor(self):
        result = rt.compute(["a/src/main/A.java"], set(), body(tier="T1"), EMPTY, jev("T0", t0=0.95, t1=0.05))
        self.assertEqual(result["tier"], "T1")
        self.assertIn("raised to T1 by the path rules", result["reasons"][-1])
        self.assertEqual(rt.compute(["a/src/main/A.java"], set(), "", EMPTY, jev("T2", t2=1.0))["tier"], "T2")
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
        self.assertEqual(state["t2_areas"], rt.tier_paths(CORE, "T2"))
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


class ReviewPolicyTest(unittest.TestCase):
    CODEOWNERS = rt.parse_codeowners("""
# Core
inject/src/main/**   @graemerocher @dstepanov
http*/src/main/**    @graemerocher @dstepanov @yawkat
http/src/main/java/io/micronaut/http/internal/
docs/** @micronaut-projects/docs
""")

    def test_global_review_rules(self):
        policy = rt.review_rules(EMPTY)
        self.assertEqual(len(policy["maintainers"]), 5)
        self.assertFalse(policy["enforce"])
        self.assertTrue(rt.review_rules(rt.merge_rules(EMPTY, {"review": {"enforce": True}}))["enforce"])

    def test_invalid_review_rules(self):
        with self.assertRaises(ValueError):
            rt.review_rules({"review": {"enforce": "yes"}})
        with self.assertRaises(ValueError):
            rt.review_rules({"review": {"maintainers": "sdelamo"}})

    def test_last_matching_codeowners_pattern_wins(self):
        self.assertEqual(rt.owners_of("inject/src/main/java/A.java", self.CODEOWNERS), ["graemerocher", "dstepanov"])
        self.assertEqual(rt.owners_of("http-client/src/main/A.java", self.CODEOWNERS),
                         ["graemerocher", "dstepanov", "yawkat"])
        self.assertEqual(rt.owners_of("http/src/main/java/io/micronaut/http/internal/X.java", self.CODEOWNERS), [])
        self.assertEqual(rt.owners_of("inject/src/test/A.java", self.CODEOWNERS), [])
        self.assertEqual(rt.owners_of("docs/guide.adoc", self.CODEOWNERS), ["micronaut-projects/docs"])

    def test_directory_patterns_own_everything_below(self):
        entries = rt.parse_codeowners("/inject @Graemerocher\nhttp/src @Yawkat\n")
        self.assertEqual(rt.owners_of("inject/src/main/A.java", entries), ["graemerocher"])
        self.assertEqual(rt.owners_of("http/src/main/A.java", entries), ["yawkat"])
        self.assertEqual(rt.owners_of("injector/A.java", entries), [])

    def test_logins_compare_case_insensitively(self):
        entries = rt.parse_codeowners("http/** @Yawkat\n")
        approvers = set(rt.latest_reviews([{"user": {"login": "YawKat"}, "state": "APPROVED"}], "x"))
        self.assertTrue(rt.review_verdict("T2", ["http/A.java"], entries, approvers, set())[0])

    def test_root_codeowners_is_t2(self):
        self.assertEqual(rt.file_tier("CODEOWNERS", EMPTY), "T2")
        self.assertEqual(rt.file_tier("docs/CODEOWNERS", EMPTY), "T2")
        self.assertEqual(rt.file_tier("project/CODEOWNERS", EMPTY), "T1")

    def test_global_renovate_rules_are_t2(self):
        self.assertEqual(rt.file_tier(".github/renovate-global.json", EMPTY), "T2")

    def test_latest_review_per_person_counts(self):
        reviews = [
            {"user": {"login": "sdelamo"}, "state": "CHANGES_REQUESTED"},
            {"user": {"login": "sdelamo"}, "state": "COMMENTED"},
            {"user": {"login": "sdelamo"}, "state": "APPROVED"},
            {"user": {"login": "yawkat"}, "state": "APPROVED"},
            {"user": {"login": "yawkat"}, "state": "DISMISSED"},
            {"user": {"login": "author"}, "state": "APPROVED"},
            {"user": {"login": "copilot-pull-request-reviewer[bot]", "type": "Bot"}, "state": "CHANGES_REQUESTED"},
        ]
        self.assertEqual(rt.latest_reviews(reviews, "author"), {"sdelamo": "APPROVED"})

    def test_t0_needs_nobody(self):
        self.assertTrue(rt.review_verdict("T0", ["README.md"], [], set(), set())[0])

    def test_no_tier_waits(self):
        self.assertFalse(rt.review_verdict(None, ["README.md"], [], {"sdelamo"}, set())[0])

    def test_t1_needs_one_approval(self):
        self.assertFalse(rt.review_verdict("T1", ["a/src/main/A.java"], [], set(), set())[0])
        self.assertTrue(rt.review_verdict("T1", ["a/src/main/A.java"], [], {"sdelamo"}, set())[0])

    def test_changes_requested_blocks(self):
        passed, reasons = rt.review_verdict("T0", ["README.md"], [], {"sdelamo"}, {"yawkat"})
        self.assertFalse(passed)
        self.assertIn("yawkat", reasons[0])

    def test_t2_needs_an_owner_of_each_owned_area(self):
        paths = ["inject/src/main/A.java", "http-netty/src/main/B.java"]
        self.assertFalse(rt.review_verdict("T2", paths, self.CODEOWNERS, {"sdelamo"}, set())[0])
        passed, reasons = rt.review_verdict("T2", paths, self.CODEOWNERS, {"yawkat"}, set())
        self.assertFalse(passed)
        self.assertTrue(any("graemerocher or dstepanov" in reason for reason in reasons))
        self.assertTrue(rt.review_verdict("T2", paths, self.CODEOWNERS, {"dstepanov"}, set())[0])

    def test_t2_without_codeowners_needs_any_maintainer(self):
        self.assertTrue(rt.review_verdict("T2", ["inject/src/main/A.java"], [], {"sdelamo"}, set())[0])

    def test_team_owners_accept_any_approval(self):
        self.assertTrue(rt.review_verdict("T2", ["docs/guide.adoc"], self.CODEOWNERS, {"sdelamo"}, set())[0])

    def test_pick_reviewer_balances_and_rotates(self):
        self.assertEqual(rt.pick_reviewer(["a", "b", "c"], {"a": 3, "b": 1, "c": 2}, 7), "b")
        self.assertEqual({rt.pick_reviewer(["a", "b"], {}, n) for n in (1, 2)}, {"a", "b"})
        self.assertIsNone(rt.pick_reviewer([], {}, 1))

    def test_unowned_t2_files(self):
        self.assertEqual(rt.unowned_t2_files(["inject/src/main/A.java", "router/src/main/R.java"],
                                             rt.merge_rules(EMPTY, {"tiers": {"T2": {"paths": [
                                                 "inject/src/main/**", "router/src/main/**"]}}}), self.CODEOWNERS),
                         ["router/src/main/R.java"])


class FakeReviewGitHub:
    def __init__(self, pull_request, reviews, files, load=None):
        self.pull_request, self.reviews, self.files, self.load = pull_request, reviews, files, load or {}
        self.api_url = "https://api.github.com"
        self.posts = []

    def request(self, method, path, data=None):
        if method == "POST":
            self.posts.append((path, data))
            return {}, ""
        if "search/issues" in path:
            login = path.split("review-requested%3A", 1)[1].split("%20", 1)[0]
            return {"total_count": self.load.get(login, 0)}, ""
        return self.pull_request, ""

    def paginate(self, path):
        return self.reviews

    def changed_files(self, number):
        return [{"filename": name} for name in self.files]

    def permission(self, login):
        return "write" if login == "committer" else "read"


class RunReviewTest(unittest.TestCase):
    def run_review(self, github, enforce, request=True, tier="T1"):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            event_path = os.path.join(directory, "event.json")
            with open(event_path, "w") as event_file:
                json.dump({"pull_request": {"number": 7}}, event_file)
            repository_rules = os.path.join(directory, "risk-tiers.toml")
            with open(repository_rules, "w") as rules_file:
                rules_file.write(f"[review]\nenforce = {'true' if enforce else 'false'}\n")
            github.pull_request.setdefault("labels", [{"name": f"risk-tier: {tier}"}])
            original, rt.GitHub = rt.GitHub, lambda *args: github
            environment = dict(os.environ)
            os.environ.update({"GITHUB_EVENT_PATH": event_path, "GITHUB_REPOSITORY": "micronaut-projects/x"})
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            cwd = os.getcwd()
            os.chdir(directory)
            try:
                args = ["--rules", _GLOBAL, "--repository-rules", repository_rules, "review"]
                return rt.main(args + (["--request"] if request else []))
            finally:
                os.chdir(cwd)
                rt.GitHub = original
                os.environ.clear()
                os.environ.update(environment)

    def test_requests_least_loaded_maintainer_and_fails(self):
        github = FakeReviewGitHub({"user": {"login": "sdelamo"}, "requested_reviewers": [], "requested_teams": []},
                                  [], ["a/src/main/A.java"],
                                  {"alvarosanchez": 4, "dstepanov": 2, "graemerocher": 9, "yawkat": 5})
        self.assertEqual(self.run_review(github, enforce=True), 1)
        self.assertEqual(github.posts, [("pulls/7/requested_reviewers", {"reviewers": ["dstepanov"]})])

    def test_no_request_when_someone_is_asked(self):
        github = FakeReviewGitHub({"user": {"login": "x"}, "requested_reviewers": [{"login": "yawkat"}],
                                   "requested_teams": []}, [], ["a/src/main/A.java"])
        self.assertEqual(self.run_review(github, enforce=True), 1)
        self.assertEqual(github.posts, [])

    def test_committer_approval_passes(self):
        github = FakeReviewGitHub({"user": {"login": "x"}, "requested_reviewers": [], "requested_teams": []},
                                  [{"user": {"login": "committer"}, "state": "APPROVED"}], ["a/src/main/A.java"])
        self.assertEqual(self.run_review(github, enforce=True), 0)

    def test_outsider_review_does_not_stop_the_request(self):
        github = FakeReviewGitHub({"user": {"login": "x"}, "requested_reviewers": [], "requested_teams": []},
                                  [{"user": {"login": "someone"}, "state": "APPROVED"}], ["a/src/main/A.java"])
        self.assertEqual(self.run_review(github, enforce=True), 1)
        self.assertEqual(len(github.posts), 1)

    def test_reader_approval_does_not_count(self):
        github = FakeReviewGitHub({"user": {"login": "x"}, "requested_reviewers": [], "requested_teams": []},
                                  [{"user": {"login": "someone"}, "state": "APPROVED"}], ["a/src/main/A.java"])
        self.assertEqual(self.run_review(github, enforce=True, request=False), 1)

    def test_not_enforced_reports_only(self):
        github = FakeReviewGitHub({"user": {"login": "x"}, "requested_reviewers": [], "requested_teams": []},
                                  [], ["a/src/main/A.java"])
        self.assertEqual(self.run_review(github, enforce=False), 0)
        self.assertEqual(github.posts, [])


if __name__ == "__main__":
    unittest.main()
