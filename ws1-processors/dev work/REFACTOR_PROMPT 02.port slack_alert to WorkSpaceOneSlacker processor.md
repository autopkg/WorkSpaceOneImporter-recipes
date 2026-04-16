# Refactoring Prompt: Port `slack_alert()` to a `WorkSpaceOneSlacker` AutoPkg Processor

## Objective

Create a new custom AutoPkg shared processor called `WorkSpaceOneSlacker` that
sends Slack webhook notifications about the results of a WorkSpace ONE import
recipe run.

The notification logic is ported from the `slack_alert()` function (lines
515–645) and supporting code in the private AutoPkg runner CICD repository
<REDACTED> in file `autopkg_tools_ws1_cloud_cli.py`.

### Key design decision

The original `slack_alert()` reads results from a `Recipe` object whose
`_parse_report()` helper parses the AutoPkg **report plist file**. The new
processor must **also read from the report plist file** — the same file that
AutoPkg writes when invoked with `--report-plist`. The path to this file is
available at runtime via the environment variable **`REPORT_PLIST`**
(`self.env.get("REPORT_PLIST")`).

#### How `autopkg` writes the report plist

When `autopkg run --report-plist /path/to/report.plist` is used, AutoPkg
collects results from every processor in the recipe run and writes a plist
with this structure (see `autopkg` source at
<https://github.com/autopkg/autopkg>, lines ~2330–2414):

```python
{
    "failures": [
        {"message": "...", "traceback": "...", "recipe": "..."},
        ...
    ],
    "summary_results": {
        "munki_importer_summary_result": {
            "summary_text": "...",
            "header": ["name", "version", "catalogs", ...],
            "data_rows": [
                {"name": "...", "version": "...", "catalogs": "...",
                 "pkg_repo_path": "...", "pkginfo_path": "...", ...},
            ],
        },
        "ws1_importer_summary_result": {
            "summary_text": "The following new app(s) were imported ...",
            "header": ["name", "version", "new_assignment_rules", ...],
            "data_rows": [
                {"name": "...", "version": "...", "new_assignment_rules": "...",
                 "console_location": "...", "pruned_versions": "...",
                 "pruned_versions_num": "...", ...},
            ],
        },
    },
}
```

The processor reads `REPORT_PLIST` from `self.env`, opens the plist, and
extracts imported items, WS1 results, and failure information — closely
mirroring the original `Recipe._parse_report()` method.

**Important:** The report plist is written by `autopkg` **after each
processor step completes**, so when `WorkSpaceOneSlacker` runs (after
`WorkSpaceOneImporter`), the plist already contains the results from all
prior processors. However, `WorkSpaceOneSlacker` must also handle the case
where `REPORT_PLIST` is not set (e.g. when `--report-plist` was not passed
to `autopkg run`) — in that case it should log a warning and fall back to
reading from `self.env` directly (see Fallback section below).

---

## Licensing

The source file `autopkg_tools_ws1_cloud_cli.py` and the repository
`equinor/autopkg-cicd` are licensed under the **BSD-3-Clause** licence
(see the `LICENSE` file at the root of that repository). The copyright holders
are:

```
Copyright (c) Facebook, Inc. and its affiliates.
Copyright (c) tig <https://6fx.eu/>.
Copyright (c) Gusto, Inc.
Copyright (c) Equinor ASA
Copyright (c) Datamind AS
```

Because the new processor is a **derivative work** of that BSD-3-Clause code,
the `WorkSpaceOneSlacker.py` file **must** carry:

1. The full BSD-3-Clause licence text in the file header.
2. All original copyright lines listed above, **plus** a new copyright line for
   the derivative work author, e.g.
   `Copyright (c) 2026 Martinus Verburg https://github.com/codeskipper`.
3. A clear note explaining that this file is BSD-3-Clause licensed because it
   derives from `autopkg_tools_ws1_cloud_cli.py` in
   `equinor/autopkg-cicd`, while the rest of the
   WorkSpaceOneImporter-recipes project is Apache-2.0.

> **The rest of the WorkSpaceOneImporter-recipes project remains
> Apache-2.0.** Only `WorkSpaceOneSlacker.py` is BSD-3-Clause.

---

## Context & Constraints

| Item | Detail |
|---|---|
| **Runtime** | `/usr/local/autopkg/python` (AutoPkg's bundled Python 3.10) |
| **Base class** | `WorkSpaceOneImporterBase` from `ws1_lib/WorkSpaceOneImporterBase.py` — provides `self.env`, `self.output()`, `self.init_tls()`, `self.ws1_auth_prep()`, and the `main()` / `execute_shell()` contract. |
| **Formatter** | Black, line-length 120 (see `pyproject.toml`). Import sorting: isort with `profile = "black"` (`.isort.cfg`). |
| **Linter** | flake8, max-line-length 120. |
| **Dependencies** | `requests` (already installed), `plistlib` (stdlib). No additional dependencies required. |
| **Package layout** | Processor file lives at `ws1-processors/WorkSpaceOneSlacker.py`. It imports `WorkSpaceOneImporterBase` via the `ws1_lib` package already on `sys.path`. |
| **Shared-processor stub recipe** | A YAML stub recipe `ws1-processors/WorkSpaceOneSlacker.recipe.yaml` must also be created so other recipes can reference the shared processor as `com.github.codeskipper.VMWARE-WorkSpaceOneSlacker/WorkSpaceOneSlacker`. |
| **AutoPkg report plist** | Written by `autopkg run --report-plist <path>`. Path available in `self.env["REPORT_PLIST"]`. See <https://github.com/autopkg/autopkg/wiki/Processor-Summary-Reporting>. |

---

## Source Code to Port

### Primary: `slack_alert()` (lines 515–645)

```python
def slack_alert(recipe, opts):
    if int(AUTOPKG_TOOLS_VERBOSE) >= 3:
        output(
            "Skipping Slack notification - verbose level ≥3 is set.", verbose_level=3
        )
        return
    if not SLACK_WEBHOOK:
        output("Skipping slack notification - webhook is missing!", verbose_level=1)
        return

    if not recipe.verified:
        task_title = f"{recipe.name} failed trust verification"
        task_description = recipe.results["message"]
    elif recipe.error:
        task_title = f"Failed to import {recipe.name}"
        if not recipe.results["failed"]:
            task_description = "Unknown error"
        else:
            task_description = ("Error: {} \n" "Traceback: {} \n").format(
                recipe.results["failed"][0]["message"],
                recipe.results["failed"][0]["traceback"],
            )

            if "No releases found for repo" in task_description:
                # Just no updates
                return
    elif recipe.updated and not recipe.ws1_updated:
        task_title = "Munki (NOT WS1 UEM!) imported %s %s" % (
            recipe.name,
            str(recipe.updated_version),
        )
        task_description = (
            "*Catalogs:* %s \n" % recipe.results["imported"][0]["catalogs"]
            + "*Package Path:* `%s` \n" % recipe.results["imported"][0]["pkg_repo_path"]
            + "*Pkginfo Path:* `%s` \n" % recipe.results["imported"][0]["pkginfo_path"]
        )
    elif recipe.updated and recipe.ws1_updated:
        task_title = "WS1 UEM and Munki - Imported"
        task_description = (
            "*WS1 UEM* \n"
            f"App:       `{recipe.name}` \n"
            f"Version: `{recipe.results['ws1_results_data'][0]['version']}` \n"
        )
        if recipe.results["ws1_results_data"][0]["new_assignment_rules"]:
            task_description += (
                "*Assignment rules:* "
                f"`{recipe.results['ws1_results_data'][0]['new_assignment_rules']}` \n"
            )
        if recipe.results["ws1_results_data"][0]["console_location"]:
            task_description += f"<{recipe.results['ws1_results_data'][0]['console_location']}|*console location*> \n\n"
        task_description += (
            "*Munki* \n"
            f"*Catalogs:* {recipe.results['imported'][0]['catalogs']} \n"
            f"*Package Path:* `{recipe.results['imported'][0]['pkg_repo_path']}` \n"
            f"*Pkginfo Path:* `{recipe.results['imported'][0]['pkginfo_path']}` \n"
        )
        if recipe.ws1_pruned:
            task_description += (
                f"*Pruned versions:* `{recipe.results['ws1_results_data'][0]['pruned_versions']}` \n\n"
                f"*Number of versions pruned:* `{recipe.results['ws1_results_data'][0]['pruned_versions_num']}` \n"
            )
    elif recipe.ws1_updated:
        task_title = "WS1 UEM - Imported"
        task_description = (
            f"App:       `{recipe.name}` \n"
            f"Version: `{recipe.results['ws1_results_data'][0]['version']}` \n"
        )
        if recipe.results["ws1_results_data"][0]["new_assignment_rules"]:
            task_description += (
                "*Assignment rules:* "
                f"`{recipe.results['ws1_results_data'][0]['new_assignment_rules']}` \n"
            )
        if recipe.results["ws1_results_data"][0]["console_location"]:
            task_description += f"<{recipe.results['ws1_results_data'][0]['console_location']}|*console location*> \n"
        if recipe.ws1_pruned:
            task_description += (
                f"*Pruned versions:* `{recipe.results['ws1_results_data'][0]['pruned_versions']}` \n\n"
                f"*Number of versions pruned:* `{recipe.results['ws1_results_data'][0]['pruned_versions_num']}` \n"
            )
    elif recipe.ws1_updated_assignments:
        task_title = "WS1 UEM - New Assignment Rules"
        task_description = (
            f"App:       `{recipe.name}` \n"
            f"Version: `{recipe.results['ws1_results_data'][0]['version']}` \n"
            f"*New Assignment rules:* `{recipe.results['ws1_results_data'][0]['new_assignment_rules']}` \n"
        )
        if recipe.results["ws1_results_data"][0]["console_location"]:
            task_description += f"<{recipe.results['ws1_results_data'][0]['console_location']}|*console location*> \n"
        if recipe.ws1_pruned:
            task_description += (
                f"*Pruned versions:* `{recipe.results['ws1_results_data'][0]['pruned_versions']}` \n\n"
                f"*Number of versions pruned:* `{recipe.results['ws1_results_data'][0]['pruned_versions_num']}` \n"
            )
    elif recipe.ws1_pruned:
        task_title = "WS1 UEM - old app versions pruned"
        task_description = (
            f"App:       `{recipe.name}` \n"
            f"*Pruned versions:* `{recipe.results['ws1_results_data'][0]['pruned_versions']}` \n"
            f"*Number of versions pruned:* `{recipe.results['ws1_results_data'][0]['pruned_versions_num']}` \n"
        )
    else:
        # Fall through if no updates
        return

    response = requests.post(
        SLACK_WEBHOOK,
        data=json.dumps(
            {
                "attachments": [
                    {
                        "username": "Autopkg",
                        "as_user": True,
                        "title": task_title,
                        "color": (
                            "warning"
                            if not recipe.verified
                            else "good" if not recipe.error else "danger"
                        ),
                        "text": task_description,
                        "mrkdwn_in": ["text"],
                    }
                ]
            }
        ),
        headers={"Content-Type": "application/json"},
    )
    if response.status_code != 200:
        raise ValueError(
            "Request to slack returned an error %s, the response is:\n%s"
            % (response.status_code, response.text)
        )
```

### Supporting: `Recipe._parse_report()` (lines 228–262) — port this logic

```python
def _parse_report(self, report):
    with open(report, "rb") as f:
        report_data = plistlib.load(f)

    failed_items = report_data.get("failures", [])
    imported_items = []
    ws1_results_data = []
    if report_data["summary_results"]:
        # This means something happened
        munki_results = report_data["summary_results"].get(
            "munki_importer_summary_result", {}
        )
        imported_items.extend(munki_results.get("data_rows", []))

        if "ws1_importer_summary_result" in report_data["summary_results"]:
            # meaning ws1 has done something
            ws1_results = report_data["summary_results"].get(
                "ws1_importer_summary_result", {}
            )
            ws1_results_header = ws1_results.get("header", {})
            if "new_assignment_rules" in ws1_results_header:
                self.ws1_updated_assignments = True
            if "pruned_versions" in ws1_results_header:
                self.ws1_pruned = True
            if (
                ws1_results["summary_text"]
                and "imported" in ws1_results["summary_text"]
            ):
                self.ws1_updated = True
            ws1_results_data.extend(ws1_results.get("data_rows", []))
    return {
        "imported": imported_items,
        "failed": failed_items,
        "ws1_results_data": ws1_results_data,
    }
```

### Supporting: `Recipe` class attributes (lines 116–131) — for reference

```python
class Recipe(object):
    def __init__(self, path):
        self.path = os.path.join(OVERRIDES_DIR, path)
        self.error = False
        self.results = {}
        self.updated = False
        self.ws1_updated = False
        self.ws1_updated_assignments = False
        self.ws1_pruned = False
        self.verified = None
        self._keys = None
        self._has_run = False
        self._name = None
```

### Supporting: `Recipe.updated_version` property (lines 158–163)

```python
@property
def updated_version(self):
    if not self.results or not self.results["imported"]:
        return None
    return self.results["imported"][0]["version"].strip().replace(" ", "")
```

---

## Report Plist Mapping

The processor reads the report plist and maps its contents to the same
variable names used in the original `slack_alert()`:

| Original `recipe.*` / `recipe.results[*]` | Report plist path | Notes |
|---|---|---|
| `recipe.results["imported"]` | `report["summary_results"]["munki_importer_summary_result"]["data_rows"]` | List of dicts; each has `name`, `version`, `catalogs`, `pkg_repo_path`, `pkginfo_path` |
| `recipe.results["failed"]` | `report["failures"]` | List of dicts with `message`, `traceback` |
| `recipe.results["ws1_results_data"]` | `report["summary_results"]["ws1_importer_summary_result"]["data_rows"]` | List of dicts; each has `version`, `new_assignment_rules`, `console_location`, `pruned_versions`, `pruned_versions_num` |
| `recipe.updated` | `bool(imported_items)` | True if Munki imported something |
| `recipe.updated_version` | `imported_items[0]["version"]` if `imported_items` else `None` | |
| `recipe.ws1_updated` | `"imported" in ws1_summary_text` | From `ws1_importer_summary_result["summary_text"]` |
| `recipe.ws1_updated_assignments` | `"new_assignment_rules" in ws1_header` | From `ws1_importer_summary_result["header"]` |
| `recipe.ws1_pruned` | `"pruned_versions" in ws1_header` | From `ws1_importer_summary_result["header"]` |
| `recipe.name` | `self.env.get("NAME", "Unknown App")` | From recipe Input, available in `self.env` |
| `recipe.verified` | `self.env.get("ws1_slack_trust_verified", "True")` | New input variable (string bool) |
| `recipe.error` | `bool(failed_items)` | True if `failures` list is non-empty |
| `recipe.results["message"]` | `self.env.get("ws1_slack_failure_message", "")` | For trust-verification failure text |

### Fallback when `REPORT_PLIST` is not available

If `self.env.get("REPORT_PLIST")` is not set or the file does not exist, the
processor should fall back to reading state from `self.env` directly:

| Fallback `self.env` key | Set by | Maps to |
|---|---|---|
| `munki_importer_summary_result` | `MunkiImporter` | Dict with `data` sub-dict → treat as single-item equivalent of `data_rows` |
| `ws1_importer_summary_result` | `WorkSpaceOneImporter` | Dict with `summary_text`, `report_fields`, `data` sub-dict |
| `ws1_imported_new` | `WorkSpaceOneImporter` | Bool → `ws1_updated` |
| `ws1_app_assignments_changed` | `WorkSpaceOneImporter` | Bool → `ws1_updated_assignments` |
| `ws1_pruned` | `WorkSpaceOneImporter` | Bool → `ws1_pruned` |
| `ws1_stderr` | `WorkSpaceOneImporter` | Error text |

Implement the fallback as a private method `_gather_state_from_env()` that
returns the same structure as `_parse_report_plist()`, so the notification
logic in `main()` works identically regardless of data source.

---

## Target File Layout

```
ws1-processors/
├── WorkSpaceOneImporter.py
├── WorkSpaceOneImporter.recipe.yaml
├── WorkSpaceOneSlacker.py                  # NEW — this processor
├── WorkSpaceOneSlacker.recipe.yaml         # NEW — stub recipe for shared-processor use
├── ws1_lib/
│   ├── __init__.py
│   └── WorkSpaceOneImporterBase.py
└── ...
```

---

## Detailed Instructions

### A. Create `ws1-processors/WorkSpaceOneSlacker.py`

1. **Shebang** — `#!/usr/local/autopkg/python`

2. **Licence header** — BSD-3-Clause (full text) with all original copyright
   lines plus the derivative-work author. Add a `NOTE:` comment explaining the
   dual-licence situation (this file is BSD-3-Clause; rest of project is
   Apache-2.0).

3. **Module docstring**:
   ```python
   """Autopkg processor to send Slack webhook notifications about WorkSpaceOne import results."""
   ```

4. **Imports**:
   ```python
   import json
   import os
   import plistlib
   import sys

   import requests
   from autopkglib import ProcessorError

   sys.path.insert(0, os.path.dirname(__file__))

   from ws1_lib.WorkSpaceOneImporterBase import WorkSpaceOneImporterBase  # noqa: E402
   ```

5. **`__all__`**:
   ```python
   __all__ = ["WorkSpaceOneSlacker"]
   ```

6. **Class definition**:
   ```python
   class WorkSpaceOneSlacker(WorkSpaceOneImporterBase):
   ```
   Inheriting from `WorkSpaceOneImporterBase` gives the processor TLS init for
   free (needed because the Slack webhook POST uses `requests` which respects
   `REQUESTS_CA_BUNDLE`). The auth-related input variables from the base class
   are harmlessly present; they are `required: False` and simply ignored if not
   supplied.

7. **`input_variables`** — merge base class variables + add Slacker-specific
   ones:

   ```python
   input_variables = {
       **WorkSpaceOneImporterBase.input_variables,
       "ws1_slack_webhook_url": {
           "required": True,
           "description": "Slack incoming-webhook URL to post notifications to.",
       },
       "ws1_slack_channel": {
           "required": False,
           "description": "Override Slack channel (optional, uses webhook default if omitted).",
       },
       "ws1_slack_username": {
           "required": False,
           "default": "Autopkg",
           "description": "Display name for the Slack bot. Default: Autopkg.",
       },
       "ws1_slack_icon_url": {
           "required": False,
           "description": "URL for the Slack bot icon (optional).",
       },
       "ws1_slack_trust_verified": {
           "required": False,
           "default": "True",
           "description": 'Set to "False" by a trust-verification wrapper to trigger '
                          'a trust-failure alert. Default: "True".',
       },
       "ws1_slack_failure_message": {
           "required": False,
           "description": "Error/traceback text from a prior step, for inclusion in failure notifications.",
       },
   }
   ```

8. **`output_variables`**:

   ```python
   output_variables = {
       "ws1_slacker_summary_result": {
           "description": "Summary of the Slack notification that was sent.",
       },
   }
   ```

9. **`_parse_report_plist()` private method** — ported from
   `Recipe._parse_report()`:

   ```python
   def _parse_report_plist(self, report_path):
       """Parse the AutoPkg report plist and return extracted results.

       Returns a dict with keys: imported, failed, ws1_results_data,
       ws1_updated, ws1_updated_assignments, ws1_pruned.
       """
       with open(report_path, "rb") as f:
           report_data = plistlib.load(f)

       failed_items = report_data.get("failures", [])
       imported_items = []
       ws1_results_data = []
       ws1_updated = False
       ws1_updated_assignments = False
       ws1_pruned = False

       summary_results = report_data.get("summary_results", {})
       if summary_results:
           munki_results = summary_results.get("munki_importer_summary_result", {})
           imported_items.extend(munki_results.get("data_rows", []))

           if "ws1_importer_summary_result" in summary_results:
               ws1_results = summary_results["ws1_importer_summary_result"]
               ws1_header = ws1_results.get("header", [])
               if "new_assignment_rules" in ws1_header:
                   ws1_updated_assignments = True
               if "pruned_versions" in ws1_header:
                   ws1_pruned = True
               summary_text = ws1_results.get("summary_text", "")
               if summary_text and "imported" in summary_text:
                   ws1_updated = True
               ws1_results_data.extend(ws1_results.get("data_rows", []))

       return {
           "imported": imported_items,
           "failed": failed_items,
           "ws1_results_data": ws1_results_data,
           "ws1_updated": ws1_updated,
           "ws1_updated_assignments": ws1_updated_assignments,
           "ws1_pruned": ws1_pruned,
       }
   ```

10. **`_gather_state_from_env()` private method** — fallback when no report
    plist is available:

    ```python
    def _gather_state_from_env(self):
        """Gather recipe run state from self.env (fallback when REPORT_PLIST is unavailable)."""
        imported_items = []
        munki_summary = self.env.get("munki_importer_summary_result")
        if isinstance(munki_summary, dict) and munki_summary.get("data"):
            imported_items.append(munki_summary["data"])

        ws1_results_data = []
        ws1_summary = self.env.get("ws1_importer_summary_result")
        if isinstance(ws1_summary, dict) and ws1_summary.get("data"):
            ws1_results_data.append(ws1_summary["data"])

        failed_items = []
        ws1_stderr = self.env.get("ws1_stderr", "")
        failure_message = self.env.get("ws1_slack_failure_message", "")
        if ws1_stderr or failure_message:
            failed_items.append({
                "message": failure_message or ws1_stderr,
                "traceback": "",
            })

        return {
            "imported": imported_items,
            "failed": failed_items,
            "ws1_results_data": ws1_results_data,
            "ws1_updated": bool(self.env.get("ws1_imported_new", False)),
            "ws1_updated_assignments": bool(self.env.get("ws1_app_assignments_changed", False)),
            "ws1_pruned": bool(self.env.get("ws1_pruned", False)),
        }
    ```

11. **`_post_to_slack()` helper method**:

    ```python
    def _post_to_slack(self, webhook_url, title, description, color):
        """Post a Slack message attachment via incoming webhook."""
    ```

    - Build the payload dict with `attachments` array matching the original
      structure: `username`, `as_user`, `title`, `color`, `text`,
      `mrkdwn_in`.
    - Optionally include `channel` and `icon_url` if the corresponding input
      variables are set.
    - POST with `requests.post()`, raise `ProcessorError` on non-200.
    - Set `self.env["ws1_slacker_summary_result"]` on success.

12. **`main()` method** — the core notification logic, ported from
    `slack_alert()`:

    ```python
    def main(self):
        """Evaluate recipe run results and send appropriate Slack notification."""
    ```

    Implementation steps:

    a. **Guard: high verbosity** — if `int(self.env.get("verbose", 1)) >= 3`,
       log a message and return without sending a notification (matches
       original line 516–519).

    b. **Guard: missing webhook** — if `ws1_slack_webhook_url` is empty/None,
       log and return (matches original lines 521–523).

    c. **Gather state** — determine data source:
       ```python
       report_path = self.env.get("REPORT_PLIST")
       if report_path and os.path.isfile(report_path):
           self.output(f"Reading results from report plist: {report_path}")
           results = self._parse_report_plist(report_path)
       else:
           self.output("REPORT_PLIST not available, falling back to environment variables.")
           results = self._gather_state_from_env()
       ```

    d. **Extract variables** from the `results` dict:
       - `app_name` ← `self.env.get("NAME", "Unknown App")`
       - `trust_verified` ← parse string-bool from `ws1_slack_trust_verified`
       - `failure_message` ← `ws1_slack_failure_message`
       - `has_error` ← `bool(results["failed"])`
       - `imported_items` ← `results["imported"]`
       - `munki_updated` ← `bool(imported_items)`
       - `updated_version` ← `imported_items[0]["version"]` if
         `imported_items` else `None`
       - `ws1_updated` ← `results["ws1_updated"]`
       - `ws1_updated_assignments` ← `results["ws1_updated_assignments"]`
       - `ws1_pruned` ← `results["ws1_pruned"]`
       - `ws1_results_data` ← `results["ws1_results_data"]`

    e. **Scenario chain** — evaluate in the same priority order as
       `slack_alert()`:

       | Priority | Condition | Original lines |
       |---|---|---|
       | 1 | Trust not verified | 525–527 |
       | 2 | Recipe error | 528–540 |
       | 2a | ↳ "No releases found" → return silently | 538–540 |
       | 3 | Munki updated, WS1 NOT updated | 541–550 |
       | 4 | Munki updated AND WS1 updated | 551–575 |
       | 5 | WS1 updated (no new Munki) | 576–593 |
       | 6 | WS1 assignments updated only | 594–607 |
       | 7 | WS1 pruned only | 608–614 |
       | 8 | Fall-through → return, no notification | 615–617 |

       For each scenario build `task_title`, `task_description`, and `color`
       matching the original strings as closely as possible (substituting
       `results[*]` access for `recipe.results[*]` access per the mapping
       table).

    f. **Determine color** (matching original lines 628–632):
       ```python
       if not trust_verified:
           color = "warning"
       elif has_error:
           color = "danger"
       else:
           color = "good"
       ```

    g. **Call `self.init_tls()`** — ensure TLS certificates are configured
       before making the HTTPS request to Slack.

    h. **Call `self._post_to_slack()`** with the assembled values.

13. **`if __name__ == "__main__"` block**:
    ```python
    if __name__ == "__main__":
        PROCESSOR = WorkSpaceOneSlacker()
        PROCESSOR.execute_shell()
    ```

### B. Create `ws1-processors/WorkSpaceOneSlacker.recipe.yaml`

```yaml
Description: |
  This is the yaml stub recipe for WorkSpaceOneSlacker shared processor, so it can be
  used by another recipe outside of this repo.
  Sends Slack webhook notifications about WorkSpaceOne import results.
  Instead of setting the 'Processor' key to a processor name only, we separate the
  recipe identifier and the processor name with a slash:
  Processor: com.github.codeskipper.VMWARE-WorkSpaceOneSlacker/WorkSpaceOneSlacker

Identifier: com.github.codeskipper.VMWARE-WorkSpaceOneSlacker
Input: {}
MinimumVersion: "2.3"
Process: []
```

### C. Example recipe usage

To use the new processor, add it as a step **after** `WorkSpaceOneImporter` in
a `.ws1.recipe.yaml`:

```yaml
Process:
- Processor: com.github.codeskipper.VMWARE-WorkSpaceOneImporter/WorkSpaceOneImporter
  Arguments:
    # ... WS1 arguments ...

- Processor: com.github.codeskipper.VMWARE-WorkSpaceOneSlacker/WorkSpaceOneSlacker
  Arguments:
    ws1_slack_webhook_url: '%WS1_SLACK_WEBHOOK_URL%'
```

**Important:** When running `autopkg`, pass `--report-plist` to enable
report-plist-based result reading:

```sh
autopkg run --report-plist /tmp/autopkg_report.plist \
  SomeApp.ws1.recipe.yaml
```

Or use it as an AutoPkg **post-processor**:

```sh
autopkg run --report-plist /tmp/autopkg_report.plist \
  --post-processor com.github.codeskipper.VMWARE-WorkSpaceOneSlacker/WorkSpaceOneSlacker \
  --key ws1_slack_webhook_url="https://hooks.slack.com/services/..." \
  SomeApp.ws1.recipe.yaml
```

---

## Validation Checklist

- [ ] `python -m py_compile ws1-processors/WorkSpaceOneSlacker.py` passes.
- [ ] `python -m py_compile ws1-processors/WorkSpaceOneSlacker.recipe.yaml`
      is valid YAML (parse with `python -c "import yaml; yaml.safe_load(open(...))"` or
      `pre-commit-macadmin check-autopkg-recipes --strict`).
- [ ] Black formatting: `black --check --line-length 120 ws1-processors/WorkSpaceOneSlacker.py`.
- [ ] isort: `isort --check --profile black ws1-processors/WorkSpaceOneSlacker.py`.
- [ ] flake8: `flake8 --max-line-length 120 ws1-processors/WorkSpaceOneSlacker.py`.
- [ ] The file header contains the full BSD-3-Clause licence text with all
      original copyright holders.
- [ ] The `input_variables` dict merges the base class with
      `**WorkSpaceOneImporterBase.input_variables`.
- [ ] `_parse_report_plist()` correctly parses the report plist structure
      matching the original `_parse_report()` logic.
- [ ] `_gather_state_from_env()` provides a working fallback when
      `REPORT_PLIST` is not available.
- [ ] All notification scenarios from the original `slack_alert()` are covered
      in the same priority order.
- [ ] The Slack payload structure (JSON with `attachments` array) matches the
      original.
- [ ] Running a `.ws1.recipe.yaml` with `--report-plist` that chains
      `WorkSpaceOneImporter` → `WorkSpaceOneSlacker` sends the expected Slack
      notification.
- [ ] Running without `--report-plist` falls back to `self.env` and still works.
- [ ] Running with `verbose >= 3` suppresses the Slack notification.
- [ ] Running without `ws1_slack_webhook_url` suppresses the Slack notification
      gracefully (no error).

---

## Notes

- The processor inherits `WorkSpaceOneImporterBase` primarily for TLS init
  (`self.init_tls()`). It does **not** need WS1 API authentication — it only
  makes an HTTPS POST to a Slack webhook. The inherited auth input variables
  are all `required: False` and are simply ignored.
- The `ws1_slack_trust_verified` and `ws1_slack_failure_message` input
  variables are designed for use by an external trust-verification wrapper
  script that sets them before invoking the recipe. In normal recipe runs
  they default to `True` and empty respectively.
- The "No releases found for repo" silent-return behaviour (original line
  538–540) is preserved to avoid noisy alerts when a GitHub release simply
  has no updates.
- The primary data source is the **report plist** (`REPORT_PLIST`), which
  gives the processor access to the same rich `data_rows` arrays that the
  original `_parse_report()` used. The `self.env` fallback is provided for
  cases where `--report-plist` is not passed to `autopkg run`, but it may
  have less data (e.g. only a single `data` dict instead of `data_rows`
  arrays).
