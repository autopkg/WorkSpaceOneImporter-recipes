#!/usr/local/autopkg/python
#
# WorkSpaceOnePruner.py - a custom Autopkg processor
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
"""Autopkg processor to prune old app versions from Omnissa Workspace ONE UEM using REST API."""

import os
import re
import sys
from datetime import datetime

import requests
from autopkglib import ProcessorError

# Ensure ws1_lib package (sibling directory) is importable
# Helpful comments copied from processors in https://github.com/autopkg/grahampugh-recipes
# To use a base module in AutoPkg we need to add this path to the sys.path.
# This violates flake8 E402 (PEP8 imports) but is unavoidable, so the following
# imports require noqa comments for E402
sys.path.insert(0, os.path.dirname(__file__))

from ws1_lib.WorkSpaceOneImporterBase import WorkSpaceOneImporterBase  # noqa: E402

__all__ = ["WorkSpaceOnePruner"]


def extract_first_integer_from_string(s):
    """Search for the first occurrence of a sequence of digits and return as int."""
    match = re.search(r"\d+", s)
    if match:
        return int(match.group())
    return None


class WorkSpaceOnePruner(WorkSpaceOneImporterBase):
    """Prunes old app versions from Workspace ONE UEM."""

    input_variables = {
        **WorkSpaceOneImporterBase.input_variables,
        "ws1_app_versions_to_keep": {
            "required": False,
            "description": "The number of versions of an app to keep in WS1. Please set this in a recipe override, if "
            "you do not the default is used.\n"
            " See also app_versions_prune.\n\n"
            "NB - please make sure to provide the input variable as type string in the recipe override, using "
            " an integer will result in a hard to trace runtime error 'expected string or bytes-like object'",
        },
        "ws1_app_versions_to_keep_default": {
            "required": False,
            "default": "5",
            "description": "The default number of versions of an app to keep in WS1. Default:5."
            "See also app_versions_prune.\nCan be set across recipes and software titles, in this case "
            " an environment variable is practical.\n"
            "NB - please make sure to provide the input variable as type string in the recipe override, using "
            " an integer will result in a hard to trace runtime error 'expected string or bytes-like object'",
        },
        "ws1_app_versions_prune": {
            "required": False,
            "default": "dry_run",
            "description": "Whether to prune old versions of an app on WS1. Possible values: True or False or "
            "dry_run. Default:dry_run. See also app_versions_to_keep.\n"
            "Can be set across recipes and software titles, in this case "
            " an environment variable is practical.",
        },
    }

    output_variables = {
        "ws1_pruned": {
            "description": "True if old app versions were pruned in this session.",
        },
        "ws1_pruner_summary_result": {
            "description": "Summary of the pruning operation.",
        },
    }

    description = __doc__

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

    def ws1_app_versions_prune(self, api_base_url, headers, app_name, search_results):
        """
        get ws1_app_versions_to_keep_default, defaults to 5
        """
        keep_versions_default_str = self.env.get("ws1_app_versions_to_keep_default", "5")
        self.output(f"ws1_app_versions_to_keep_default: {keep_versions_default_str}", verbose_level=3)
        keep_versions_default = extract_first_integer_from_string(keep_versions_default_str)
        if keep_versions_default < 1:
            self.output(
                f"ws1_app_versions_to_keep_default setting {keep_versions_default:d} is out of range, "
                "setting default of 5."
            )
            keep_versions_default = 5

        """
        NB - please make sure to provide the input variable as type string in the recipe override, providing as
          an int will result in a hard to trace runtime error "expected string or bytes-like object"
        """
        keep_versions_str = self.env.get("ws1_app_versions_to_keep")
        try:
            keep_versions = extract_first_integer_from_string(keep_versions_str)
            if keep_versions is None:
                raise ValueError("No integer found in ws1_app_versions_to_keep")
        except ValueError:
            self.output(
                f"ws1_app_versions_to_keep setting {keep_versions_str} is out of range, "
                f"setting default of {keep_versions_default}."
            )
            keep_versions = keep_versions_default

        if self.env.get("ws1_app_versions_prune", "True").lower() in ("true", "0", "t"):
            app_versions_prune = "True"
        elif self.env.get("ws1_app_versions_prune", "False").lower() in (
            "false",
            "1",
            "f",
        ):
            # app_versions_prune = "False"
            self.output("app_versions_prune is set to False, skipping")
            return None
        else:
            app_versions_prune = "dry_run"
        self.output(f"ws1_app_versions_prune is set to: {app_versions_prune}", verbose_level=2)

        num_versions_found = 0

        # prepare API V2 headers
        headers_v2 = dict(headers)
        headers_v2["Accept"] = f"{headers['Accept']};version=2"
        self.output(f"API v.2 call headers: {headers_v2}", verbose_level=4)

        self.output(f"Looking for old versions of {app_name} on WorkspaceONE")
        app_list = []

        for app in search_results["Application"]:
            if app["Platform"] == 10 and app["ApplicationName"] in app_name:
                # get assignment rules to find first deployment date
                try:
                    r = requests.get(
                        f"{api_base_url}/api/mam/apps/{app['Uuid']}/assignment-rules",
                        headers=headers_v2,
                    )
                    result = r.json()
                except requests.exceptions.RequestException:
                    raise ProcessorError("WorkSpaceOnePruner: API call to get existing app assignment rules failed")
                if not r.status_code == 200:
                    raise ProcessorError(
                        f"WorkSpaceOnePruner: Unable to get existing app assignment rules from WS1 "
                        f"- message: {result['message']}."
                    )
                try:
                    """ugly hack to split just the date at the T from the returned ISO-8601 as we don't care about the
                    time may have a float as seconds or an int
                    no timezone is returned in UEM v.22.12 but suspect that might change
                    datetime.fromisoformat() can't handle the above in current Python v3.10
                    alternative would be to install python-dateutil but that would introduce a new dependency
                    """
                    e_date = "".join(result["assignments"][0]["distribution"]["effective_date"].split("T", 1)[:1])
                    self.output(
                        f"Deployment date found in assignment #0: {[e_date]} ",
                        verbose_level=4,
                    )
                    ws1_app_ass_day0_str = datetime.fromisoformat(e_date).date().isoformat()

                    num_versions_found += 1
                    app_list.append(
                        {
                            "App_ID": app["Id"]["Value"],
                            "UUID:": app["Uuid"],
                            "version": app["ActualFileVersion"],
                            "date": ws1_app_ass_day0_str,
                            "num": app["AssignedDeviceCount"],
                            "status": "n/a",
                        }
                    )
                except IndexError:
                    self.output(
                        "Failed to find deployment date in Assignments, skipping "
                        f"version:{app['ActualFileVersion']}...!"
                    )
                    ws1_app_ass_day0_str = "UNKNOWN!"
                self.output(
                    f"App ID: [{app['Id']['Value']}] UUID: [{app['Uuid']}] "
                    f"version: [{app['ActualFileVersion']}] "
                    f"deployment date: {ws1_app_ass_day0_str} "
                    f"Assigned device count: [{app['AssignedDeviceCount']}]",
                    verbose_level=3,
                )

        self.output("Sorting app version list by date", verbose_level=4)

        # works as intended, but PyCharm code inspection throws warning, not sure if it needs type hints or how
        # see: https://stackoverflow.com/q/78764269/4326287
        # Unexpected type(s):((x: Any) -> Any)Possible type(s):(None)(Callable[Any, SupportsDunderLT | SupportsDunderGT]) # noqa: E501
        app_list.sort(key=lambda x: x["date"])

        self.output(app_list, verbose_level=4)
        self.output("Updating prune status", verbose_level=2)
        for index, row in enumerate(app_list):
            if index < (num_versions_found - keep_versions):
                row["status"] = "TO BE PRUNED"
            else:
                row["status"] = "keep"
            self.output(row, verbose_level=2)
        self.output(f"App {app_name}  - found {num_versions_found} versions")
        if app_versions_prune == "True":
            num_pruned = 0
            pruned_versions = ""
            for row in app_list:
                if row["status"] == "TO BE PRUNED":
                    self.output(f"Deleting old version {row['version']}...", verbose_level=3)

                    # safeguard against removal of versions that are still assigned to devices, hardcoded limit for now
                    if int(row["num"]) > 0:
                        self.output(
                            f"Version {row['version']} is still assigned to {row['num']} devices, "
                            "cannot be deleted, bailing out.",
                            verbose_level=1,
                        )
                        raise ProcessorError(
                            f"WorkSpaceOnePruner: Version {row['version']} is still assigned to {row['num']} "
                            "devices, cannot be deleted, bailing out."
                        )
                    else:
                        self.output(
                            f"Version {row['version']} is assigned to {row['num']} devices, and " "will be pruned.",
                            verbose_level=2,
                        )
                    try:
                        r = requests.delete(
                            f"{api_base_url}/api/mam/apps/internal/{row['App_ID']}",
                            headers=headers,
                        )
                    except requests.exceptions.RequestException as err:
                        raise ProcessorError(
                            f"WorkSpaceOnePruner: delete of pre-existing app failed, error: {err}, aborting."
                        )
                    if not r.status_code == 202 and not r.status_code == 204:
                        self.output(f"App delete status code: {r.status_code}", verbose_level=4)
                        self.output(f"App delete response: {r.text}", verbose_level=4)
                        result = r.json()
                        self.output(f"App delete result: {result}", verbose_level=3)
                        raise ProcessorError("WorkSpaceOnePruner: delete of old app version failed, aborting.")
                    else:
                        self.output(
                            f"Successfully deleted old version {row['version']}",
                            verbose_level=2,
                        )
                        row["status"] = "PRUNED"
                        pruned_versions += f"[{row['version']}] "
                        num_pruned += 1
            if num_pruned > 0:
                self.output(f"Successfully deleted {num_pruned} old versions", verbose_level=1)
                self.env["ws1_pruned"] = True
                self.env["ws1_pruner_summary_result"] = {
                    "summary_text": "Old software versions pruned",
                    "report_fields": ["name", "pruned_versions", "pruned_versions_num"],
                    "data": {
                        "name": app_name,
                        "pruned_versions": pruned_versions,
                        "pruned_versions_num": str(num_pruned),
                    },
                }

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

        self.output(f"Beginning the WorkSpace ONE pruning process for {app_name}.")

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


if __name__ == "__main__":
    PROCESSOR = WorkSpaceOnePruner()
    PROCESSOR.execute_shell()
