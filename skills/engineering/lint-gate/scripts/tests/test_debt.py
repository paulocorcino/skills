"""debt.py: the block that turns a group on with its debt list, and `shrink`, which holds it."""

from __future__ import annotations

import unittest

from harness import ScriptCase


class Writers(ScriptCase):
    def setUp(self) -> None:
        super().setUp()
        self.script("tally.py", "ruff", "ruff.json", "--json", "ruff.t.json")
        self.script("tally.py", "clippy", "clippy.prod.json", "--json", "prod.json")
        self.script("tally.py", "clippy", "clippy.all.json", "--json", "all.json")
        self.script("tally.py", "oxlint", "oxlint.json", "--json", "oxlint.t.json")
        self.script("tally.py", "golangci", "golangci.json", "--json", "go.t.json")

    def test_ruff_lists_each_code_with_sites_under_its_count(self) -> None:
        ran = self.script("debt.py", "ruff", "--sites", "ruff.t.json", "--plan", "docs/plan.md")
        self.assertEqual(ran.code, 0)
        self.assertIn('  # debt: 2 sites\n  "C901",', ran.out)
        self.assertIn("debt that docs/plan.md", ran.out)
        self.assertIn("3 codes in debt (4 sites), 0 noise", ran.err)

    def test_a_tallys_own_mark_is_no_rule(self) -> None:
        ran = self.script("debt.py", "ruff", "--sites", "ruff.t.json")
        self.assertNotIn("syntax error", ran.out)

    def test_mypy_names_the_codes_to_take_out_of_enable_error_code(self) -> None:
        ran = self.script(
            "debt.py", "mypy", "--sites", "tally-record.json", "--enabled", "T201,other"
        )
        self.assertIn("    # debt: 3 sites\n    T201,", ran.out)
        self.assertIn("remove from enable_error_code", ran.err)
        self.assertTrue(ran.err.strip().splitlines()[0].endswith(": T201"))

    def test_clippy_turns_a_group_on_with_its_debt_and_noise(self) -> None:
        ran = self.script(
            "debt.py", "clippy", "--help-list", "clippy-help.txt",
            "--sites", "prod.json", "all.json", "--noise", "noise.json",
            "--groups", "clippy::pedantic,rust_2018_idioms",
            "--target", "clippy::unwrap_used,clippy::dbg_macro,unsafe_code",
        )  # fmt: skip
        rust, clippy = ran.out.split("[workspace.lints.clippy]")
        self.assertIn('rust_2018_idioms = { level = "deny", priority = -1 }', rust)
        self.assertIn('unsafe_code = "deny"', rust)
        self.assertIn('# noise: fires on every pure fn\nmust_use_candidate = "allow"', clippy)
        self.assertIn('# debt: 1 site\nneedless_return = "allow"', clippy)
        self.assertIn('dbg_macro = "deny"', clippy)
        self.assertNotIn("unwrap_used", clippy, "a target lint with sites is the plan's to turn on")

    def test_clippy_fails_on_a_group_the_tool_does_not_list(self) -> None:
        ran = self.script(
            "debt.py", "clippy", "--help-list", "clippy-help.txt", "--sites", "prod.json",
            "--groups", "clippy::nope",
        )  # fmt: skip
        self.assertEqual(ran.code, 1)
        self.assertIn("no group clippy::nope", ran.err)

    def test_oxlint_counts_what_a_new_plugin_and_category_bring(self) -> None:
        ran = self.script(
            "debt.py", "oxlint", "--rules", "oxlint-rules.json", "--config", "oxlintrc.json",
            "--sites", "oxlint.t.json", "--plugins", "unicorn", "--categories", "restriction",
            "--target", "no-debugger,no-console",
        )  # fmt: skip
        self.assertIn('"plugins": ["typescript", "unicorn"],', ran.out)
        self.assertIn('// debt: 1 site\n"no-console": "off",', ran.out)
        self.assertIn('// debt: 1 site\n"typescript/no-explicit-any": "off",', ran.out)
        self.assertIn("6 rules come on: 4 with no site, 2 debt (2 sites), 0 noise", ran.err)

    def oxlint(self, config: str, *more: str) -> tuple[str, str]:
        self.write("rc.json", config)
        ran = self.script(
            "debt.py", "oxlint", "--rules", "oxlint-rules.json", "--config", "rc.json",
            "--sites", "oxlint.t.json", *more,
        )  # fmt: skip
        self.assertEqual(ran.code, 0, ran.err)
        return ran.out, ran.err

    def test_oxlint_keeps_a_rule_the_config_sets_at_error_or_off(self) -> None:
        out, _ = self.oxlint(
            '{"rules": {"no-console": "off", "no-debugger": ["error"]}}',
            "--target", "no-console,no-debugger",
        )  # fmt: skip
        self.assertNotIn("no-console", out)
        self.assertNotIn("no-debugger", out)

    def test_oxlint_raises_a_rule_set_at_warn(self) -> None:
        out, err = self.oxlint(
            '{"rules": {"no-alert": ["warn", {"x": 1}], "no-console": 1}}', "--plan", "plan.md"
        )
        self.assertIn('"no-alert": ["error", {"x": 1}],', out)
        self.assertIn('// debt: 1 site\n"no-console": "off",', out)
        self.assertIn("each line replaced by the block's: no-alert, no-console", err)

    def test_oxlint_keeps_the_options_of_a_warn_rule_that_waits_as_debt(self) -> None:
        out, _ = self.oxlint('{"rules": {"no-console": ["warn", {"allow": ["error"]}]}}')
        self.assertIn(
            '// debt: 1 site; was ["warn", {"allow": ["error"]}]\n"no-console": "off",', out
        )
        self.write("rc.json", "{\n" + out.split("\n\n", 1)[1] + "\n}")
        held = self.script("debt.py", "shrink", "rc.json", "rc.json")
        self.assertIn("1 debt entries (1 sites)", held.out, "shrink reads a comment with a note")

    def test_oxlint_counts_the_rules_of_a_category_at_warn(self) -> None:
        out, err = self.oxlint('{"plugins": ["typescript"], "categories": {"restriction": "warn"}}')
        self.assertIn('"categories": {"restriction": "error"},', out)
        self.assertIn('// debt: 1 site\n"typescript/no-explicit-any": "off",', out)
        self.assertIn("4 rules come on: 2 with no site, 2 debt (2 sites)", err)

    def test_oxlint_takes_the_options_of_the_draft(self) -> None:
        self.write(
            "draft.json",
            '{"rules": {"no-console": ["error", {"allow": ["error"]}],'
            ' "typescript/no-namespace": ["error", {"allowDeclarations": true}]}}',
        )
        out, _ = self.oxlint(
            '{"plugins": ["typescript"]}', "--categories", "restriction", "--draft", "draft.json"
        )
        self.assertIn('"typescript/no-namespace": ["error", {"allowDeclarations": true}],', out)
        self.assertIn('// debt: 1 site; its options are in draft.json\n"no-console": "off",', out)
        self.assertNotIn("no-alert", out, "a rule its category turns on needs no line")

    def test_oxlint_fails_on_a_target_rule_the_tool_does_not_list(self) -> None:
        ran = self.script(
            "debt.py", "oxlint", "--rules", "oxlint-rules.json", "--config", "oxlintrc.json",
            "--sites", "oxlint.t.json", "--target", "no-zzz",
        )  # fmt: skip
        self.assertEqual(ran.code, 1)
        self.assertIn("unknown --target rules: eslint/no-zzz", ran.err)

    def test_golangci_by_id_keeps_a_linter_on_and_lists_its_checks(self) -> None:
        ran = self.script("debt.py", "golangci", "--sites", "go.t.json", "--by-id", "gosec")
        disable, settings = ran.out.split("  settings:")
        self.assertIn("    # debt: 1 site\n    - errcheck", disable)
        self.assertNotIn("gosec", disable)
        self.assertIn(
            "    gosec:\n      excludes:\n        # debt: 1 site\n        - G104", settings
        )

    def test_golangci_by_id_takes_only_the_linters_it_knows(self) -> None:
        ran = self.script("debt.py", "golangci", "--sites", "go.t.json", "--by-id", "revive")
        self.assertEqual(ran.code, 2)


