# AGENTS.md

## Project Overview

Custom [AutoPkg](https://github.com/autopkg/autopkg) shared processor and recipes for importing macOS app packages into **Omnissa Workspace ONE UEM** via its REST API. Runs under AutoPkg's bundled Python 3.10 at `/Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/python3`.

## Architecture

- **`ws1-processors/WorkSpaceOneImporter.py`** — The main AutoPkg processor. Subclasses `WorkSpaceOneImporterBase` and handles: uploading pkg/pkginfo/icon blobs, creating app objects, simple & advanced app assignments (API V1 & V2), and pruning old app versions.
- **`ws1-processors/ws1_lib/WorkSpaceOneImporterBase.py`** — Base class extracted from the main processor. Owns all WS1 REST API authentication (OAuth 2.0 + Basic), TLS/CA-cert init (`REQUESTS_CA_BUNDLE` or optional `macsesh`), and OAuth token persistence in a dedicated macOS keychain. Future processors inherit auth "for free."
- **`ws1-processors/ws1_lib/`** — Python package (`__init__.py` re-exports `WorkSpaceOneImporterBase`). Imported via `sys.path.insert(0, os.path.dirname(__file__))` in the processor.
- **`ws1-recipes/`** — YAML-format `.ws1.recipe.yaml` files. Each chains a community munki `ParentRecipe` with the `WorkSpaceOneImporter` shared processor. Secrets are templated as `%WS1_*%` variables.
- **`ws1-parent-recipes/`** — Custom munki parent recipes for apps not available in community repos.
- **`ws1-recipes-plist/`** — Legacy plist-format recipe (kept for reference; prefer YAML).
- **`ws1-processors/research/`** — Standalone API test scripts (OAuth, assignment rules).

## Key Conventions

- **All input variables** start with `ws1_` prefix. Recipe-level Input keys use `WS1_` (uppercase) and are substituted into processor Arguments as `%WS1_*%`.
- **`input_variables` merging pattern** — child processor merges parent's dict: `input_variables = {**WorkSpaceOneImporterBase.input_variables, ...}`. Follow this when adding new processors.
- **Processor identification** — the shared processor identifier is `com.github.codeskipper.VMWARE-WorkSpaceOneImporter` (the YAML stub recipe in `ws1-processors/WorkSpaceOneImporter.recipe.yaml`). Recipes reference it as `com.github.codeskipper.VMWARE-WorkSpaceOneImporter/WorkSpaceOneImporter`.
- **`ws1_app_versions_to_keep`** must be a **string** in recipe overrides, not an integer — passing an int causes a runtime error `'expected string or bytes-like object'`.
- **Assignment rule tags** — `#AUTOPKG` and `#AUTOPKG_DONE` in the assignment description field track automation state. Do not remove this tagging logic.

## Code Style & Linting

Formatting: **Black** (line-length 120, configured in `pyproject.toml`). Import sorting: **isort** with `profile = "black"` (`.isort.cfg`). Linting: **flake8** (max-line-length 120, `.flake8`). Recipe validation: **pre-commit-macadmin** `check-autopkg-recipes --strict`.

```sh
# Install pre-commit hooks (uses AutoPkg's Python)
/Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/pre-commit install --install-hooks
# Run all checks
/Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/pre-commit run --all-files
```

## Dependencies & Runtime

Python deps (`requests`, `requests_toolbelt`) must be installed into AutoPkg's Python:
```sh
sudo -H /Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/pip3 install requests requests_toolbelt
```
`macsesh` is optional — only imported when `REQUESTS_CA_BUNDLE` env var is **not** set.

## Testing

No automated test suite. Validation is done by running recipes through `autopkg`:
```sh
autopkg run -vvvv --key ws1_import_new_only=false SuspiciousPackage.ws1.recipe.yaml
```
**Warning:** verbose level > 2 prints secrets in plaintext. Use `AUTOPKG_` env var prefix for settings:
```sh
export AUTOPKG_verbose=2
export AUTOPKG_ws1_import_new_only=false
```
A smoke test for the base-class refactor exists at `ws1-processors/ws1_lib/test_refactor.py` — run with AutoPkg's Python.

## Planned Refactoring (Roadmap)

The processor is being split for [cloud-autopkg-runner (CAR)](https://pypi.org/project/cloud-autopkg-runner/) compatibility. Future processors (`WorkSpaceOneUploader`, `WorkSpaceOneAssigner`, `WorkSpaceOnePruner`) will each inherit `WorkSpaceOneImporterBase`. The refactor prompt is documented in `ws1-processors/ws1_lib/REFACTOR_PROMPT 01.separate out supporting functions into library.md`.
