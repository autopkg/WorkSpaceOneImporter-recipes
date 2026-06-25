#!/usr/local/autopkg/python
#
# WorkSpaceOneImporter.py - a custom Autopkg processor
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
"""Autopkg processor to upload files from a Munki repo to Omnissa Workspace ONE UEM using REST API"""

import hashlib
import os
import plistlib
import re
import subprocess
import sys

import requests  # dependency, needs to be installed
from autopkglib import ProcessorError, get_pref
from requests_toolbelt import StreamingIterator  # dependency from requests

# Ensure ws1_lib package (sibling directory) is importable
# Helpful comments copied from processors in https://github.com/autopkg/grahampugh-recipes
# To use a base module in AutoPkg we need to add this path to the sys.path.
# This violates flake8 E402 (PEP8 imports) but is unavoidable, so the following
# imports require noqa comments for E402
sys.path.insert(0, os.path.dirname(__file__))

from ws1_lib.WorkSpaceOneImporterBase import (  # noqa: E402
    WorkSpaceOneImporterBase,
    is_url,
)

__all__ = ["WorkSpaceOneImporter"]


def getsha256hash(filename):
    """
    Calculates the SHA-256 hash value of a file as a hex string. Nicked from Munki hash library munkihash.py

    Args:
        filename: The file name to calculate the hash value of.
    Returns:
        The hash of the given file as hex string.
    """
    hasher = hashlib.sha256()
    if not os.path.isfile(filename):
        return "NOT A FILE"
    try:
        fileref = open(filename, "rb")
        while True:
            chunk = fileref.read(2**16)
            if not chunk:
                break
            hasher.update(chunk)
        fileref.close()
        return hasher.hexdigest()
    except OSError:
        return "HASH_ERROR"


def stream_file(filepath, url, headers):
    """expects headers w/ token, auth, and content-type"""
    streamer = StreamingIterator(os.path.getsize(filepath), open(filepath, "rb"))
    r = requests.post(url, data=streamer, headers=headers)
    return r.json()


