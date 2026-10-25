# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Martinus Verburg
"""Offline regression tests. No AutoPkg processing or UEM connections."""

import importlib.util
import json
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".github/skills/autopkg-workspace-one"
GENERATOR = SKILL / "scripts/new_ws1_recipe.py"
LINTER = SKILL / "scripts/lint_recipes.py"
spec = importlib.util.spec_from_file_location("ws1_recipe_lint", LINTER)
recipe_lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recipe_lint)


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / "recipes with spaces"

    def generate(self, *extra, name="Vendor Example App", app="ExampleApp", prefix="com.github.example"):
        return subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                app,
                "--name",
                name,
                "--identifier-prefix",
                prefix,
                "--out",
                str(self.out),
                *extra,
            ],
            capture_output=True,
            text=True,
        )

    def full_set(self):
        result = self.generate("--parent", "com.github.vendor.munki.ExampleApp")
        self.assertEqual(result.returncode, 0, result.stderr)
        return sorted(self.out.glob("*.recipe.yaml"))

    def test_full_set_namespaces_and_inheritance(self):
        files = self.full_set()
        self.assertEqual(len(files), 3)
        for path in files:
            recipe = recipe_lint.load_recipe(path)
            self.assertEqual(recipe["Input"]["NAME"], "Vendor Example App")
            self.assertEqual(recipe_lint.lint(recipe, ws1=True)[0], [])
            self.assertTrue(recipe["Identifier"].startswith("com.github.example."))
            self.assertTrue(recipe["Process"][0]["Processor"].startswith("com.github.codeskipper."))
            self.assertNotIn("pkginfo", recipe["Input"])
            plistlib.dumps(recipe)
        importer = recipe_lint.load_recipe(self.out / "ExampleApp.ws1.recipe.yaml")
        self.assertEqual(importer["ParentRecipe"], "com.github.vendor.munki.ExampleApp")
        for kind in ("assigner", "pruner"):
            self.assertNotIn("ParentRecipe", recipe_lint.load_recipe(self.out / f"ExampleApp.ws1-{kind}.recipe.yaml"))

    def test_pruner_defaults_are_strings_and_dry_run(self):
        self.full_set()
        recipe = recipe_lint.load_recipe(self.out / "ExampleApp.ws1-pruner.recipe.yaml")
        inputs = recipe["Input"]
        self.assertIsInstance(inputs["WS1_APP_VERSIONS_TO_KEEP"], str)
        self.assertEqual(inputs["WS1_SAFEGUARD_HALT_ON_ASSIGNED"], "1")
        self.assertEqual(inputs["WS1_APP_VERSIONS_PRUNE"], "dry_run")
        self.assertEqual(recipe["Process"][0]["Arguments"]["ws1_app_versions_prune"], "%WS1_APP_VERSIONS_PRUNE%")

    def test_staged_generation_and_no_overwrite(self):
        result = self.generate("--only", "importer", "--parent", "com.github.vendor.munki.ExampleApp")
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.out / "ExampleApp.ws1.recipe.yaml"
        original = path.read_bytes()
        self.full_set()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(len(list(self.out.glob("*.yaml"))), 3)

    def test_existing_name_or_namespace_conflict_blocks_creation(self):
        result = self.generate("--only", "pruner")
        self.assertEqual(result.returncode, 0, result.stderr)
        for options in ({"name": "Other Name"}, {"prefix": "com.github.other"}):
            result = self.generate("--parent", "com.github.vendor.munki.ExampleApp", **options)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(len(list(self.out.glob("*.yaml"))), 1)

    def test_existing_parent_conflict_blocks_creation(self):
        self.generate("--only", "importer", "--parent", "com.example.munki.First")
        result = self.generate("--parent", "com.example.munki.Second")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(list(self.out.glob("*.yaml"))), 1)

    def test_special_characters_roundtrip(self):
        name = 'Vendor: "App" & Tools / Plus \\ Café'
        result = self.generate("--only", "assigner", name=name)
        self.assertEqual(result.returncode, 0, result.stderr)
        recipe = recipe_lint.load_recipe(self.out / "ExampleApp.ws1-assigner.recipe.yaml")
        self.assertEqual(recipe["Input"]["NAME"], name)
        self.assertEqual(recipe_lint.lint(recipe, ws1=True)[0], [])

    def test_missing_parent_unsafe_path_or_multiline_name(self):
        for extra, kwargs in [
            ((), {}),
            (("--only", "pruner"), {"app": "../escape"}),
            (("--only", "pruner"), {"name": "Vendor\nApp"}),
        ]:
            result = self.generate(*extra, **kwargs)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.out.exists())

    @unittest.skipUnless(shutil.which("plistyamlplist"), "optional macOS formatting tool is not installed")
    def test_tidy_roundtrip_preserves_required_scalar_types(self):
        for path in self.full_set():
            before = recipe_lint.load_recipe(path)
            subprocess.run(["plistyamlplist", str(path), "--tidy"], check=True, capture_output=True, text=True)
            after = recipe_lint.load_recipe(path)
            self.assertEqual(before, after)
            self.assertEqual(recipe_lint.lint(after, ws1=True)[0], [])