class Shrink(ScriptCase):
    def shrink(self, base: str, head: str, *more: str) -> tuple[int, str]:
        ran = self.script("debt.py", "shrink", base, head, *more)
        return ran.code, ran.out

    def test_the_same_list_passes(self) -> None:
        code, out = self.shrink("cargo-base.toml", "cargo-base.toml")
        self.assertEqual(code, 0)
        self.assertIn("2 debt entries (15 sites), 0 gone since the base", out)

    def test_a_list_that_shrank_passes(self) -> None:
        code, out = self.shrink("cargo-base.toml", "cargo-shrunk.toml")
        self.assertEqual(code, 0)
        self.assertIn("1 debt entries (9 sites), 1 gone since the base", out)

    def test_growth_fails_and_names_each_kind(self) -> None:
        code, out = self.shrink("cargo-base.toml", "cargo-grown.toml", "--plan", "plan.md")
        self.assertEqual(code, 1)
        self.assertIn("debt grew: doc_markdown 12 -> 14", out)
        self.assertIn("new debt entry: unwrap_used (2)", out)
        self.assertIn("new entry with no `debt:` or `noise:` comment: similar_names", out)
        self.assertIn("new noise entry: if_not_else (taste)", out)

    def test_a_new_noise_entry_passes_when_the_plan_records_its_decision(self) -> None:
        _, out = self.shrink("cargo-base.toml", "cargo-grown.toml", "--plan", "plan.md")
        self.assertNotIn("items_after_statements", out)
        _, out = self.shrink("cargo-base.toml", "cargo-grown.toml")
        self.assertIn("new noise entry: items_after_statements", out)

    def test_a_list_of_members_is_no_debt_list(self) -> None:
        _, out = self.shrink("cargo-base.toml", "cargo-grown.toml")
        self.assertNotIn("crates/a", out)

    def test_the_first_list_passes(self) -> None:
        code, out = self.shrink("no-such-file.toml", "cargo-base.toml")
        self.assertEqual(code, 0)
        self.assertIn("this change brings the first one, 2 entries (15 sites), 1 noise", out)

    def test_a_debt_comment_tied_to_no_entry_fails(self) -> None:
        code, out = self.shrink("cargo-base.toml", "cargo-unread.toml")
        self.assertEqual(code, 1)
        self.assertIn("1 `debt:` comments are tied to no entry", out)

    def test_every_config_form_is_read(self) -> None:
        forms = {
            "ruff-debt.toml": "2 debt entries (12 sites)",
            "golangci-debt.yml": "1 debt entries (4 sites)",
            "mypy-debt.ini": "1 debt entries (6 sites)",
            "oxlint-debt.json": "2 debt entries (3 sites)",
        }
        for config, summary in forms.items():
            with self.subTest(config):
                code, out = self.shrink(config, config)
                self.assertEqual(code, 0)
                self.assertIn(summary, out)


if __name__ == "__main__":
    unittest.main()