class WorkSpaceOneImporter(WorkSpaceOneImporterBase):
    """Uploads apps from Munki repo to WorkSpace ONE"""

    input_variables = {
        **WorkSpaceOneImporterBase.input_variables,
        "ws1_console_url": {
            "required": False,
            "description": "Base url of WorkSpace ONE UEM Console server for easy result lookup "
            "(eg. https://admin-mobile.myorg.com)",
        },
        "ws1_force_import": {
            "required": False,
            "default": "False",
            "description": 'If "true", force import into WS1 if version already exists. Default:false',
        },
        "ws1_import_new_only": {
            "required": False,
            "default": "True",
            "description": 'If "false", in case no version was imported into Munki in this session, find latest version'
            " in munki_repo to import into WS1.\n\n"
            "Default: true, meaning only newly imported versions are imported to WS1, this is default to preserve "
            "previous behaviour.",
        },
    }

    output_variables = {
        "makecatalogs_resultcode": {
            "description": "Result code from the makecatalogs operation.",
        },
        "makecatalogs_stderr": {
            "description": "Error output (if any) from makecatalogs.",
        },
        "ws1_resultcode": {
            "description": "Result code from the WorkSpace ONE Import.",
        },
        "ws1_stderr": {
            "description": "Error output (if any) from the WorkSpace ONE Import.",
        },
        "ws1_app_id": {
            "description": "Application ID of the app version in WS1 UEM",
        },
        "ws1_imported_new": {
            "description": "True if a new app version was imported in this session to WS1 UEM",
        },
        "ws1_importer_summary_result": {"description": "Description of interesting results."},
    }
    description = __doc__

    # GIT FUNCTIONS
    def git_run(self, repo, cmd):
        """shell out a command to git in the Munki repo"""
        cmd = ["git"] + cmd
        self.output("Running " + " ".join(cmd), verbose_level=2)
        try:
            # result = subprocess.run(" ".join(cmd), shell=True, cwd=MUNKI_REPO, capture_output=hide_cmd_output)
            result = subprocess.run(" ".join(cmd), shell=True, cwd=repo, capture_output=True)
            self.output(result, verbose_level=2)
        except subprocess.CalledProcessError as e:
            # print(e.stderr)
            self.output(e.stderr)
            raise e

    def git_lfs_pull(self, repo, filename):
        """pull specific LFS filename from git origin"""
        gitcmd = ["lfs", "pull", f'--include="{filename}"']
        self.git_run(repo, gitcmd)

    def ws1_import(self, pkg_path, pkg_info_path, icon_path):
        """high-level method for Workspace ONE API interactions: uploading an app and creating the App object"""
        self.output("Beginning the WorkSpace ONE import process for %s." % self.env["NAME"])
        api_base_url = self.env.get("ws1_api_url")
        console_url = self.env.get("ws1_console_url")
        org_group_id = self.env.get("ws1_groupid")
        force_import = self.env.get("ws1_force_import").lower() in ("true", "1", "t")

        # init result
        self.env["ws1_imported_new"] = False

        if not is_url(console_url):
            self.output(
                f"WS1 Console URL input value [{console_url}] does not look like a valid URL, setting example value",
                verbose_level=2,
            )
            console_url = "https://my-mobile-admin-console.my-org.org"

        # Get some global variables for later use from pkginfo, don't rely on
        # munki_importer_summary_result being filled in current session
        try:
            with open(pkg_info_path, "rb") as fp:
                pkg_info = plistlib.load(fp)
        except IOError:
            raise ProcessorError(f"Could not read pkg_info file [{pkg_info_path}]")
        except Exception:
            raise ProcessorError(f"Failed to parse pkg_info file [{pkg_info_path}] somehow.")
        if "version" not in pkg_info:
            raise ProcessorError(f"version not found in pkginfo [{pkg_info_path}]")
        app_version = pkg_info["version"]
        if "name" not in pkg_info:
            raise ProcessorError(f"name not found in pkginfo [{pkg_info_path}]")
        app_name = pkg_info["name"]

        # handle any REQUESTS_CA_BUNDLE supplied or macsesh installed
        self.init_tls()

        # take care of headers for WS1 REST API authentication
        headers, headers_v2 = self.ws1_auth_prep()

        # get OG ID from GROUPID
        ogid = self.resolve_ogid(api_base_url, org_group_id, headers_v2)

        # Check for app versions already present on WS1 server
        search_results = self.search_apps(api_base_url, ogid, app_name, headers)
        if search_results is not None:

            # handle any updates that might be needed for the latest app version already present on WS1 UEM
            for app in search_results["Application"]:
                if (
                    app["Platform"] == 10
                    and app["ActualFileVersion"] == str(app_version)
                    and app["ApplicationName"] in app_name
                ):
                    ws1_app_id = app["Id"]["Value"]
                    self.env["ws1_app_id"] = ws1_app_id
                    self.output("Pre-existing App ID: %s" % ws1_app_id, verbose_level=2)
                    self.output(f"Pre-existing App version: {app_version}", verbose_level=2)
                    self.output(
                        f"Pre-existing App platform: {app['Platform']}",
                        verbose_level=3,
                    )
                    if not force_import:
                        self.output(
                            f"App [{app_name}] version [{app_version}] is already present on server, "
                            "and ws1_force_import is not set."
                        )
                        return "Nothing new to upload - completed."
                    else:
                        self.output(
                            f"App [{app_name}] version [{app_version}] already present on server, and "
                            f"ws1_force_import==True, attempting to delete on server first."
                        )
                        try:
                            r = requests.delete(
                                f"{api_base_url}/api/mam/apps/internal/{ws1_app_id}",
                                headers=headers,
                            )
                        except requests.exceptions.RequestException as err:
                            raise ProcessorError(
                                f"ws1_force_import - delete of pre-existing app failed, error: {err}, aborting."
                            )
                        if not r.status_code == 202 and not r.status_code == 204:
                            result = r.json()
                            self.output(f"App delete result: {result}", verbose_level=3)
                            raise ProcessorError("ws1_force_import - delete of pre-existing app failed, aborting.")
                        try:
                            r = requests.get(
                                f"{api_base_url}/api/mam/apps/internal/{ws1_app_id}",
                                headers=headers,
                            )
                            if not r.status_code == 401:
                                result = r.json()
                                self.output(
                                    f"App not deleted yet, status: {result['Status']} - retrying",
                                    verbose_level=2,
                                )
                                requests.delete(
                                    f"{api_base_url}/api/mam/apps/internal/{ws1_app_id}",
                                    headers=headers,
                                )
                        except requests.exceptions.RequestException as err:
                            raise ProcessorError(
                                f"ws1_force_import - delete of pre-existing app failed, error: {err} aborting."
                            )
                        self.output(f"Pre-existing App [ID: {ws1_app_id}] now successfully deleted")
                        break
        else:
            # app not found on WS1 server, so we're fine to proceed with upload
            self.output(f"App [{app_name}] version [{app_version}] is not yet present on server, will attempt upload")

        # proceed with upload
        if pkg_path is not None:
            self.output("Uploading pkg...")
            # upload pkg, dmg, mpkg file (application/json)
            headers["Content-Type"] = "application/json"
            posturl = (
                f"{api_base_url}/api/mam/blobs/uploadblob?filename={os.path.basename(pkg_path)}"
                f"&organizationGroupId={str(ogid)}"
            )
            try:
                res = stream_file(pkg_path, posturl, headers)
                pkg_id = res["Value"]
                self.output(f"Pkg ID: {pkg_id}")
            except KeyError:
                raise ProcessorError("WorkSpaceOneImporter: Something went wrong while uploading the pkg.")
        else:
            raise ProcessorError("WorkSpaceOneImporter: Did not receive a pkg_path from munkiimporter.")

        if pkg_info_path is not None:
            self.output("Uploading pkg_info...")
            # upload pkginfo plist (application/json)
            headers["Content-Type"] = "application/json"
            posturl = (
                f"{api_base_url}/api/mam/blobs/uploadblob?filename={os.path.basename(pkg_info_path)}"
                f"&organizationGroupId={str(ogid)}"
            )
            try:
                res = stream_file(pkg_info_path, posturl, headers)
                pkginfo_id = res["Value"]
                self.output(f"PkgInfo ID: {pkginfo_id}")
            except KeyError:
                raise ProcessorError("WorkSpaceOneImporter: Something went wrong while uploading the pkginfo.")
        else:
            raise ProcessorError("WorkSpaceOneImporter: Did not receive a pkg_info_path from munkiimporter.")

        icon_id = ""
        if icon_path is not None:
            self.output("Uploading icon...")
            # upload icon file (application/json)
            headers["Content-Type"] = "application/json"
            posturl = (
                f"{api_base_url}/api/mam/blobs/uploadblob?filename={os.path.basename(icon_path)}"
                f"&organizationGroupId={str(ogid)}"
            )
            try:
                res = stream_file(icon_path, posturl, headers)
                icon_id = res["Value"]
                self.output(f"Icon ID: {icon_id}")
            except KeyError:
                self.output("Something went wrong while uploading the icon.")
                self.output("Continuing app object creation...")
                pass

        # Create a dict with the app details to be passed to WS1 to create the App object
        # include applicationIconId only if we have one
        if icon_id:

            app_details = {
                "pkgInfoBlobId": str(pkginfo_id),
                "applicationBlobId": str(pkg_id),
                "applicationIconId": str(icon_id),
                "version": str(app_version),
            }
        else:
            app_details = {
                "pkgInfoBlobId": str(pkginfo_id),
                "applicationBlobId": str(pkg_id),
                "version": str(app_version),
            }

        # Make the API call to create the App object
        self.output("Creating App Object in WorkSpaceOne...")
        self.output(f"app_details: {app_details}", verbose_level=3)
        r = requests.post(
            f"{api_base_url}/api/mam/groups/{ogid}/macos/apps",
            headers=headers,
            json=app_details,
        )
        if not r.status_code == 201:
            result = r.json()
            self.output(f"App create result: {result}", verbose_level=3)
            raise ProcessorError("WorkSpaceOneImporter: Unable to create the App Object.")

        # Now get the new App ID from the server
        # When status_code is 201, the response header "Location" URL holds the ApplicationId after last slash
        self.output(f"App create response headers: {r.headers}", verbose_level=4)
        ws1_app_id = r.headers["Location"].rsplit("/", 1)[-1]
        self.output(f"App create ApplicationId: {ws1_app_id}", verbose_level=3)
        self.env["ws1_app_id"] = ws1_app_id
        self.env["ws1_imported_new"] = True
        app_ws1console_loc = f"{console_url}/AirWatch/#/AirWatch/Apps/Details/Internal/{ws1_app_id}"
        self.output(f"App created, see in WS1 console at: {app_ws1console_loc}")
        self.env["ws1_importer_summary_result"] = {
            "summary_text": "The following new app was imported in WS1:",
            "report_fields": ["name", "version", "console_location"],
            "data": {
                "name": app_name,
                "version": app_version,
                "console_location": app_ws1console_loc,
            },
        }

        return "Application was successfully uploaded to WorkSpaceOne."

    def main(self):
        """Rebuild Munki catalogs in repo_path"""

        # clear any pre-existing summary result
        if "ws1_importer_summary_result" in self.env:
            del self.env["ws1_importer_summary_result"]
        self.env["ws1_imported_new"] = False

        cache_dir = get_pref("CACHE_DIR") or os.path.expanduser("~/Library/AutoPkg/Cache")
        current_run_results_plist = os.path.join(cache_dir, "autopkg_results.plist")
        try:
            with open(current_run_results_plist, "rb") as f:
                run_results = plistlib.load(f)
        except IOError:
            run_results = []

        munkiimported_new = False

        # get ws1_import_new_only, defaults to True
        import_new_only = self.env.get("ws1_import_new_only", "True").lower() in (
            "true",
            "1",
            "t",
        )

        # key munki_importer_summary_result might not exist, nor data or pkginfo_path, try-catch is simplest
        try:
            pkginfo_path = self.env["munki_importer_summary_result"]["data"]["pkginfo_path"]
        except (KeyError, TypeError):
            pkginfo_path = None

        if pkginfo_path:
            munkiimported_new = True

        if not munkiimported_new and import_new_only:
            self.output(run_results)
            self.output("No updates so nothing to import to WorkSpaceOne")
            self.env["ws1_resultcode"] = 0
            self.env["ws1_stderr"] = ""
            return
        elif not munkiimported_new and not import_new_only:
            self.output(
                "Nothing new imported into Munki repo, but ws1_import_new_only==False so will try to find "
                "existing matching version in Munki repo."
            )
            # get cached installer path that was set by MunkiImporter processor in previous recipe step because the one
            # in the Munki repo might be a Git LFS shortcut
            ci = self.env["pkg_path"]
            self.output(
                f"comparing hash of cached installer [{ci}] to find pkginfo file",
                verbose_level=2,
            )
            # hash code copied from Munki's pkginfolib.py and function from hash lib munkihash.py
            # get size of installer item
            citemsize = 0
            citemhash = "N/A"
            if os.path.isfile(ci):
                citemsize = int(os.path.getsize(ci))
                try:
                    citemhash = getsha256hash(ci)
                except OSError as err:
                    raise ProcessorError(err)

            # use pkg_repo_path env var set by MunkiImporter to find an existing installer in repo
            pkg = self.env["pkg_repo_path"]
            self.output(f"matching installer already exists in repo [{pkg}]", verbose_level=2)

            munki_repo = self.env["MUNKI_REPO"]
            self.output(f"MUNKI_REPO: {munki_repo}", verbose_level=2)
            if os.path.isfile(pkg):
                itemsize = int(os.path.getsize(pkg))
                installer_item_path = pkg[len(munki_repo) + 1 :]  # get path relative from repo
                if not itemsize == citemsize:
                    self.output(
                        "size of item in local munki repo differs from cached, might be a Git LFS shortcut, "
                        "pulling remote",
                        verbose_level=2,
                    )
                    self.git_lfs_pull(munki_repo, installer_item_path)
                try:
                    itemhash = getsha256hash(pkg)
                    if not itemhash == citemhash:
                        if os.path.splitext(pkg)[1][1:].lower() == "dmg":
                            self.output(
                                "Installer dmg item in Munki repo differs from cached installer, this is expected if "
                                "your recipe has a DmgCreator step; checking dmg checksum.",
                                verbose_level=2,
                            )
                            result = subprocess.run(["hdiutil", "verify", "-quiet", pkg])
                            if not result.returncode == 0:
                                raise ProcessorError(f"Installer dmg verification failed for [{pkg}]")
                        else:
                            raise ProcessorError(
                                "Installer item in Munki repo differs from cached installer, please check."
                            )
                except OSError as err:
                    raise ProcessorError(err)

                # look in same dir from pkgsinfo/ for matching pkginfo file
                installer_item_dir = os.path.dirname(pkg)
                installer_info_dir = re.sub(r"/pkgs", "/pkgsinfo", installer_item_dir)
                # walk the dir to check each pkginfo file for matching hash
                self.output(
                    f"scanning [{installer_info_dir}] to find matching pkginfo file with installer_item_hash "
                    f"value: [{itemhash}]",
                    verbose_level=2,
                )
                found_match = False
                pi = ""
                for path, _subdirs, files in os.walk(installer_info_dir):
                    for name in files:
                        if name == ".DS_Store":
                            continue
                        pi = os.path.join(path, name)
                        self.output(
                            f"checking [{name}] to find matching installer_item_hash",
                            verbose_level=2,
                        )
                        try:
                            with open(pi, "rb") as fp:
                                pkg_info = plistlib.load(fp)
                        except IOError:
                            raise ProcessorError(f"Could not read pkg_info file [{pi}]")
                        except Exception as err:
                            raise ProcessorError(f"Could not parse pkg_info file [{pi}] error: {err}")
                        if "installer_item_hash" in pkg_info and pkg_info["installer_item_hash"] == itemhash:
                            found_match = True
                            iih = pkg_info["installer_item_hash"]
                            self.output(
                                f"installer_item_hash match found: [{iih}]",
                                verbose_level=4,
                            )
                            break
                    if found_match:
                        self.output(
                            f"Found matching installer info file in munki repo [{pi}]",
                            verbose_level=2,
                        )
                        break
                if not found_match:
                    raise ProcessorError(f"Failed to find matching pkginfo in [{installer_info_dir}]")
            else:
                #
                raise ProcessorError(f"Failed to read installer [{pkg}]")
        else:
            # use paths for newly imported items set by MunkiImporter
            pi = self.env["pkginfo_repo_path"]
            pkg = self.env["pkg_repo_path"]

        # Get icon file settings. Read pkginfo plist file to find if specific icon_path key is present, if so
        # use that. If not, check for common icon file. Proceed to WS1 with what we have regardless.
        try:
            with open(pi, "rb") as fp:
                pkg_info = plistlib.load(fp)
        except IOError:
            raise ProcessorError(f"Could not read pkg_info file [{pi}] to check icon_name ")
        except Exception:
            raise ProcessorError(f"Failed to parse pkg_info file [{pi}] somehow.")
        if "icon_name" not in pkg_info:
            # if key isn't present, look for common icon file with same 'first' name as installer item
            icon_path = f"{self.env['MUNKI_REPO']}/icons/{self.env['NAME']}.png"
            self.output(f"Looking for icon file [{icon_path}]", verbose_level=1)
        else:
            # when icon was specified for this installer version
            icon_path = f"{self.env['MUNKI_REPO']}/icons/{pkg_info['icon_name']}"
            self.output(f"Icon file for this installer version was specified as [{icon_path}]")
        # if we can't read or find any icon, proceed with upload regardless
        if not os.path.exists(icon_path):
            self.output(f"Could not read icon file [{icon_path}] - skipping.")
            icon_path = None
        elif icon_path is None:
            self.output("Could not find any icon file - skipping.")
        self.output(self.ws1_import(pkg, pi, icon_path))


if __name__ == "__main__":
    # PROCESSOR = MakeCatalogsProcessor()
    PROCESSOR = WorkSpaceOneImporter()
    PROCESSOR.execute_shell()
