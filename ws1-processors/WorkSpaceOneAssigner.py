#!/usr/local/autopkg/python
#
# WorkSpaceOneAssigner.py - a custom Autopkg processor
# Copyright 2022 Martinus Verburg https://github.com/codeskipper
# Adapted from https://github.com/jprichards/AirWatchImporter/blob/master/AirWatchImporter.py by
#     John Richards https://github.com/jprichards and
#     Jeremy Baker https://github.com/jbaker10
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Autopkg processor to manage app assignments in Omnissa Workspace ONE UEM using REST API V1 & V2."""

import json
import os
import sys
from datetime import datetime, timedelta

import requests
from autopkglib import ProcessorError

# Ensure ws1_lib package (sibling directory) is importable
# Helpful comments copied from processors in https://github.com/autopkg/grahampugh-recipes
# To use a base module in AutoPkg we need to add this path to the sys.path.
# This violates flake8 E402 (PEP8 imports) but is unavoidable, so the following
# imports require noqa comments for E402
sys.path.insert(0, os.path.dirname(__file__))

from ws1_lib.WorkSpaceOneImporterBase import WorkSpaceOneImporterBase, is_url  # noqa: E402

__all__ = ["WorkSpaceOneAssigner"]


class WorkSpaceOneAssigner(WorkSpaceOneImporterBase):
    """Manages app assignments (simple V1 & advanced V2) in Workspace ONE UEM.

    Searches for the app by NAME on the WS1 server, determines the latest version,
    and applies assignments to it. Uses app UUID as the primary identifier.
    """

    input_variables = {
        **WorkSpaceOneImporterBase.input_variables,
        "ws1_console_url": {
            "required": False,
            "description": "Base url of WorkSpace ONE UEM Console server for easy result lookup "
            "(eg. https://admin-mobile.myorg.com)",
        },
        "ws1_smart_group_name": {
            "required": False,
            "description": "The name of the smart group the app should be assigned to (simple V1 assignment).",
        },
        "ws1_push_mode": {
            "required": False,
            "description": "For a simple app assignment, how to deploy the app: 'Auto' or 'On-Demand' (V1 only).",
        },
        "ws1_app_assignments": {
            "required": False,
            "description": "Advanced app assignments (API V2 rules). Complex structure — "
            "see https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_app_assignments\n",
        },
    }

    output_variables = {
        "ws1_app_uuid": {
            "description": "Application UUID of the latest app version found on WS1 UEM.",
        },
        "ws1_app_id": {
            "description": "Application numeric ID of the latest app version found on WS1 UEM.",
        },
        "ws1_app_assignments_changed": {
            "description": "True if any app assignments were successfully applied.",
        },
        "ws1_importer_summary_result": {
            "description": "Dictionary with summary of assignment changes for reporting.",
        },
    }

    description = __doc__

    def get_smartgroup_id(self, base_url, smartgroup, headers):
        """Get Smart Group ID and UUID to assign the package to."""

        # we need to replace any spaces with '%20' for the API call
        condensed_sg = smartgroup.replace(" ", "%20")
        r = requests.get(
            f"{base_url}/api/mdm/smartgroups/search?name={condensed_sg}",
            headers=headers,
        )
        if not r.status_code == 200:
            raise ProcessorError(
                f"WorkSpaceOneAssigner: No SmartGroup ID found for SmartGroup {smartgroup} - bailing out."
            )
        sg_uuid = sg_id = ""
        try:
            smart_group_results = r.json()
            for sg in smart_group_results["SmartGroups"]:
                if smartgroup in sg["Name"]:
                    sg_id = sg["SmartGroupID"]
                    self.output(f"Smart Group ID: {sg_id}", verbose_level=2)
                    sg_uuid = sg["SmartGroupUuid"]
                    self.output(f"Smart Group UUID: {sg_uuid}", verbose_level=2)
                    break
        except (ValueError, TypeError):
            raise ProcessorError("Failed to parse results from Smart Group search API call")
        return sg_id, sg_uuid

    @staticmethod
    def _parse_version_tuple(version_str):
        """Parse a version string into a tuple of integers for comparison.

        The WS1 API returns AppVersion as a normalized 4-component string (e.g. "1.118.1.0").
        This method splits on '.' and converts each component to int, enabling reliable
        tuple comparison: (1, 118, 1, 0) < (1, 119, 0, 0).

        Args:
            version_str: Version string like "1.118.1.0".

        Returns:
            Tuple of integers, or empty tuple if parsing fails.
        """
        try:
            return tuple(int(x) for x in version_str.split("."))
        except (ValueError, AttributeError):
            return ()

    def find_latest_app_version(self, search_results, app_name):
        """Find the latest macOS app version from WS1 search results.

        Iterates through search results to find all macOS (Platform==10) apps matching app_name,
        then determines the latest by comparing the normalized AppVersion field (always 4 components,
        e.g. "1.118.1.0") as integer tuples. Falls back to highest App ID if version parsing fails.

        Args:
            search_results: JSON response dict from the app search API.
            app_name: Application name to match.

        Returns:
            Dict with keys: app_id, app_uuid, app_version.

        Raises:
            ProcessorError: If no matching macOS app is found.
        """
        matching_apps = []
        for app in search_results["Application"]:
            if app["Platform"] == 10 and app["ApplicationName"] in app_name:
                matching_apps.append(
                    {
                        "app_id": app["Id"]["Value"],
                        "app_uuid": app["Uuid"],
                        "app_version": app["ActualFileVersion"],
                        "app_version_sortable": app.get("AppVersion", ""),
                    }
                )
                self.output(
                    f"Found app: ID [{app['Id']['Value']}] UUID [{app['Uuid']}] "
                    f"version [{app['ActualFileVersion']}] AppVersion [{app.get('AppVersion', '')}]",
                    verbose_level=2,
                )

        if not matching_apps:
            raise ProcessorError(f"WorkSpaceOneAssigner: No macOS app matching [{app_name}] found on WS1 server.")

        # Determine the latest version using the normalized AppVersion field (4-component, e.g. "1.118.1.0")
        # which allows reliable semantic version comparison via integer tuples.
        # Fall back to highest App ID if AppVersion is missing or unparseable.
        latest = max(
            matching_apps,
            key=lambda x: self._parse_version_tuple(x["app_version_sortable"]) or (int(x["app_id"]),),
        )
        self.output(
            f"Latest app version: ID [{latest['app_id']}] UUID [{latest['app_uuid']}] "
            f"version [{latest['app_version']}]",
            verbose_level=1,
        )
        return latest

    def ws1_app_assign_v1(self, base_url, smart_group, assignment_pushmode, headers, ws1_app_id):
        """Create a simple V1 app assignment to a single smart group.

        Assembles assignment parameters and calls WS1 API V1:
        POST /apps/internal/{applicationId}/assignments
        """
        sg_id, sg_uuid = self.get_smartgroup_id(base_url, smart_group, headers)
        set_macos_desired_state_management = assignment_pushmode == "Auto"
        app_assignment = {
            "SmartGroupIds": [sg_id],
            "DeploymentParameters": {
                "PushMode": assignment_pushmode,
                "AssignmentId": 1,
                "MacOsDesiredStateManagement": set_macos_desired_state_management,
                "RemoveOnUnEnroll": False,
                "AutoUpdateDevicesWithPreviousVersion": True,
                "VisibleInAppCatalog": True,
            },
        }

        try:
            payload = json.dumps(app_assignment)
            self.output(f"App assignment data to send: {app_assignment}", verbose_level=2)
        except ValueError:
            raise ProcessorError("Failed to parse App assignment as json")

        try:
            r = requests.post(
                f"{base_url}/api/mam/apps/internal/{ws1_app_id}/assignments",
                headers=headers,
                data=payload,
            )
        except requests.exceptions.RequestException:
            raise ProcessorError(
                f"Something went wrong assigning the app [{self.env['NAME']}] to group [{smart_group}]"
            )
        if not r.status_code == 201:
            result = r.json()
            self.output(
                f"App assignment failed: {result['errorCode']} - {result['message']}",
                verbose_level=2,
            )
            raise ProcessorError(f"Unable to assign the app [{self.env['NAME']}] to the group [{smart_group}]")
        self.env["ws1_app_assignments_changed"] = True
        self.output(f"Successfully assigned the app [{self.env['NAME']}] to the group [{smart_group}]")

    def ws1_app_assign_v2(self, api_base_url, app_assignments, headers, ws1_app_uuid, app_name, app_version):
        """
        Apply advanced assignment rules via API V2.
        MAM REST API V2 — PUT /apps/{applicationUuid}/assignment-rules

        NB - an App Assignment Rule with an effective_date in the future causes previous versions of the app to NOT be
        deployed to newly enrolled devices, and NOT be offered in the Hub and user portal. Neither will the app version
        with effective_date in the future be deployed or be offered in the Hub or user portal before effective_date.
        For that reason, we need to postpone setting such assignment rules until effective_date, and skip those set
        for a future date until next autopkg session.
        """
        console_url = self.env.get("ws1_console_url")
        if not is_url(console_url):
            self.output(
                f"WS1 Console URL input value [{console_url}] does not look like a valid URL, setting example value",
                verbose_level=2,
            )
            console_url = "https://my-mobile-admin-console.my-org.org"

        self.output(f"ws1_app_uuid: [{ws1_app_uuid}]", verbose_level=2)

        # prepare API V2 headers
        headers_v2 = dict(headers)
        headers_v2["Accept"] = f"{headers['Accept']};version=2"
        self.output(f"API v.2 call headers: {headers_v2}", verbose_level=4)

        # default day0 to today; will be overridden if existing assignment has an effective_date
        ws1_app_ass_day0 = datetime.today().date()

        # get any existing assignment rules and see if they need updating
        try:
            r = requests.get(
                f"{api_base_url}/api/mam/apps/{ws1_app_uuid}/assignment-rules",
                headers=headers_v2,
            )
            result = r.json()
        except requests.exceptions.RequestException as err:
            raise ProcessorError(f"API call to get existing app assignment rules failed, error: {err}")
        if not r.status_code == 200:
            raise ProcessorError(
                f"WorkSpaceOneAssigner: Unable to get existing app assignment rules from WS1 "
                f"- message: {result['message']}."
            )
        if not result["assignments"]:
            self.output(
                "No existing Assignment Rules found — will create new ones.",
                verbose_level=1,
            )
        elif result["assignments"]:
            for index, assignment in enumerate(result["assignments"]):
                self.output(
                    f"Existing assignment #[{index}] is [{assignment}]",
                    verbose_level=2,
                )
                if assignment["distribution"]["description"]:
                    if "#AUTOPKG_DONE" in assignment["distribution"]["description"]:
                        self.output(
                            "Assignment Rules are already marked as complete.",
                            verbose_level=1,
                        )
                        return
                    if "#AUTOPKG" not in assignment["distribution"]["description"]:
                        self.output(
                            "Assignment Rule description is NOT tagged as made by Autopkg - skipping.",
                            verbose_level=1,
                        )
                        return
                else:
                    self.output(
                        "Assignment Rule description not present, so NOT tagged as made by Autopkg - skipping.",
                        verbose_level=1,
                    )
                    return

            # if there's an existing assignment rule, use its effective_date as base deployment date
            if result["assignments"][0]["distribution"]["effective_date"]:
                # ugly hack to split just the date at the T from the returned ISO-8601 as we don't care about the
                # time may have a float as seconds or an int
                # no timezone is returned in UEM v.22.12 but suspect that might change
                # datetime.fromisoformat() can't handle the above in current Python v3.10
                # alternative would be to install python-dateutil but that would introduce a new dependency
                edate = "".join(result["assignments"][0]["distribution"]["effective_date"].split("T", 1)[:1])
                self.output(
                    f"Deployment date found in existing assignment #0: {[edate]} ",
                    verbose_level=2,
                )
                ws1_app_ass_day0 = datetime.fromisoformat(edate).date()

        # process assignment rules from recipe input
        self.output(
            f"Assignments recipe input var is of type: [{type(app_assignments)}]",
            verbose_level=3,
        )
        self.output(f"App assignments data input: {app_assignments}", verbose_level=2)
        skip_remaining_assignments = False
        report_assignment_rules = []
        priority_index = 0
        for priority_index, app_assignment in enumerate(app_assignments):
            app_assignment["priority"] = str(priority_index)  # rules must be passed in order of ascending priority
            app_assignment["distribution"]["smart_groups"] = []
            report_assignment_rules.append(
                {
                    "priority": str(priority_index),
                    "name": app_assignment["distribution"]["name"],
                }
            )
            for smart_group_name in app_assignment["distribution"]["smart_group_names"]:
                self.output(
                    f"App assignment[{priority_index}] Smart Group name: [{smart_group_name}]",
                    verbose_level=2,
                )
                sg_id, sg_uuid = self.get_smartgroup_id(api_base_url, smart_group_name, headers)
                app_assignment["distribution"]["smart_groups"].append(sg_uuid)
            # smart_group_names is used as input, NOT in API call
            del app_assignment["distribution"]["smart_group_names"]
            distr_delay_days = app_assignment["distribution"]["distr_delay_days"]
            self.output(f"distr_delay_days: {distr_delay_days}", verbose_level=3)
            if distr_delay_days == "0":
                app_assignment["distribution"]["effective_date"] = ws1_app_ass_day0.isoformat()
            else:
                # calculate effective_date to use in API call
                num_delay_days = int(distr_delay_days)
                self.output(
                    f"smart group deployment delay for assignment[{priority_index}] is: [{num_delay_days}] days",
                    verbose_level=2,
                )
                deploy_date = ws1_app_ass_day0 + timedelta(days=num_delay_days)
                self.output(
                    f"That makes the deploy date for assignment[{priority_index}]: [{deploy_date.isoformat()}].",
                    verbose_level=2,
                )

                # Assignments must be deployed after their designated date, otherwise they would 'hide' previous
                # versions
                if deploy_date > datetime.today().date():
                    skip_remaining_assignments = True
                    break
                app_assignment["distribution"]["effective_date"] = deploy_date.isoformat()
            # distr_delay_days is used as input, NOT in API call
            del app_assignment["distribution"]["distr_delay_days"]

            if app_assignment["distribution"]["keep_app_updated_automatically"]:
                # need to pass auto_update_devices_with_previous_versions as well to have apps update automatically
                app_assignment["distribution"]["auto_update_devices_with_previous_versions"] = True
            else:
                app_assignment["distribution"]["auto_update_devices_with_previous_versions"] = False

            # If we made it to the last assignment...
            if priority_index == (len(app_assignments) - 1):
                # add a tag to the assignment description to signify Autopkg processing is complete
                app_assignment["distribution"]["description"] += " #AUTOPKG_DONE"
            else:
                # add a tag to the assignment description to signify it is handled by Autopkg
                app_assignment["distribution"]["description"] += " #AUTOPKG"
        if skip_remaining_assignments:
            del app_assignments[priority_index:]
            del report_assignment_rules[priority_index:]
            self.output(
                f"Skipping remaining assignments from index [{priority_index}] as they are designated for a "
                f"future date.",
                verbose_level=1,
            )

        # remove existing assignments from report_assignment_rules
        report_assignment_rules = report_assignment_rules[len(result["assignments"]) :]

        # if the same number of assignments exist already, bail out
        if len(app_assignments) <= len(result["assignments"]):
            self.output("No new assignments to make at this time.", verbose_level=1)
            return
        else:
            self.output(f"App assignments data to send: {app_assignments}", verbose_level=3)
            try:
                assignment_rules = {"assignments": app_assignments}
                payload = json.dumps(assignment_rules)
                self.output(
                    f"App assignments data to send as json: {payload}",
                    verbose_level=2,
                )
            except ValueError as err:
                raise ProcessorError(f"Failed parsing app assignments as json, error: {err}")

            try:
                # Make the WS1 APIv2 call to assign the App
                r = requests.put(
                    f"{api_base_url}/api/mam/apps/{ws1_app_uuid}/assignment-rules",
                    headers=headers_v2,
                    data=payload,
                )
            except requests.exceptions.RequestException as err:
                raise ProcessorError(
                    f"Failed setting assignment-rules for app [{app_name}] version [{app_version}], error: {err}"
                )
            if not r.status_code == 202:
                result = r.json()
                self.output(
                    f"Setting App assignment rules failed: {result['errorCode']} - {result['message']}",
                    verbose_level=2,
                )
                raise ProcessorError(f"Unable to set assignment rules for [{app_name}] version [{app_version}]")

            self.output(f"Successfully set assignment rules for [{app_name}] version [{app_version}]")
            new_assignment_rules = ""
            for rule in report_assignment_rules:
                new_assignment_rules += f"[{rule['priority']}: {rule['name']}] "
            self.env["ws1_app_assignments_changed"] = True
            ws1_app_id = self.env["ws1_app_id"]
            app_ws1console_loc = f"{console_url}/AirWatch/#/AirWatch/Apps/Details/Internal/{ws1_app_id}/Assignment"
            self.env["ws1_importer_summary_result"] = {
                "summary_text": "The following new app assignment rules are applied in WS1:",
                "report_fields": [
                    "name",
                    "version",
                    "new_assignment_rules",
                    "console_location",
                ],
                "data": {
                    "name": app_name,
                    "version": app_version,
                    "new_assignment_rules": new_assignment_rules,
                    "console_location": app_ws1console_loc,
                },
            }

    def main(self):
        """Manage app assignments in Workspace ONE UEM.

        Searches for the app by NAME, finds the latest version via highest App ID,
        and applies the configured assignment (V1 simple or V2 advanced).
        """
        # Clear any pre-existing summary result
        if "ws1_importer_summary_result" in self.env:
            del self.env["ws1_importer_summary_result"]
        self.env["ws1_app_assignments_changed"] = False

        api_base_url = self.env.get("ws1_api_url")
        org_group_id = self.env.get("ws1_groupid")
        assignment_group = self.env.get("ws1_smart_group_name")
        assignment_pushmode = self.env.get("ws1_push_mode")
        app_assignments = self.env.get("ws1_app_assignments")
        console_url = self.env.get("ws1_console_url")

        # Validate mutual exclusivity of V1 vs V2 assignment modes
        has_simple = assignment_group and assignment_group != "none"
        has_advanced = app_assignments and app_assignments != "none"
        if has_simple and has_advanced:
            raise ProcessorError(
                "WorkSpaceOneAssigner: Both ws1_smart_group_name and ws1_app_assignments are specified. "
                "Please use only one assignment mode (V1 simple OR V2 advanced)."
            )
        if not has_simple and not has_advanced:
            self.output(
                "Neither ws1_smart_group_name nor ws1_app_assignments specified — nothing to assign.",
                verbose_level=1,
            )
            return

        app_name = self.env.get("NAME")
        if not app_name:
            raise ProcessorError("WorkSpaceOneAssigner: NAME is not set — cannot determine which app to assign.")

        self.output(f"Beginning the WorkSpace ONE assignment process for {app_name}.")

        # Init TLS and authenticate
        self.init_tls()
        headers, headers_v2 = self.ws1_auth_prep()

        # Resolve Organization Group numeric ID
        ogid = self.resolve_ogid(api_base_url, org_group_id, headers_v2)

        # Search for existing app versions on WS1 by NAME
        search_results = self.search_apps(api_base_url, ogid, app_name, headers)
        if search_results is None:
            raise ProcessorError(f"WorkSpaceOneAssigner: App [{app_name}] not found on WS1 server — cannot assign.")
        if "Application" not in search_results or not search_results["Application"]:
            raise ProcessorError(
                f"WorkSpaceOneAssigner: No matching applications for [{app_name}] found on WS1 server."
            )

        # Find the latest version (highest App ID = most recently uploaded)
        latest_app = self.find_latest_app_version(search_results, app_name)
        ws1_app_uuid = latest_app["app_uuid"]
        ws1_app_id = latest_app["app_id"]
        app_version = latest_app["app_version"]

        # Set output variables
        self.env["ws1_app_uuid"] = ws1_app_uuid
        self.env["ws1_app_id"] = ws1_app_id
        self.output(
            f"Targeting latest app version [{app_version}] UUID [{ws1_app_uuid}] for assignment.",
            verbose_level=1,
        )

        if has_simple:
            # API V1 simple assignment (uses numeric app ID)
            if not assignment_pushmode:
                raise ProcessorError("WorkSpaceOneAssigner: ws1_push_mode is required for simple (V1) assignments.")
            self.output(f"Using simple V1 assignment to group [{assignment_group}]", verbose_level=1)
            self.ws1_app_assign_v1(api_base_url, assignment_group, assignment_pushmode, headers, ws1_app_id)

            if not is_url(console_url):
                console_url = "https://my-mobile-admin-console.my-org.org"
            app_ws1console_loc = f"{console_url}/AirWatch/#/AirWatch/Apps/Details/Internal/{ws1_app_id}/Assignment"
            self.env["ws1_importer_summary_result"] = {
                "summary_text": "The following new app assignment was made in WS1:",
                "report_fields": [
                    "name",
                    "version",
                    "assignment_group",
                    "console_location",
                ],
                "data": {
                    "name": app_name,
                    "version": app_version,
                    "assignment_group": assignment_group,
                    "console_location": app_ws1console_loc,
                },
            }
        else:
            # API V2 advanced assignments (uses app UUID natively)
            self.output("Using advanced V2 assignment rules", verbose_level=1)
            self.ws1_app_assign_v2(api_base_url, app_assignments, headers, ws1_app_uuid, app_name, app_version)


if __name__ == "__main__":
    PROCESSOR = WorkSpaceOneAssigner()
    PROCESSOR.execute_shell()