class LintTests(unittest.TestCase):
    def test_bad_types_and_tokens(self):
        recipe = {
            "Identifier": "com.example.App",
            "MinimumVersion": 2.3,
            "Comment": None,
            "Input": {"NAME": "{{NAME}}", "WS1_APP_VERSIONS_TO_KEEP": 3},
            "Process": [{"Processor": "Example", "Arguments": {"ws1_groupid": 12}}],
        }
        self.assertGreaterEqual(len(recipe_lint.lint(recipe, ws1=True)[0]), 5)

    def test_boolean_safeguard_is_rejected(self):
        recipe = {
            "Identifier": "com.example.ws1-pruner.App",
            "Input": {"NAME": "Vendor App", "WS1_SAFEGUARD_HALT_ON_ASSIGNED": True},
            "Process": [],
        }
        self.assertIn("WS1_SAFEGUARD_HALT_ON_ASSIGNED must be a string", recipe_lint.lint(recipe, ws1=True)[0])

    def test_complex_assignments_cannot_be_substitution_strings(self):
        recipe = {
            "Identifier": "com.example.App",
            "Input": {"NAME": "Vendor App"},
            "Process": [{"Processor": "Example", "Arguments": {"ws1_app_assignments": "%ASSIGNMENTS%"}}],
        }
        self.assertTrue(any("must be a list" in error for error in recipe_lint.lint(recipe, ws1=True)[0]))

    def test_duplicate_yaml_keys_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.recipe.yaml"
            path.write_text("Identifier: first\nIdentifier: second\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                recipe_lint.load_recipe(path)

    def test_plist_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Example.recipe"
            recipe = {"Identifier": "com.example.pkg.App", "Process": []}
            path.write_bytes(plistlib.dumps(recipe))
            self.assertEqual(recipe_lint.load_recipe(path), recipe)

    def test_cli_reports_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.recipe.yaml"
            path.write_text("Identifier: com.example.App\nInput: []\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(LINTER), "--ws1", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Input must be a mapping", result.stdout)


class DistributionTests(unittest.TestCase):
    def test_skill_frontmatter_and_pi_manifest(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        metadata = yaml.safe_load(text.split("---", 2)[1])
        self.assertEqual(metadata["name"], SKILL.name)
        self.assertLessEqual(len(metadata["description"]), 1024)
        self.assertEqual(set(metadata), {"name", "description", "license"})
        self.assertEqual(metadata["license"], "Apache-2.0")
        package = json.loads((ROOT / "package.json").read_text())
        self.assertEqual(package["pi"]["skills"], ["./.github/skills/autopkg-workspace-one"])
        self.assertTrue(package["private"])
        self.assertNotIn("dependencies", package)

    def test_license_is_included_with_copied_and_packaged_skill(self):
        root_license = (ROOT / "LICENSE").read_bytes()
        self.assertEqual(root_license, (SKILL / "LICENSE").read_bytes())
        self.assertIn(b"Apache License", root_license)
        self.assertIn(b"END OF TERMS AND CONDITIONS", root_license)
        package = json.loads((ROOT / "package.json").read_text())
        self.assertEqual(package["license"], "Apache-2.0")
        self.assertIn(".github/skills/autopkg-workspace-one/LICENSE", package["files"])
        for path in SKILL.glob("scripts/*.py"):
            self.assertIn("SPDX-License-Identifier: Apache-2.0", path.read_text())

    def test_skill_bundle_works_after_copy_without_other_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            isolated = Path(directory) / ".github/skills/autopkg-workspace-one"
            shutil.copytree(SKILL, isolated, ignore=shutil.ignore_patterns("__pycache__"))
            result = subprocess.run(
                [
                    sys.executable,
                    str(isolated / "scripts/new_ws1_recipe.py"),
                    "ExampleApp",
                    "--name",
                    "Vendor Example App",
                    "--identifier-prefix",
                    "com.github.example",
                    "--only",
                    "pruner",
                    "--out",
                    str(Path(directory) / "out"),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            path = Path(directory) / "out/ExampleApp.ws1-pruner.recipe.yaml"
            self.assertEqual(recipe_lint.lint(recipe_lint.load_recipe(path), ws1=True)[0], [])
            skill_text = (isolated / "SKILL.md").read_text()
            self.assertNotIn("../autopkg-recipes", skill_text)

    def test_relative_skill_links_resolve_within_bundle(self):
        for path in [SKILL / "SKILL.md", *SKILL.glob("references/*.md")]:
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                if "://" not in target and not target.startswith("#"):
                    resolved = (path.parent / target.split("#")[0]).resolve()
                    self.assertIn(SKILL.resolve(), resolved.parents)
                    self.assertTrue(resolved.is_file(), target)

    def test_templates_are_not_runnable_recipe_files(self):
        self.assertEqual(len(list((SKILL / "templates").glob("*.recipe.yaml.in"))), 3)
        self.assertEqual(list((SKILL / "templates").glob("*.recipe.yaml")), [])


if __name__ == "__main__":
    unittest.main()
