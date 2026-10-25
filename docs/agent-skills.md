# Workspace ONE agent tooling (preview)

This repository includes a self-contained [Agent Skills](https://agentskills.io/specification) bundle for authoring and reviewing importer, assigner, and pruner recipes:

```text
.github/skills/autopkg-workspace-one/
  SKILL.md
  references/parents-and-validation.md
  scripts/new_ws1_recipe.py
  scripts/lint_recipes.py
  templates/*.recipe.yaml.in
```

One source serves skill-capable coding harnesses. There is no harness SDK dependency, network integration, shell pre-approval, credential installation, or automatic deployment. These are agent instructions and offline tools, not an AutoPkg replacement or an enforcement boundary.

## Status and scope

The tooling is a preview. Offline script/resource checks are separate from interactive host acceptance tests and live UEM tests. No live operations are covered by the test suite. Do not infer that generated placeholders, dry-run mode, or a passing linter make it safe to run a recipe against production.

General AutoPkg parent authoring can use the published [homebysix skill](https://github.com/autopkg/homebysix-recipes/blob/master/.claude/skills/create-autopkg-recipes/SKILL.md) and Recipe Robot. That skill is linked as an optional resource, not bundled, copied, or required to be installed alongside this one. Its repository-specific conventions are not universal WS1 policy.

No top-level license was present when this tooling was prepared. The optional package manifest therefore remains `private: true` / `UNLICENSED` until maintainers choose distribution terms. Do not publish to npm or represent the preview as licensed for redistribution until that decision is made.

## GitHub Copilot in PyCharm

GitHub documents project skill discovery in `.github/skills`; JetBrains support depends on the installed Copilot plugin version and surface. Open the repository containing this bundle and use a supported agent-mode surface. Check your plugin's documentation rather than assuming all chat modes load skills.

Use this smoke-test request:

> Use the autopkg-workspace-one skill. First identify the SKILL.md and referenced resources you read. Generate only an ExampleApp importer in a temporary directory, using Vendor Example App as NAME and an illustrative parent identifier. Run offline structural lint only. Do not run AutoPkg, download software, contact UEM, change trust, or commit anything.

Inspect tool activity, the generated file, and actual lint output. A model asserting it used a skill is not proof. The example parent is intentionally not a real recipe: this discovery test must not attempt parent resolution.

## Copilot cloud agent

The cloud agent needs this bundle in the repository/ref it can access. A directory in your Mac's home folder or an external symlink is not available remotely. If using a separate CI/CD repository, vendor a reviewed/pinned copy (including scripts, references, and templates), or configure a reviewed checkout of this repository in the agent environment. Keep the source ref recorded and review updates rather than silently synchronizing arbitrary branches.

Cloud editing environments can generally author files and run available structural checks. They cannot certify native macOS installer/signature/DMG behavior without the relevant platform tools. A separately configured CAR workflow may run platform-independent WS1 assignments/pruning on Linux; that does not authorize live operations in an editing session. Never provide production WS1 credentials just for a discovery test.

## Pi

The root package.json is only a thin adapter exposing the same skill directory. It has no npm dependencies, lifecycle scripts, or custom Pi extension. After source review, install the repository as a Pi package:

```sh
pi install /absolute/path/to/WorkSpaceOneImporter-recipes
```

Or test without changing Pi's saved package/skill configuration, from the repository root:

```sh
pi --no-skills --skill ./.github/skills/autopkg-workspace-one
```

Use `/reload` after a package/resource configuration change where appropriate. Disable conflicting older local AutoPkg/WS1 skills before normal use, but preserve backups until the replacement is tested. Do not load the same bundle through multiple discovery routes.

A future public git installation should use a reviewed release/ref. No npm publication is needed for git-based Pi discovery.

## Other harnesses

The frontmatter uses only portable `name` and `description`. A host implementing Agent Skills may consume the bundle, but verify its current discovery, resource-access, approval, and sandbox behavior before claiming compatibility. This PR does not claim tested Claude Code or Codex integration.

## Dependencies and offline generation

Generation and YAML lint require Python 3.9+ with PyYAML. Use an existing interpreter or explicitly create an isolated environment. Do not install tool dependencies into AutoPkg's global Python merely to run the offline tests.

From the repository root:

```sh
python3 -m venv /path/to/disposable-venv
/path/to/disposable-venv/bin/python -m pip install -r tests/agent_skills/requirements.txt
```

The test requirements also include the established strict recipe checker. They are not processor runtime dependencies and are not installed automatically by Pi.

Generate all three types, or add `--only importer`, `--only assigner`, or `--only pruner`:

```sh
SKILL=.github/skills/autopkg-workspace-one
python3 "$SKILL/scripts/new_ws1_recipe.py" ExampleApp \
  --name 'Vendor Example App' \
  --identifier-prefix com.github.codeskipper \
  --parent com.github.vendor.munki.ExampleApp \
  --out /path/to/recipe-output
```

Substitute a real reviewed Munki parent before using the recipe. The illustrative parent does not exist. Namespace prefixes for generated recipes do not change the reference processors' namespace. Existing files are never overwritten; conflicting names, identifiers, or a supplied parent are errors.

The importer inherits metadata. The assigner starts with simple assignment placeholders; AppsV2 users must clear the simple group input and supply a lowercase list. The pruner explicitly defaults to dry_run and a string-typed enabled assigned-version safeguard. Dry-run mode still contacts UEM; changing it to deletion mode requires approval. Retention placeholders may fall back to processor defaults and are not a guardrail.

Templates end in `.in` so normal AutoPkg indexing and strict recipe hooks do not mistake incomplete scaffolds for runnable recipes. Output files have the normal `.recipe.yaml` extension.

## Validation

```sh
python3 -m unittest discover -s tests/agent_skills -v
python3 .github/skills/autopkg-workspace-one/scripts/lint_recipes.py --ws1 /path/to/recipes/*.recipe.yaml
check-autopkg-recipes --strict /path/to/recipes/*.recipe.yaml
```

Use the chosen environment's executable paths as needed. If plistyamlplist is installed, the tests also exercise formatting round trips; otherwise that optional test is explicitly skipped. The CI workflow runs offline tests and strict-checks generated output on Linux without credentials or recipe execution. Unit tests cover the dry-run default, string types, namespace separation, quoting, staged generation, conflict/overwrite protection, duplicate keys, and copied-bundle portability.

The structural linter is intentionally limited. It does not resolve parents, verify signatures, discover vendor names, validate all processor/API arguments, establish trust, or prove live deployment behavior. Use the repository's established strict checker as well. At the pinned v1.24.1 revision, that checker exits successfully for these generated recipes but warns that WS1 is an unknown recipe type and skips processor convention checks. Do not present that result as full WS1 schema validation.

The installed pre-commit runner must support the stages used by the repository's hook versions. Do not bypass hooks or change unrelated hook/tool versions to make this preview pass; use an approved isolated tooling environment if necessary.

### Host acceptance checklist

- [ ] PyCharm Copilot discovers this exact bundle and reads its resources.
- [ ] Copilot cloud agent discovers the bundle from the selected branch/ref.
- [ ] Pi discovers the bundle through the thin package adapter or explicit path.
- [ ] Each host performs the temporary-generation/lint smoke test without live operations.
- [ ] Tool limitations and required user approvals are reported correctly.

These are manual acceptance checks, not claims made by passing the Python tests.

## CI/CD workspace conventions

Reusable recipes belong here; environment-specific overrides/preferences/lists belong in the deployment repository. For a layout such as [AutoPkg-WS1-example](https://github.com/equinor/AutoPkg-WS1-example), read that checkout's actual `autopkg_ws1-car.yml` and driver, run from its repository root, and use its exported preferences and repo-relative cache/repo/override/report paths. Do not silently configure global AutoPkg preferences or copy a runner's absolute paths to another machine.

Keep project-specific CAR paths, CA bundles, runtime pins, and private configuration in that deployment project's instructions. This skill does not install dependencies, clone Munki/recipe repositories, retrieve keychain credentials, run launchers, or execute deployments when loaded.

## Sources

- GitHub skill setup and supported locations: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/create-skills
- GitHub skill concepts/surfaces: https://docs.github.com/en/copilot/concepts/customizations/agent-skills
- Agent Skills specification: https://agentskills.io/specification

Host support evolves. Recheck the installed client's capabilities, and preserve approvals/sandbox controls rather than pre-approving shell execution.
