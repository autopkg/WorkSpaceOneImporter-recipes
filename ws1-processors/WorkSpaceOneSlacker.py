#!/usr/local/autopkg/python
#
# BSD-3-Clause
# Copyright (c) Facebook, Inc. and its affiliates.
# Copyright (c) tig <https://6fx.eu/>.
# Copyright (c) Gusto, Inc.
# Copyright (c) Equinor ASA
# Copyright (c) Datamind AS
# Copyright (c) 2026 Martinus Verburg https://github.com/codeskipper
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
# following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
# disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the
# following disclaimer in the documentation and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote
# products derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# NOTE: This file is licensed under the BSD-3-Clause licence because it is a derivative work of
# autopkg_tools_ws1_cloud_cli.py from https://github.com/equinor/autopkg-cicd.
# The rest of the WorkSpaceOneImporter-recipes project is licensed under the Apache License 2.0.

# Credits: takes elements from https://github.com/notverypc/autopkg-recipes/blob/master/PostProcessors/Slacker.py

"""Autopkg processor to send Slack webhook notifications about WorkSpaceOne import results."""

import json
import os
import plistlib
import sys

import requests
from autopkglib import ProcessorError

# Ensure ws1_lib package (sibling directory) is importable
# Helpful comments copied from processors in https://github.com/autopkg/grahampugh-recipes
# To use a base module in AutoPkg we need to add this path to the sys.path.
# This violates flake8 E402 (PEP8 imports) but is unavoidable, so the following
# imports require noqa comments for E402
sys.path.insert(0, os.path.dirname(__file__))
from ws1_lib.WorkSpaceOneImporterBase import WorkSpaceOneImporterBase  # noqa: E402

__all__ = ["WorkSpaceOneSlacker"]


