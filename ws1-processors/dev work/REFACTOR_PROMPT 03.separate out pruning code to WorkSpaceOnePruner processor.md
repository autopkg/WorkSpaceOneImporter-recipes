# Refactoring Prompt: Extract Pruning into a `WorkSpaceOnePruner` Processor

## Objective

Separate the app-version pruning logic from
`ws1-processors/WorkSpaceOneImporter.py` (the `ws1_app_versions_prune` method,
lines ~840–1023) into a new standalone AutoPkg processor
`ws1-processors/WorkSpaceOnePruner.py` containing the class
`WorkSpaceOnePruner(WorkSpaceOneImporterBase)`.

The goal is to allow pruning of old app versions to run **independently** —
ideally as a **pre-processor** (running before `WorkSpaceOneImporter`), or on a
separate schedule — enabling compatibility with
[cloud-autopkg-runner (CAR)](https://pypi.org/project/cloud-autopkg-runner/)
where the import processor may be short-circuited after the check phase if
there are no new downloads.

**Why a pre-processor?** Pruning old versions _before_ importing new ones is
the natural workflow: clean up first, then upload. This avoids the situation
where a new version is imported but the prune step never runs (e.g. because CAR
short-circuits later processors). Running as a pre-processor also means pruning
happens on every scheduled run regardless of whether a new download was found.

---

## Context & Constraints

| Item | Detail |
|---|---|
| **Runtime** | `/usr/local/autopkg/python` (AutoPkg's bundled Python 3.10) |
| **Base class** | `WorkSpaceOneImporterBase` from `ws1_lib/WorkSpaceOneImporterBase.py` — provides `self.env`, `self.output()`, `self.init_tls()`, `self.ws1_auth_prep()`, and the `main()` / `execute_shell()` contract. |
| **Formatter** | Black, line-length 120 (see `pyproject.toml`). Import sorting: isort with `profile = "black"` (`.isort.cfg`). |
| **Linter** | flake8, max-line-length 120. |
| **Dependencies** | `requests` (already installed). No additional dependencies required. |
| **Package layout** | Processor file lives at `ws1-processors/WorkSpaceOnePruner.py`. It imports `WorkSpaceOneImporterBase` via the `ws1_lib` package already on `sys.path`. |
| **Shared-processor stub recipe** | A YAML stub recipe `ws1-processors/WorkSpaceOnePruner.recipe.yaml` must also be created so other recipes can reference the shared processor as `com.github.codeskipper.VMWARE-WorkSpaceOnePruner/WorkSpaceOnePruner`. |
| **Backwards compat** | `WorkSpaceOneImporter.py` must continue to work identically (pruning still called from `ws1_import()`) until recipes are migrated. The pruning method is **duplicated** in both files initially — NOT removed from `WorkSpaceOneImporter` in this PR. |
| **Licence** | Apache-2.0, same as the rest of the project. |

---

## Source Code to Extract

### Primary: `ws1_app_versions_prune()` method (lines 840–1023)

This method currently lives on the `WorkSpaceOneImporter` class. It:

1. Reads `ws1_app_versions_to_keep_default` (default "5") and `ws1_app_versions_to_keep` from `self.env`.
2. Reads `ws1_app_versions_prune` mode (True / False / dry_run) from `self.env`.
3. Iterates `search_results["Application"]` filtering for `Platform == 10` and matching `ApplicationName`.
4. For each matching app, calls the **V2 API** `GET /api/mam/apps/{uuid}/assignment-rules` to find the first deployment date.
5. Builds a sorted list of app versions by deployment date.
6. Marks the oldest versions (beyond `keep_versions`) as "TO BE PRUNED".
7. When mode is `True` (not `dry_run`): validates `AssignedDeviceCount == 0` then calls `DELETE /api/mam/apps/internal/{App_ID}`.
8. On success, updates `self.env["ws1_pruned"]` and `self.env["ws1_importer_summary_result"]` with the pruned details.

### Supporting: `extract_first_integer_from_string()` (lines 75–81)

Module-level helper used to parse integer values from string input variables. Must be available in the new processor.

### Supporting: App search API call pattern (lines 307–317)

The pruner needs `search_results` — the JSON response from
`GET /api/mam/apps/search?locationgroupid={ogid}&applicationname={name}`.
In the standalone processor this call must be performed in `main()` before
calling the pruning logic.

### Supporting: OG ID resolution (lines 282–305)

The pattern to resolve `ws1_groupid` → numeric `ogid` via
`GET /api/system/groups/search?groupid={org_group_id}`.
This is needed to form the app search URL.

---

## Target File Layout

```
ws1-processors/
├── WorkSpaceOneImporter.py              # UNCHANGED in this PR
├── WorkSpaceOneImporter.recipe.yaml
├── WorkSpaceOnePruner.py                # NEW — standalone pruning processor
├── WorkSpaceOnePruner.recipe.yaml       # NEW — stub recipe for shared-processor use
├── ws1_lib/
│   ├── __init__.py
│   └── WorkSpaceOneImporterBase.py
└── ...
```

---

## Detailed Instructions

### A. Create `ws1-processors/WorkSpaceOnePruner.py`

1. **Shebang** — `#!/usr/local/autopkg/python`

2. **Licence header** — Apache-2.0 (same as `WorkSpaceOneImporter.py`), with
   author `Martinus Verburg https://github.com/codeskipper`.

3. **Module docstring**:
   ```python
   """Autopkg processor to prune old app versions from Omnissa Workspace ONE UEM using REST API."""
   ```

4. **Imports**:
   ```python
   import os
   import re
   import sys
   from datetime import datetime

   import requests
   from autopkglib import ProcessorError

   sys.path.insert(0, os.path.dirname(__file__))

   from ws1_lib.WorkSpaceOneImporterBase import (  # noqa: E402
       WorkSpaceOneImporterBase,
       is_url,
   )
   ```

5. **`__all__`**:
   ```python
   __all__ = ["WorkSpaceOnePruner"]
   ```

6. **Module-level helper** — copy `extract_first_integer_from_string()`:
   ```python
   def extract_first_integer_from_string(s):
       """Search for the first occurrence of a sequence of digits and return as int."""
       match = re.search(r"\d+", s)
       if match:
           return int(match.group())
       return None
   ```

7. **Class definition**:
   ```python
   class WorkSpaceOnePruner(WorkSpaceOneImporterBase):
       """Prunes old app versions from Workspace ONE UEM."""
   ```

8. **`input_variables`** — merge base class variables + add Pruner-specific ones:

   ```python
   input_variables = {
       **WorkSpaceOneImporterBase.input_variables,
       "ws1_app_versions_to_keep": {
           "required": False,
           "description": "The number of versions of an app to keep in WS1. Please set this in a recipe (override).\n"
           "NB - please make sure to provide the input variable as type string in the recipe override, using "
           " an integer will result in a hard to trace runtime error 'expected string or bytes-like object'",
       },
       "ws1_app_versions_to_keep_default": {
           "required": False,
           "default": "5",
           "description": "The default number of versions of an app to keep in WS1. Default:5.",
       },
       "ws1_app_versions_prune": {
           "required": False,
           "default": "dry_run",
           "description": "Whether to prune old versions of an app on WS1. Possible values: True or False or "
           "dry_run. Default:dry_run.",
       },
   }
   ```

9. **`output_variables`**:

   ```python
   output_variables = {
       "ws1_pruned": {
           "description": "True if old app versions were pruned in this session.",
       },
       "ws1_pruner_summary_result": {
           "description": "Summary of the pruning operation.",
       },
   }
   ```

10. **`_resolve_ogid()` private method** — ported from `ws1_import()` lines 282–305:

    ```python
    def _resolve_ogid(self, api_base_url, org_group_id, headers_v2):
        """Resolve the WS1 Organization Group ID from the textual GroupID."""
        try:
            r = requests.get(
                f"{api_base_url}/api/system/groups/search?groupid={org_group_id}",
                headers=headers_v2,
            )
            result = r.json()
            r.raise_for_status()
        except AttributeError:
            raise ProcessorError(
                f"WorkSpaceOnePruner: Unable to retrieve an ID for the Organizational GroupID specified: {org_group_id}"
            )
        except requests.exceptions.HTTPError as err:
            raise ProcessorError(
                f"WorkSpaceOnePruner: Server responded with error when making the OG ID API call: {err}"
            )
        except requests.exceptions.RequestException as e:
            raise ProcessorError(f"WorkSpaceOnePruner: Error making the OG ID API call: {e}")

        ogid = ""
        if org_group_id in result["OrganizationGroups"][0]["GroupId"]:
            ogid = result["OrganizationGroups"][0]["Id"]
        self.output(f"Organisation group ID: {ogid}", verbose_level=2)
        return ogid
    ```

11. **`_search_apps()` private method** — ported from `ws1_import()` lines 307–317:

    ```python
    def _search_apps(self, api_base_url, ogid, app_name, headers):
        """Search WS1 for existing versions of the given app."""
        condensed_app_name = app_name.replace(" ", "%20")
        try:
            r = requests.get(
                f"{api_base_url}/api/mam/apps/search?locationgroupid={ogid}&applicationname={condensed_app_name}",
                headers=headers,
            )
        except Exception:
            raise ProcessorError("WorkSpaceOnePruner: Something went wrong searching for app on server.")
        if r.status_code != 200:
            self.output(
                f"App search returned status {r.status_code}, no apps found to prune.",
                verbose_level=1,
            )
            return None
        return r.json()
    ```

12. **`ws1_app_versions_prune()` method** — port the full method from
    `WorkSpaceOneImporter.py` lines 840–1023 **byte-for-byte**, with the
    following changes:

    - Prefix `ProcessorError` messages with `"WorkSpaceOnePruner:"` instead of
      `"ws1_app_versions_prune -"` where appropriate.
    - Replace `self.env["ws1_importer_summary_result"]` with
      `self.env["ws1_pruner_summary_result"]` for the result key (so it doesn't
      overwrite the importer's summary).
    - The method signature stays the same:
      `def ws1_app_versions_prune(self, api_base_url, headers, app_name, search_results):`
    - Keep all logic unchanged: the `keep_versions_default`, `keep_versions`,
      `app_versions_prune` mode parsing, the v2 headers construction, the app
      list building with assignment-rule date lookup, the sort-by-date, the
      status marking, and the deletion loop including the
      `AssignedDeviceCount > 0` safeguard.

13. **`main()` method** — the orchestrator:

    ```python
    def main(self):
        """Prune old app versions from Workspace ONE UEM."""
        # Clear any pre-existing summary result
        if "ws1_pruner_summary_result" in self.env:
            del self.env["ws1_pruner_summary_result"]
        self.env["ws1_pruned"] = False

        api_base_url = self.env.get("ws1_api_url")
        org_group_id = self.env.get("ws1_groupid")

        # The app name to prune. Use NAME from environment (set by parent recipe).
        app_name = self.env.get("NAME")
        if not app_name:
            raise ProcessorError("WorkSpaceOnePruner: NAME is not set — cannot determine which app to prune.")

        # Init TLS and authenticate
        self.init_tls()
        headers, headers_v2 = self.ws1_auth_prep()

        # Resolve Organization Group numeric ID
        ogid = self._resolve_ogid(api_base_url, org_group_id, headers_v2)

        # Search for existing app versions
        search_results = self._search_apps(api_base_url, ogid, app_name, headers)
        if search_results is None:
            self.output("No app versions found on server, nothing to prune.")
            return
        if "Application" not in search_results or not search_results["Application"]:
            self.output("No matching applications found, nothing to prune.")
            return

        # Run pruning logic
        self.ws1_app_versions_prune(api_base_url, headers, app_name, search_results)
    ```

14. **`if __name__ == "__main__"` block**:
    ```python
    if __name__ == "__main__":
        PROCESSOR = WorkSpaceOnePruner()
        PROCESSOR.execute_shell()
    ```

### B. Create `ws1-processors/WorkSpaceOnePruner.recipe.yaml`

```yaml
Description: |
  This is the yaml stub recipe for WorkSpaceOnePruner shared processor, so it can be
  used by another recipe outside of this repo.
  Prunes old app versions from Omnissa Workspace ONE UEM.
  Instead of setting the 'Processor' key to a processor name only, we separate the
  recipe identifier and the processor name with a slash:
  Processor: com.github.codeskipper.VMWARE-WorkSpaceOnePruner/WorkSpaceOnePruner

Identifier: com.github.codeskipper.VMWARE-WorkSpaceOnePruner
Input: {}
MinimumVersion: "2.3"
Process: []
```

### C. Example recipe usage

The pruner is best used as a **pre-processor** — running _before_
`WorkSpaceOneImporter` so that old versions are cleaned up before a new one
is imported. This ensures pruning runs on every scheduled execution regardless
of whether a new download was found:

```yaml
Process:
- Processor: com.github.codeskipper.VMWARE-WorkSpaceOnePruner/WorkSpaceOnePruner
  Arguments:
    ws1_oauth_client_id: '%WS1_OAUTH_CLIENT_ID%'
    ws1_oauth_client_secret: '%WS1_OAUTH_CLIENT_SECRET%'
    ws1_oauth_token_url: '%WS1_OAUTH_TOKEN_URL%'
    ws1_api_url: '%WS1_API_URL%'
    ws1_groupid: '%WS1_GROUPID%'
    ws1_app_versions_to_keep: '%WS1_APP_VERSIONS_TO_KEEP%'
    ws1_app_versions_prune: "True"

- Processor: com.github.codeskipper.VMWARE-WorkSpaceOneImporter/WorkSpaceOneImporter
  Arguments:
    # ... WS1 import arguments ...
    ws1_app_versions_prune: "False"   # disable pruning in the importer (handled above)
```

Alternatively, with AutoPkg's `--preprocessor` flag it can run before _every_
recipe without modifying recipe files:

```sh
autopkg run --preprocessor com.github.codeskipper.VMWARE-WorkSpaceOnePruner/WorkSpaceOnePruner \
  --key ws1_app_versions_prune=True \
  --key ws1_app_versions_to_keep=3 \
  SomeApp.ws1.recipe.yaml
```

It can also run on a **separate schedule** (e.g. weekly via cron/launchd) as a
standalone recipe that only prunes:

```yaml
Description: Prune old versions of Google Chrome from WS1 UEM.
Identifier: com.github.codeskipper.ws1.GoogleChrome.prune
MinimumVersion: "2.3"

Input:
  NAME: Google Chrome
  WS1_OAUTH_CLIENT_ID: OAUTH2_CLIENT_ID_HERE
  WS1_OAUTH_CLIENT_SECRET: OAUTH2_CLIENT_SECRET_HERE
  WS1_OAUTH_TOKEN_URL: OAUTH2_ACCESS_TOKEN_SERVER_URL_HERE
  WS1_API_URL: WORKSPACEONE_API_URL_HERE
  WS1_GROUPID: GROUP_ID_HERE
  WS1_APP_VERSIONS_TO_KEEP: "3"
  WS1_APP_VERSIONS_PRUNE: "True"

Process:
- Processor: com.github.codeskipper.VMWARE-WorkSpaceOnePruner/WorkSpaceOnePruner
  Arguments:
    ws1_oauth_client_id: '%WS1_OAUTH_CLIENT_ID%'
    ws1_oauth_client_secret: '%WS1_OAUTH_CLIENT_SECRET%'
    ws1_oauth_token_url: '%WS1_OAUTH_TOKEN_URL%'
    ws1_api_url: '%WS1_API_URL%'
    ws1_groupid: '%WS1_GROUPID%'
    ws1_app_versions_to_keep: '%WS1_APP_VERSIONS_TO_KEEP%'
    ws1_app_versions_prune: '%WS1_APP_VERSIONS_PRUNE%'
```

### D. Do NOT modify `WorkSpaceOneImporter.py` (in this PR)

The pruning method stays in `WorkSpaceOneImporter.py` **as-is** for backwards
compatibility. Recipes that currently rely on the importer doing pruning
continue to work unchanged. A follow-up PR can:

1. Set `ws1_app_versions_prune` default to `"False"` in `WorkSpaceOneImporter`.
2. Add `WorkSpaceOnePruner` as a **pre-processor step** (first in `Process` list) in existing recipes.
3. Eventually deprecate and remove the pruning method from `WorkSpaceOneImporter`.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **Pre-processor is the recommended position** | Pruning before import ensures old versions are cleaned up even when CAR short-circuits after the check phase; it also guarantees pruning runs on every schedule regardless of new downloads. |
| Standalone `main()` performs its own auth + app search | Pruner must work independently without `WorkSpaceOneImporter` having run first (essential for pre-processor and standalone-schedule use). |
| `NAME` environment variable used for app name | Same pattern as all other processors — `NAME` is always set by the parent recipe. |
| Results written to `ws1_pruner_summary_result` (not `ws1_importer_summary_result`) | Avoids overwriting the importer's summary when both run in the same chain. `WorkSpaceOneSlacker` should be updated to also read `ws1_pruner_summary_result`. |
| `ws1_pruned` env var still set by the pruner | Maintains compatibility with downstream processors (`WorkSpaceOneSlacker`) that check this flag. |
| `extract_first_integer_from_string()` duplicated | Keeps the pruner self-contained. Could be moved to `ws1_lib` in a future PR. |
| OG resolution and app search duplicated as private methods | Same endpoints, but encapsulated cleanly. Could be promoted to `WorkSpaceOneImporterBase` in future. |

---

## Validation Checklist

- [ ] `python -m py_compile ws1-processors/WorkSpaceOnePruner.py` passes.
- [ ] `WorkSpaceOnePruner.recipe.yaml` is valid YAML (parse with
      `python -c "import yaml; yaml.safe_load(open(...))"` or
      `pre-commit-macadmin check-autopkg-recipes --strict`).
- [ ] Black formatting: `black --check --line-length 120 ws1-processors/WorkSpaceOnePruner.py`.
- [ ] isort: `isort --check --profile black ws1-processors/WorkSpaceOnePruner.py`.
- [ ] flake8: `flake8 --max-line-length 120 ws1-processors/WorkSpaceOnePruner.py`.
- [ ] The `input_variables` dict merges the base class with
      `**WorkSpaceOneImporterBase.input_variables`.
- [ ] `WorkSpaceOneImporter.py` is **unchanged** and still passes
      `python -m py_compile`.
- [ ] Running an existing `.ws1.recipe.yaml` (that has pruning enabled in the
      importer) through `autopkg run -vvv` produces identical behaviour to
      the pre-refactor code.
- [ ] Running `WorkSpaceOnePruner` standalone (via a prune-only recipe)
      authenticates, searches apps, and prunes correctly in `dry_run` and
      `True` modes.
- [ ] Running `WorkSpaceOnePruner` as a pre-processor (first in `Process`
      list, before `WorkSpaceOneImporter`) works correctly — pruning runs
      before import and does not interfere with subsequent processors.
- [ ] `dry_run` mode lists versions and their prune status but does NOT delete.
- [ ] `True` mode deletes the correct versions and refuses to delete versions
      with `AssignedDeviceCount > 0`.
- [ ] `False` mode short-circuits and returns immediately.
- [ ] `ws1_pruned` is set to `True` in `self.env` after successful pruning.
- [ ] `ws1_pruner_summary_result` is populated with `name`,
      `pruned_versions`, and `pruned_versions_num`.

---

## Future Roadmap (out of scope for this PR)

- Move `extract_first_integer_from_string()` to `ws1_lib` as a shared utility.
- Move `_resolve_ogid()` and `_search_apps()` to `WorkSpaceOneImporterBase`
  since they are needed by multiple processors.
- Deprecate and remove `ws1_app_versions_prune()` from `WorkSpaceOneImporter`.
- Update `WorkSpaceOneSlacker` to read both `ws1_importer_summary_result` and
  `ws1_pruner_summary_result`.
- Add a `ws1_app_name` input variable as an explicit override (instead of
  relying solely on `NAME`) for cases where the WS1 app name differs from the
  munki name.






