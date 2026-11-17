# AGENTS.md

## Project Overview

Custom [AutoPkg](https://github.com/autopkg/autopkg) shared processor and recipes for importing macOS app packages into **Omnissa Workspace ONE UEM** via its REST API. Runs under AutoPkg's bundled Python 3.10 at `/Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/python3`.

## Architecture

- **`ws1-processors/WorkSpaceOneImporter.py`** — Main AutoPkg processor. Subclasses `WorkSpaceOneImporterBase` and handles: uploading pkg/pkginfo/icon blobs, creating app objects, simple & advanced app assignments (API V1 & V2), and pruning old app versions.
- **`ws1-processors/ws1_lib/WorkSpaceOneImporterBase.py`** — Base class owning all WS1 REST API authentication (OAuth 2.0 + Basic), TLS/CA-cert init (`REQUESTS_CA_BUNDLE` or optional `macsesh`), and OAuth token persistence in a dedicated macOS keychain. Future processors inherit auth for free.
- **`ws1-processors/ws1_lib/`** — Python package (`__init__.py` re-exports `WorkSpaceOneImporterBase`). Imported via `sys.path.insert(0, os.path.dirname(__file__))` in the processor — this `sys.path` hack is required by AutoPkg's shared processor loading; keep the `# noqa: E402` comments on the resulting imports.
- **`ws1-recipes/`** — YAML `.ws1.recipe.yaml` files. Each chains a community munki `ParentRecipe` with the shared processor. Secrets are templated as `%WS1_*%` variables.
- **`ws1-parent-recipes/`** — Custom munki parent recipes for apps not in community repos.
- **`shared-processors/SharePointSharedFolderURLProvider.py`** — Generic URL provider for anonymous OneDrive/SharePoint share links (folder listing via REST, cookie session, curl via `URLGetter`). Outputs `url` + `request_headers` for `URLDownloader` and `sharepoint_unchanged` for `StopProcessingIf` (SharePoint returns no ETag and no 304). Stub recipe identifier `com.github.codeskipper.SharePointSharedFolderURLProvider`. Used by `SnagitOffline` recipes.
- **`ws1-processors/WorkSpaceOneImporter.recipe.yaml`** — Stub recipe that registers the shared processor identifier `com.github.codeskipper.OMNISSA-WorkSpaceOneImporter`. Recipes reference it as `com.github.codeskipper.OMNISSA-WorkSpaceOneImporter/WorkSpaceOneImporter`.

## Key Conventions

- **Input variable naming** — processor-level variables use `ws1_` (lowercase). Recipe-level Input keys use `WS1_` (uppercase) and are substituted into processor Arguments as `%WS1_*%`.
- **`input_variables` merging** — child processor merges parent's dict: `input_variables = {**WorkSpaceOneImporterBase.input_variables, ...}`. Always follow this pattern when adding new processors.
- **`ws1_app_versions_to_keep`** must be a **string** in recipe overrides, not an integer — an int causes runtime error `'expected string or bytes-like object'`.
- **Assignment tagging** — `#AUTOPKG` and `#AUTOPKG_DONE` tags in assignment description fields track automation state. Do not remove this logic.
- **TLS/CA trust** — If env var `REQUESTS_CA_BUNDLE` is set, it's used for CA certs; otherwise `macsesh` is imported if available. `macsesh` forces `urllib3 < 2` due to deprecation issues.

## Code Style & Linting

Formatting: **Black** (line-length 120, `pyproject.toml`). Import sorting: **isort** `profile = "black"` (`.isort.cfg`). Linting: **flake8** (max-line-length 120, `.flake8`). Recipe validation: **pre-commit-macadmin** `check-autopkg-recipes --strict`.

```sh
# Install pre-commit hooks (uses AutoPkg's Python)
/Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/pre-commit install --install-hooks
# Run all checks
/Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/pre-commit run --all-files
```

If AutoPkg's bundled pre-commit is too old for a hook (seen with the isort hook), run a current one instead: `uvx pre-commit run --files <paths>` or `uvx pre-commit run --all-files`.

## Dependencies & Runtime

Python deps (`requests`, `requests_toolbelt`) must be installed into AutoPkg's Python:
```sh
sudo -H /Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/pip3 install requests requests_toolbelt
```

## Testing

There is no automated test suite for the WS1 processors. Validate by running recipes through `autopkg`:
```sh
autopkg run -vvvv --key ws1_import_new_only=false SuspiciousPackage.ws1.recipe.yaml
```
**Warning:** verbose level > 2 prints secrets in plaintext. Prefer env-var style:
```sh
export AUTOPKG_verbose=2
export AUTOPKG_ws1_import_new_only=false
```
Unit tests for `SharePointSharedFolderURLProvider` (offline, no network): `/Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/python3 -m unittest discover -s tests/shared_processors -v`.

Smoke test for the base-class refactor: `ws1-processors/ws1_lib/test_refactor.py` — run with AutoPkg's Python.

## Agent Tooling (Preview)

For recipe authoring/review, read `.github/skills/autopkg-workspace-one/SKILL.md` and its referenced guidance. The bundle is self-contained and does not require another local skill. Setup, limitations, and manual Copilot/Pi acceptance checks are documented in `docs/agent-skills.md`.

Offline tests: `python3 -m unittest discover -s tests/agent_skills -v` (PyYAML required). Install test dependencies only into an approved disposable environment. Do not treat offline tests or `autopkg info` as permission to execute live recipes.

## Adding a New Recipe

Copy an existing `.ws1.recipe.yaml` from `ws1-recipes/` (e.g., `Firefox.ws1.recipe.yaml`). Set `ParentRecipe` to the community munki recipe identifier, update `Identifier` to `com.github.codeskipper.ws1.<AppName>`, and keep the `Process` block referencing the shared processor with `%WS1_*%` variable substitution. All `WS1_*` Input keys are placeholders — actual values come from recipe overrides or env vars.

## Recipe Authoring Pitfalls

- **Check phase and full run must agree.** Runners such as cloud-autopkg-runner run `autopkg run --check` first and the full recipe only when a download was reported. AutoPkg just drops the steps after `EndOfCheckPhase`; a processor cannot tell which of the two it is in. Never stop a recipe on "unchanged" before `EndOfCheckPhase` (e.g. `StopProcessingIf`): the full run sees the file the check phase just downloaded as unchanged and stops before the import. When a processor detects an unchanged cached download itself, set `PKG` to the cached file: URLDownloader then skips the transfer, reports no download, and the rest of the recipe still runs (as with a 304). See `SharePointSharedFolderURLProvider` and `SnagitOffline.download`.
- **MunkiInstallsItemsCreator.** A string `version_comparison_key` is applied to every installs item, so the run fails if one of them (e.g. a dylib) lacks that key. The per-path dict form is ignored in YAML recipes, and file items always get an md5. Keep `installs_item_paths` to the app bundle unless every item has the key.
- **Install scripts in `pkginfo`.** Run them in a sandbox first (rewrite the paths to a temp folder, substitute a fake secret). Test an upgrade over an existing install as well as a fresh install. Folders a script creates are owned by root: if the app writes there as the user, set the permissions explicitly, after writing the files. Example: Snagit creates `Snagit/License` on first launch and does not activate without write access (`SnagitOffline.munki`).
- **Testing a recipe that is not merged yet.** With `FAIL_RECIPES_WITHOUT_TRUST_INFO` set, make throwaway overrides: `autopkg make-override --override-dir /tmp/<dir> -d shared-processors -d ws1-parent-recipes <recipe>`, then `autopkg run --override-dir /tmp/<dir> -d … <recipe>`. Run `autopkg update-trust-info` on them after every recipe or processor change. Pass secrets as `AUTOPKG_<KEY>` environment variables and import into a scratch `MUNKI_REPO`.

## Planned Refactoring

The processor is being split for [cloud-autopkg-runner (CAR)](https://pypi.org/project/cloud-autopkg-runner/) compatibility. Future processors (`WorkSpaceOneUploader`, `WorkSpaceOneAssigner`, `WorkSpaceOnePruner`) will each inherit `WorkSpaceOneImporterBase`. See `ws1-processors/ws1_lib/REFACTOR_PROMPT 01.separate out supporting functions into library.md`.


## Prompt and results summary saving style

- **Prompt and results** are saved in a new, separate Markdown file, with the prompt at the top and results below.  Folder structure is `dev work/<year> <seq> <topic>/<number>. REFACTOR_PROMPT <short-description>.md` (repo root), e.g. `dev work/2026 3 agentic tooling/`. Earlier refactoring work is in `dev work/2026 refactoring to separate WS1 operations/`.


## workaround for file creation issues in the chat AI
- see 035.1. TOOLING_ISSUE file creation workaround.md
- The tooling must use the workaround for create_file **with a literal (unescaped) path containing spaces.**
- This is needed because create_file with a path containing spaces is currently producing an error in the chat AI, and this workaround allows us to continue saving our prompt and results documents without interruption.
- Also, the use of a Heredoc in this context is failing, so that is not an option until the tooling is fixed.