class WorkSpaceOneSlacker(WorkSpaceOneImporterBase):
    """Send Slack webhook notifications about WorkSpaceOne import results.

    Reads results from the AutoPkg report plist (preferred) or falls back
    to environment variables set by earlier processors in the recipe chain.
    """

    description = __doc__

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
            "description": (
                'Set to "False" by a trust-verification wrapper to trigger ' 'a trust-failure alert. Default: "True".'
            ),
        },
        "ws1_slack_failure_message": {
            "required": False,
            "description": "Error/traceback text from a prior step, for inclusion in failure notifications.",
        },
    }

    output_variables = {
        "ws1_slacker_summary_result": {
            "description": "Summary of the Slack notification that was sent.",
        },
    }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

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
            failed_items.append(
                {
                    "message": failure_message or ws1_stderr,
                    "traceback": "",
                }
            )

        return {
            "imported": imported_items,
            "failed": failed_items,
            "ws1_results_data": ws1_results_data,
            "ws1_updated": bool(self.env.get("ws1_imported_new", False)),
            "ws1_updated_assignments": bool(self.env.get("ws1_app_assignments_changed", False)),
            "ws1_pruned": bool(self.env.get("ws1_pruned", False)),
        }

    def _post_to_slack(self, webhook_url, title, description, color):
        """Post a Slack message attachment via incoming webhook."""
        username = self.env.get("ws1_slack_username", "Autopkg")
        payload = {
            "attachments": [
                {
                    "username": username,
                    "as_user": True,
                    "title": title,
                    "color": color,
                    "text": description,
                    "mrkdwn_in": ["text"],
                }
            ]
        }

        channel = self.env.get("ws1_slack_channel")
        if channel:
            payload["channel"] = channel

        icon_url = self.env.get("ws1_slack_icon_url")
        if icon_url:
            payload["icon_url"] = icon_url

        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        if response.status_code != 200:
            raise ProcessorError(
                "Request to Slack returned an error %s, the response is:\n%s" % (response.status_code, response.text)
            )

        self.output(f"Slack notification sent: {title}")
        self.env["ws1_slacker_summary_result"] = {
            "summary_text": "Slack notification sent.",
            "report_fields": ["title", "color"],
            "data": {"title": title, "color": color},
        }

    # ------------------------------------------------------------------
    # Main
    # ------------------------------------------------------------------

    def main(self):
        """Evaluate recipe run results and send appropriate Slack notification."""

        # Guard: high verbosity — avoid leaking secrets in logs
        verbose = int(self.env.get("verbose", 0))
        if verbose >= 3:
            self.output("Skipping Slack notification — verbose level ≥3 is set.")
            return

        # Guard: missing webhook
        webhook_url = self.env.get("ws1_slack_webhook_url")
        if not webhook_url:
            self.output("Skipping Slack notification — webhook URL is missing.")
            return

        # Gather state — prefer report plist, fall back to env
        report_path = self.env.get("REPORT_PLIST")
        if report_path and os.path.isfile(report_path):
            self.output(f"Reading results from report plist: {report_path}")
            results = self._parse_report_plist(report_path)
        else:
            self.output("REPORT_PLIST not available, falling back to environment variables.")
            results = self._gather_state_from_env()

        # Extract variables
        app_name = self.env.get("NAME", "Unknown App")
        trust_verified_str = self.env.get("ws1_slack_trust_verified", "True")
        trust_verified = trust_verified_str.lower() not in ("false", "0", "no")
        failure_message = self.env.get("ws1_slack_failure_message", "")

        imported_items = results["imported"]
        failed_items = results["failed"]
        ws1_results_data = results["ws1_results_data"]
        munki_updated = bool(imported_items)
        has_error = bool(failed_items)
        ws1_updated = results["ws1_updated"]
        ws1_updated_assignments = results["ws1_updated_assignments"]
        ws1_pruned = results["ws1_pruned"]

        updated_version = None
        if imported_items:
            updated_version = imported_items[0].get("version", "").strip().replace(" ", "")

        # Scenario chain — same priority order as original slack_alert()
        task_title = None
        task_description = None

        if not trust_verified:
            task_title = f"{app_name} failed trust verification"
            task_description = failure_message or "Trust verification failed."
        elif has_error:
            task_title = f"Failed to import {app_name}"
            if not failed_items:
                task_description = "Unknown error"
            else:
                task_description = "Error: {} \nTraceback: {} \n".format(
                    failed_items[0].get("message", ""),
                    failed_items[0].get("traceback", ""),
                )
                if "No releases found for repo" in task_description:
                    # Just no updates — return silently
                    return
        elif munki_updated and not ws1_updated:
            task_title = "Munki (NOT WS1 UEM!) imported %s %s" % (
                app_name,
                str(updated_version),
            )
            task_description = (
                "*Catalogs:* %s \n" % imported_items[0].get("catalogs", "")
                + "*Package Path:* `%s` \n" % imported_items[0].get("pkg_repo_path", "")
                + "*Pkginfo Path:* `%s` \n" % imported_items[0].get("pkginfo_path", "")
            )
        elif munki_updated and ws1_updated:
            ws1_row = ws1_results_data[0] if ws1_results_data else {}
            task_title = "WS1 UEM and Munki - Imported"
            task_description = (
                "*WS1 UEM* \n" f"App:       `{app_name}` \n" f"Version: `{ws1_row.get('version', '')}` \n"
            )
            if ws1_row.get("new_assignment_rules"):
                task_description += f"*Assignment rules:* `{ws1_row['new_assignment_rules']}` \n"
            if ws1_row.get("console_location"):
                task_description += f"<{ws1_row['console_location']}|*console location*> \n\n"
            task_description += (
                "*Munki* \n"
                f"*Catalogs:* {imported_items[0].get('catalogs', '')} \n"
                f"*Package Path:* `{imported_items[0].get('pkg_repo_path', '')}` \n"
                f"*Pkginfo Path:* `{imported_items[0].get('pkginfo_path', '')}` \n"
            )
            if ws1_pruned:
                task_description += (
                    f"*Pruned versions:* `{ws1_row.get('pruned_versions', '')}` \n\n"
                    f"*Number of versions pruned:* `{ws1_row.get('pruned_versions_num', '')}` \n"
                )
        elif ws1_updated:
            ws1_row = ws1_results_data[0] if ws1_results_data else {}
            task_title = "WS1 UEM - Imported"
            task_description = f"App:       `{app_name}` \n" f"Version: `{ws1_row.get('version', '')}` \n"
            if ws1_row.get("new_assignment_rules"):
                task_description += f"*Assignment rules:* `{ws1_row['new_assignment_rules']}` \n"
            if ws1_row.get("console_location"):
                task_description += f"<{ws1_row['console_location']}|*console location*> \n"
            if ws1_pruned:
                task_description += (
                    f"*Pruned versions:* `{ws1_row.get('pruned_versions', '')}` \n\n"
                    f"*Number of versions pruned:* `{ws1_row.get('pruned_versions_num', '')}` \n"
                )
        elif ws1_updated_assignments:
            ws1_row = ws1_results_data[0] if ws1_results_data else {}
            task_title = "WS1 UEM - New Assignment Rules"
            task_description = (
                f"App:       `{app_name}` \n"
                f"Version: `{ws1_row.get('version', '')}` \n"
                f"*New Assignment rules:* `{ws1_row.get('new_assignment_rules', '')}` \n"
            )
            if ws1_row.get("console_location"):
                task_description += f"<{ws1_row['console_location']}|*console location*> \n"
            if ws1_pruned:
                task_description += (
                    f"*Pruned versions:* `{ws1_row.get('pruned_versions', '')}` \n\n"
                    f"*Number of versions pruned:* `{ws1_row.get('pruned_versions_num', '')}` \n"
                )
        elif ws1_pruned:
            ws1_row = ws1_results_data[0] if ws1_results_data else {}
            task_title = "WS1 UEM - old app versions pruned"
            task_description = (
                f"App:       `{app_name}` \n"
                f"*Pruned versions:* `{ws1_row.get('pruned_versions', '')}` \n"
                f"*Number of versions pruned:* `{ws1_row.get('pruned_versions_num', '')}` \n"
            )
        else:
            # Fall through — no updates, no notification
            self.output("No updates detected — skipping Slack notification.")
            return

        # Determine color
        if not trust_verified:
            color = "warning"
        elif has_error:
            color = "danger"
        else:
            color = "good"

        # Ensure TLS certificates are configured
        self.init_tls()

        # Send the notification
        self._post_to_slack(webhook_url, task_title, task_description, color)


if __name__ == "__main__":
    PROCESSOR = WorkSpaceOneSlacker()
    PROCESSOR.execute_shell()
