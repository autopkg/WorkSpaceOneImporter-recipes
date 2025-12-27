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
"""Autopkg processor to upload files from a Munki repo to VMWare Workspace ONE UEM using REST API"""

import base64
import hashlib
import json
import os
import plistlib
import re
import subprocess
from datetime import datetime, timedelta
from urllib.parse import urlparse

# if you need to use custom CA certificates, e.g. if your runner is behind a proxy or gateway that does packet
# inspection, you can use MasSesh or provide the extra certificates another way, like having all the CA certificates
# available in a file and set the REQUESTS_CA_BUNDLE environment variable to point to the path.
# The environment variable is used instead of macsesh if set.
if "REQUESTS_CA_BUNDLE" in os.environ:
    HAS_REQUESTS_CA_BUNDLE = True
    HAS_MACSESH = False
else:
    HAS_REQUESTS_CA_BUNDLE = False
    try:
        # see if we can import macsesh module
        # because of the deprecation issues cited below, using macsesh currently means you need urllib3 < 2.
        # https://github.com/sheagcraig/MacSesh/issues/7
        # https://github.com/sheagcraig/MacSesh/issues/9
        import macsesh

        HAS_MACSESH = True
    except ImportError:
        HAS_MACSESH = False
    except ModuleNotFoundError:
        HAS_MACSESH = False

import requests  # dependency, needs to be installed
from autopkglib import Processor, ProcessorError, get_pref
from requests_toolbelt import StreamingIterator  # dependency from requests, needs to be installed

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


def get_timestamp():
    """
    RFS3389 Timestamp rounded to nearest second
    """
    timestamp = (datetime.now().astimezone() + timedelta(milliseconds=500)).replace(microsecond=0)
    return timestamp


def get_password_from_keychain(keychain, service, account):
    """
    Fetch the secret (password) from the dedicated macOS keychain, return None if not found
    """
    command = f"/usr/bin/security find-generic-password -w -s '{service}' -a '{account}' '{keychain}'"
    result = subprocess.run(command, shell=True, capture_output=True)
    if result.returncode == 0:
        password = result.stdout.decode().strip()
        return password
    else:
        return None


def set_password_in_keychain(keychain, service, account, password):
    """
    Store the secret (password) in the dedicated macOS keychain, return exitcode 0 for success
    """

    # first check if there pre-existing password, if so, it must be deleted first
    if get_password_from_keychain(keychain, service, account) is not None:
        command = f"/usr/bin/security delete-generic-password -s '{service}' -a '{account}' '{keychain}'"
        result = subprocess.run(command, shell=True, capture_output=True)
        if result.returncode != 0:
            return result.returncode

    command = f"/usr/bin/security add-generic-password -s '{service}' -a '{account}'  -w '{password}' '{keychain}'"
    result = subprocess.run(command, shell=True, capture_output=True)
    return result.returncode


def extract_first_integer_from_string(s):
    # Search for the first occurrence of a sequence of digits
    match = re.search(r"\d+", s)
    if match:
        # Convert the first match to an integer and return it
        return int(match.group())
    return None


# validate if a URL was supplied (in input variable) - thanks https://stackoverflow.com/a/52455972
def is_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def stream_file(filepath, url, headers):
    """expects headers w/ token, auth, and content-type"""
    streamer = StreamingIterator(os.path.getsize(filepath), open(filepath, "rb"))
    r = requests.post(url, data=streamer, headers=headers)
    return r.json()


class WorkSpaceOneImporter(Processor):
    """Uploads apps from Munki repo to WorkSpace ONE"""

    input_variables = {
        "ws1_api_url": {
            "required": True,
            "description": "Base url of WorkSpace ONE UEM REST API server " "(eg. https://myorg.awmdm.com)",
        },
        "ws1_console_url": {
            "required": False,
            "description": "Base url of WorkSpace ONE UEM Console server for easy result lookup "
            "(eg. https://admin-mobile.myorg.com)",
        },
        "ws1_groupid": {
            "required": True,
            "description": "Group ID of WorkSpace ONE Organization Group " "where files should be uploaded.",
        },
        "ws1_api_token": {
            "required": False,
            "description": "WorkSpace ONE REST API Token. Needed for Basic authentication.",
        },
        "ws1_api_username": {
            "required": False,
            "description": "WorkSpace ONE REST API Username. Either api_username and api_password or "
            "b64encoded_api_credentials are required for Basic authentication.",
        },
        "ws1_api_password": {
            "required": False,
            "description": "WorkSpace ONE REST API User Password. Either api_username and api_password or "
            "b64encoded_api_credentials are required for Basic authentication.",
        },
        "ws1_b64encoded_api_credentials": {
            "required": False,
            "description": '"Basic " + Base64 encoded username:password. Either api_username and api_password or '
            "b64encoded_api_credentials are required for Basic authentication.",
        },
        "ws1_oauth_client_id": {
            "required": False,
            "description": "Client ID for Oauth 2.0 authorization - a more secure and recommended replacement for Basic"
            " authentication.",
        },
        "ws1_oauth_client_secret": {
            "required": False,
            "description": "Client Secret for Oauth 2.0 authorization - a more secure and recommended replacement for "
            "Basic authentication.",
        },
        "ws1_oauth_token_url": {
            "required": False,
            "description": "Access Token renewal service URL for Oauth 2.0 authorization.",
        },
        "ws1_oauth_renew_margin": {
            "required": False,
            "description": "Oauth2 token is to be renewed when the specified percentage of the expiry time is left",
        },
        "ws1_oauth_keychain": {
            "required": False,
            "description": "Name for dedicated macOS keychain to store Oauth2 token and timestamp in.",
        },
        "ws1_oauth_token": {
            "required": False,
            "description": "Existing Oauth2 token for WS1 UEM API access.",
        },
        "ws1_oauth_renew_timestamp": {
            "required": False,
            "description": "timestamp for existing Oauth2 token to be renewed.",
        },
        "ws1_force_import": {
            "required": False,
            "default": "False",
            "description": 'If "true", force import into WS1 if version already exists. Default:false',
        },
        "ws1_update_assignments": {
            "required": False,
            "default": "False",
            "description": 'If "true", update assignments for existing app version in WS1. Default:false',
        },
        "ws1_import_new_only": {
            "required": False,
            "default": "True",
            "description": 'If "false", in case no version was imported into Munki in this session, find latest version'
            " in munki_repo to import into WS1.\n\n"
            "Default: true, meaning only newly imported versions are imported to WS1, this is default to preserve "
            "previous behaviour.",
        },
        "ws1_smart_group_name": {
            "required": False,
            "description": "The name of the first smart group the app should be assigned to, typically testers / "
            "early access.",
        },
        "ws1_push_mode": {
            "required": False,
            "description": "for a simple app assignment, how to deploy the app, can be Auto or On-Demand.",
        },
        "ws1_assignment_rules": {
            "required": False,
            "description": 'Define recipe Input-variable "ws1_app_assignments" instead of this documentation '
            "placeholder. NOT as Processor input var as it is "
            "too complex to be be substituted. MUST override.\n\n"
            "See https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_app_assignments\n",
        },
        "ws1_app_versions_to_keep": {
            "required": False,
            "description": "The number of versions of an app to keep in WS1. Please set this in a recipe (override).\n"
            " See also app_versions_prune.\n\n"
            "NB - please make sure to provide the input variable as type string in the recipe override, using "
            " an integer will result in a hard to trace runtime error 'expected string or bytes-like object'",
        },
        "ws1_app_versions_to_keep_default": {
            "required": False,
            "default": "5",
            "description": "The default number of versions of an app to keep in WS1. Default:5."
            "See also app_versions_prune.\n\n"
            "NB - please make sure to provide the input variable as type string in the recipe override, using "
            " an integer will result in a hard to trace runtime error 'expected string or bytes-like object'",
        },
        "ws1_app_versions_prune": {
            "required": False,
            "default": "dry_run",
            "description": "Whether to prune old versions of an app on WS1. Possible values: True or False or "
            "dry_run. Default:dry_run. See also app_versions_to_keep",
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
        "ws1_app_assignments_changed": {
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

    def oauth_keychain_init(self, password):
        """
        init housekeeping vars for OAuth renewal, and prepare dedicated keychain to persist token and timestamp
        """

        # oauth2 token is to be renewed when a specified percentage of the expiry time is left
        oauth_renew_margin_str = self.env.get("ws1_oauth_renew_margin")
        if oauth_renew_margin_str is not None:
            try:
                oauth_renew_margin = float(oauth_renew_margin_str)
                self.output(
                    f"Found ws1_oauth_renew_margin: {oauth_renew_margin:.1f}",
                    verbose_level=3,
                )
            except ValueError:
                raise ProcessorError(
                    f"Found var ws1_oauth_renew_margin is NOT a float: [{oauth_renew_margin_str}] - aborting!"
                )
        else:
            oauth_renew_margin = 10
            # oauth_renew_margin_str = str(f"oauth_renew_margin:.1f")
            # self.output(f"Type of oauth_renew_margin_str: {type(oauth_renew_margin_str)}", verbose_level=4)
            self.output(
                f"Using default for ws1_oauth_renew_margin: {oauth_renew_margin:.1f}",
                verbose_level=3,
            )

        oauth_keychain = self.env.get("ws1_oauth_keychain")
        if oauth_keychain is not None:
            self.output(f"Found setting ws1_oauth_keychain: {oauth_keychain}", verbose_level=3)
        else:
            oauth_keychain = "Autopkg_WS1_OAuth"
            self.output(
                f"Using default for ws1_oauth_keychain: {oauth_keychain}",
                verbose_level=3,
            )

        # check existing + unlock or create new dedicated keychain to store the Oauth token and timestamp to trigger
        # renewal
        command = f"/usr/bin/security list-keychains -d user | grep -q {oauth_keychain}"
        result = subprocess.run(command, shell=True, capture_output=True)
        if result.returncode == 0:
            command = f"/usr/bin/security unlock-keychain -p {password} {oauth_keychain}"
            result = subprocess.run(command, shell=True, capture_output=True)
            if result.returncode == 0:
                # unlock went fine
                self.output(f"Unlock OK for keychain {oauth_keychain}", verbose_level=4)
                return oauth_keychain, oauth_renew_margin
            else:
                self.output(f"Unlocking keychain {oauth_keychain} failed, deleting it and creating a new one.")
                command = f"/usr/bin/security delete-keychain {oauth_keychain}"
                result = subprocess.run(command, shell=True, capture_output=True)
                if result.returncode != 0:
                    raise ProcessorError(f"Deleting keychain {oauth_keychain} failed - bailing out.")

        # create new empty keychain
        command = f"/usr/bin/security create-keychain -p {password} {oauth_keychain}"
        subprocess.run(command, shell=True, capture_output=True)

        # add keychain to beginning of users keychain search list, so we can find items in it, first delete the
        # newlines and the double quotes
        command = "/usr/bin/security list-keychains -d user"
        result = subprocess.run(command, shell=True, capture_output=True)
        searchlist = result.stdout.decode().replace("\n", "")
        searchlist = searchlist.replace('"', "")
        command = f"/usr/bin/security list-keychains -d user -s {oauth_keychain} {searchlist}"
        subprocess.run(command, shell=True, capture_output=True)

        # Setting (NOT removing) relock timeout on keychain, thanks to
        # https://forums.developer.apple.com/forums/thread/690665
        command = f"/usr/bin/security set-keychain-settings -t 5 {oauth_keychain}"
        subprocess.run(command, shell=True, capture_output=True)
        self.output(
            f"keychain {oauth_keychain} settings adjusted to timeout of 5 seconds.",
            verbose_level=3,
        )
        return oauth_keychain, oauth_renew_margin

    def get_oauth_token(self, oauth_client_id, oauth_client_secret, oauth_token_url):
        """
        get OAuth2 token from either environment, dedicated keychain, or
        fetch new token from Access token server with API
        """
        keychain_service = "Autopkg_WS1_OAUTH"
        oauth_keychain, oauth_renew_margin = self.oauth_keychain_init(oauth_client_secret)

        oauth_token = self.env.get("ws1_oauth_token")
        if oauth_token is not None:
            self.output(
                f"Retrieved existing token from environment: {oauth_token}",
                verbose_level=4,
            )
        else:
            oauth_token = get_password_from_keychain(oauth_keychain, keychain_service, "oauth_token")
            if oauth_token is not None:
                self.output(
                    f"Retrieved existing token from keychain: {oauth_token}",
                    verbose_level=4,
                )
        oauth_token_renew_timestamp_str = self.env.get("ws1_oauth_renew_timestamp")
        if oauth_token_renew_timestamp_str is not None:
            self.output(
                f"Retrieved existing token renew timestamp from environment: {oauth_token_renew_timestamp_str}",
                verbose_level=4,
            )
        else:
            oauth_token_renew_timestamp_str = get_password_from_keychain(
                oauth_keychain, keychain_service, "oauth_token_renew_timestamp"
            )
        if oauth_token_renew_timestamp_str is not None:
            try:
                oauth_token_renew_timestamp = datetime.fromisoformat(oauth_token_renew_timestamp_str)
            except ValueError:
                raise ProcessorError("Could not read timestamp - bailing out!")
            self.output(
                f"Retrieved timestamp to renew existing token: {oauth_token_renew_timestamp.isoformat()}",
                verbose_level=4,
            )
        else:
            oauth_token_renew_timestamp = None

        timestamp = get_timestamp()
        if oauth_token is None or oauth_token_renew_timestamp is None or timestamp >= oauth_token_renew_timestamp:
            # need to get e new token
            self.output("Renewing OAuth access token", verbose_level=3)
            request_body = {
                "grant_type": "client_credentials",
                "client_id": oauth_client_id,
                "client_secret": oauth_client_secret,
            }
            self.output(f"OAuth token request body: {request_body}", verbose_level=4)

            try:
                r = requests.post(oauth_token_url, data=request_body)
                r.raise_for_status()
            except requests.exceptions.HTTPError as err:
                raise ProcessorError(f"WorkSpaceOneImporter: Oauth token server response code: {err}")
            except requests.exceptions.RequestException as e:
                raise ProcessorError(f"WorkSpaceOneImporter: Something went wrong when getting Oauth token: {e}")
            oauth_token_issued_timestamp = get_timestamp()
            self.output(
                f"OAuth token issued at: {oauth_token_issued_timestamp.isoformat()}",
                verbose_level=2,
            )
            result = r.json()
            self.output(f"OAuth token request result: {result}", verbose_level=4)
            oauth_token = result["access_token"]
            renew_threshold = round(result["expires_in"] * (100 - oauth_renew_margin) / 100)
            self.output(
                f"OAuth token threshold for renewal set to {renew_threshold} seconds",
                verbose_level=3,
            )
            oauth_token_renew_timestamp = oauth_token_issued_timestamp + timedelta(seconds=renew_threshold)
            self.output(
                f"OAuth token should be renewed after: {oauth_token_renew_timestamp.isoformat()}",
                verbose_level=2,
            )
            self.env["ws1_oauth_token"] = oauth_token
            result = set_password_in_keychain(oauth_keychain, keychain_service, "oauth_token", oauth_token)
            if result != 0:
                self.output(
                    "OAuth token could not be saved in dedicated keychain",
                    verbose_level=2,
                )
            self.env["ws1_oauth_renew_timestamp"] = oauth_token_renew_timestamp.isoformat()
            result = set_password_in_keychain(
                oauth_keychain,
                keychain_service,
                "oauth_token_renew_timestamp",
                oauth_token_renew_timestamp.isoformat(),
            )
            if result != 0:
                self.output(
                    "OAuth token renewal timestamp could not be saved in dedicated keychain",
                    verbose_level=2,
                )
        self.output(
            f"Current timestamp: {timestamp.isoformat()} - "
            f"re-using current OAuth token until: {oauth_token_renew_timestamp.isoformat()}",
            verbose_level=2,
        )
        return oauth_token

    def get_oauth_headers(self, oauth_client_id, oauth_client_secret, oauth_token_url):
        oauth_token = self.get_oauth_token(oauth_client_id, oauth_client_secret, oauth_token_url)
        headers = {
            "Authorization": f"Bearer {oauth_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        return headers

    def ws1_auth_prep(self):
        ws1_api_token = self.env.get("ws1_api_token")
        ws1_api_username = self.env.get("ws1_api_username")
        ws1_api_password = self.env.get("ws1_api_password")
        ws1_api_basicauth_b64 = self.env.get("ws1_b64encoded_api_credentials")
        oauth_client_id = self.env.get("ws1_oauth_client_id")
        oauth_client_secret = self.env.get("ws1_oauth_client_secret")
        oauth_token_url = self.env.get("ws1_oauth_token_url")

        # if placeholder value is set, ignore and set to None
        if ws1_api_basicauth_b64 == "B64ENCODED_API_CREDENTIALS_HERE":
            self.output(
                "Ignoring standard placeholder value supplied for b64encoded_api_credentials, setting default "
                "value of None",
                verbose_level=2,
            )
            ws1_api_basicauth_b64 = None

        if is_url(oauth_token_url) and oauth_client_id and oauth_client_secret:
            self.output("Oauth client credentials were supplied, proceeding to use these.")
            headers = self.get_oauth_headers(oauth_client_id, oauth_client_secret, oauth_token_url)
        else:
            # create baseline headers
            if ws1_api_basicauth_b64:  # if specified, take precedence over USERNAME and PASSWORD
                basicauth = ws1_api_basicauth_b64
                self.output(
                    "b64encoded_api_credentials found and used for Basic authorization header instead of "
                    "api_username and api_password",
                    verbose_level=1,
                )
            else:  # if NOT specified, use USERNAME and PASSWORD
                hashed_auth = base64.b64encode(f"{ws1_api_username}:{ws1_api_password}".encode("UTF-8"))
                basicauth = f"Basic {hashed_auth}".decode("utf-8")
            self.output(f"Authorization header: {basicauth}", verbose_level=3)
            headers = {
                "aw-tenant-code": ws1_api_token,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "authorization": basicauth,
            }
        headers_v2 = dict(headers)
        headers_v2["Accept"] = f"{headers['Accept']};version=2"
        self.output(f"API v.2 call headers: {headers_v2}", verbose_level=4)

        return headers, headers_v2

    def get_smartgroup_id(self, base_url, smartgroup, headers):
        """Get Smart Group ID and UUID to assign the package to"""

        # we need to replace any spaces with '%20' for the API call
        condensed_sg = smartgroup.replace(" ", "%20")
        r = requests.get(
            f"{base_url}/api/mdm/smartgroups/search?name={condensed_sg}",
            headers=headers,
        )
        if not r.status_code == 200:
            raise ProcessorError(
                f"WorkSpaceOneImporter: No SmartGroup ID found for SmartGroup {smartgroup} - bailing out."
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
            raise ProcessorError("failed to parse results from Smart Group search API call")
        return sg_id, sg_uuid

    def ws1_import(self, pkg_path, pkg_info_path, icon_path):
        """high-level method for Workspace ONE API interactions like uploading an app, app assignment(s) and pruning
        old app versions"""
        self.output("Beginning the WorkSpace ONE import process for %s." % self.env["NAME"])
        api_base_url = self.env.get("ws1_api_url")
        console_url = self.env.get("ws1_console_url")
        org_group_id = self.env.get("ws1_groupid")
        assignment_group = self.env.get("ws1_smart_group_name")
        assignment_pushmode = self.env.get("ws1_push_mode")
        force_import = self.env.get("ws1_force_import").lower() in ("true", "1", "t")
        update_assignments = self.env.get("ws1_update_assignments").lower() in (
            "true",
            "1",
            "t",
        )

        # init result
        self.env["ws1_imported_new"] = False

        if not is_url(console_url):
            self.output(
                f"WS1 Console URL input value [{console_url}] does not look like a valid URL, setting example value",
                verbose_level=2,
            )
            console_url = "https://my-mobile-admin-console.my-org.org"

        # fetch the app assignments Input from the recipe
        app_assignments = self.env.get("ws1_app_assignments")
        self.output(f"App assignments Input from recipe: {app_assignments}", verbose_level=3)

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

        if HAS_REQUESTS_CA_BUNDLE:
            self.output(
                f"Found environment variable REQUESTS_CA_BUNDLE is set to: [{os.getenv('REQUESTS_CA_BUNDLE')}] "
                "so using that for CA-certificates instead of macsesh module.",
                verbose_level=2,
            )
        else:
            if HAS_MACSESH:
                # Init the MacSesh so we can use the trusted certs in macOS Keychains to verify SSL.
                # Needed especially in networks with TLS packet inspection and custom certificates.
                macsesh.inject_into_requests()
                self.output("MacSesh is installed, imported, and injected.", verbose_level=2)
            else:
                self.output(
                    "MacSesh was NOT found installed. If you need to use custom CA certificates for TLS packet "
                    "inspection, you must either install it or provide the certs another way, like having the CA "
                    "certificates available in a file and set the REQUESTS_CA_BUNDLE environment variable to point "
                    "to the path.",
                    verbose_level=2,
                )

        # take care of headers for WS1 REST API authentication
        headers, headers_v2 = self.ws1_auth_prep()

        # get OG ID from GROUPID
        result = ""
        try:
            r = requests.get(
                f"{api_base_url}/api/system/groups/search?groupid={org_group_id}",
                headers=headers_v2,
            )
            result = r.json()
            r.raise_for_status()
        except AttributeError:
            raise ProcessorError(
                "WorkSpaceOneImporter:"
                f"Unable to retrieve an ID for the Organizational GroupID specified: {org_group_id}"
            )
        except requests.exceptions.HTTPError as err:
            raise ProcessorError(
                f"WorkSpaceOneImporter: Server responded with error when making the OG ID API call: {err}"
            )
        except requests.exceptions.RequestException as e:
            ProcessorError(f"WorkSpaceOneImporter: Error making the OG ID API call: {e}")
        ogid = ""
        if org_group_id in result["OrganizationGroups"][0]["GroupId"]:
            ogid = result["OrganizationGroups"][0]["Id"]
        self.output(f"Organisation group ID: {ogid}", verbose_level=2)

        # Check for app versions already present on WS1 server
        try:
            condensed_app_name = app_name.replace(" ", "%20")
            r = requests.get(
                f"{api_base_url}/api/mam/apps/search?locationgroupid={ogid}&applicationname=" f"{condensed_app_name}",
                headers=headers,
            )
        except Exception:
            raise ProcessorError("Something went wrong handling pre-existing app version on server")
        if r.status_code == 200:
            search_results = r.json()

            # handle older versions of app already present on WS1 UEM
            self.ws1_app_versions_prune(api_base_url, headers, app_name, search_results)

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
                    # if not self.env.get("ws1_force_import").lower() == "true":
                    if not force_import:
                        if update_assignments and not assignment_group == "none":
                            self.output("updating simple app assignment", verbose_level=2)
                            app_assignment = self.ws1_app_assignment_conf(
                                api_base_url,
                                assignment_pushmode,
                                assignment_group,
                                headers,
                            )
                            self.ws1_app_assign(
                                api_base_url,
                                assignment_group,
                                app_assignment,
                                headers,
                                ws1_app_id,
                            )
                            self.env["ws1_importer_summary_result"] = {
                                "summary_text": "The following new app assignment was made in WS1:",
                                "report_fields": [
                                    "name",
                                    "version",
                                    "assignment_group",
                                ],
                                "data": {
                                    "name": self.env["NAME"],
                                    "version": app_version,
                                    "assignment_group": assignment_group,
                                },
                            }
                        elif update_assignments and not app_assignments == "none":
                            self.output("updating advanced app assignment", verbose_level=2)
                            self.ws1_app_assignments(api_base_url, app_assignments, headers, ws1_app_id)
                        elif update_assignments:
                            raise ProcessorError(
                                "update_assignments is True, but ws1_smart_group_name is not"
                                " specified and neither is ws1_app_assignments"
                            )
                        else:
                            self.output(
                                f"App [{app_name}] version [{app_version}] is already present on server, "
                                "and neither ws1_force_import nor ws1_update_assignments is set."
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
        elif r.status_code == 204:
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

        """
        Create the app assignment details for API V1 assignments POST call
        MAM (Mobile Application Management) REST API V1  - POST /apps/internal/{applicationId}/assignments
        https://as135.awmdm.com/api/help/#!/InternalAppsV1/InternalAppsV1_AddAssignmentsWithFlexibleDeploymentParametersAsync
        """
        # get WS1 Smart Group ID from its name
        if not assignment_group == "none":
            app_assignment = self.ws1_app_assignment_conf(api_base_url, assignment_pushmode, assignment_group, headers)
            self.ws1_app_assign(api_base_url, assignment_group, app_assignment, headers, ws1_app_id)
        else:
            self.ws1_app_assignments(api_base_url, app_assignments, headers, ws1_app_id)

        return "Application was successfully uploaded to WorkSpaceOne."

    def ws1_app_assignments(self, api_base_url, app_assignments, headers, ws1_app_id):
        """
        prep app assignment rules and make API V2 assignments PUT call
        MAM (Mobile Application Management) REST API V2  - PUT /apps/{applicationUuid}/assignment-rules
        https://as135.awmdm.com/API/help/#!/AppsV2/AppsV2_UpdateAssignmentRuleAsync

        NB - an App Assignment Rule with an effective_date in the future causes previous versions of the app to NOT be
        deployed to newly enrolled devices, and NOT be offered in the Hub and user portal. Neither will the app version
        with effective_date in the future be deployed or be offered in the Hub or user portal before effective_date.
        For that reason, we need to postpone setting such assignment rules until effective_date, and skip those set
        for a future date until next autopkg session.
        """
        # call Get for internal app to get app UUID
        try:
            r = requests.get(f"{api_base_url}/api/mam/apps/internal/{ws1_app_id}", headers=headers)
            result = r.json()
        except requests.exceptions.RequestException as err:
            raise ProcessorError(f"API call to get internal app details failed, error: {err}")
        if not r.status_code == 200:
            raise ProcessorError(
                f"WorkSpaceOneImporter: Unable to get internal app details - message: {result['message']}."
            )
        ws1_app_uuid = result["uuid"]
        app_name = result["ApplicationName"]
        app_version = result["ActualFileVersion"]
        self.output(f"ws1_app_uuid: [{ws1_app_uuid}]", verbose_level=2)
        if not app_assignments == "none":
            # prepare API V2 headers
            headers_v2 = dict(headers)
            headers_v2["Accept"] = f"{headers['Accept']};version=2"
            self.output(f"API v.2 call headers: {headers_v2}", verbose_level=4)

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
                    f"WorkSpaceOneImporter: Unable to get existing app assignment rules from WS1 "
                    f"- message: {result['message']}."
                )
            if not result["assignments"] and not self.env.get("ws1_imported_new"):
                self.output(
                    "No existing Assignment Rules found, operator must have removed those - skipping.",
                    verbose_level=1,
                )
                return
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

                # if there's an existing assignment rule, use its effective_date as base deployment date, else
                # use today's date
                ws1_app_ass_day0 = datetime.min
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
            else:
                ws1_app_ass_day0 = datetime.today().date()

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
                    """
                    Commented out the time setting part as it isn't respected in UEM v.22.9.0.8 (2209) as of 2023-02-17
                    # convert date to datetime, and add 12 hours to deploy at noon in WS1 UEM console timezone
                    deploy_datetime = datetime.datetime.combine(deploy_date, datetime.time(12))
                    # specify target date and time as noon in iso 8601 format with local timezone offset
                    app_assignment["distribution"]["effective_date"] = deploy_datetime.astimezone().isoformat()
                    app_assignment["distribution"]["effective_date"] = deploy_datetime.isoformat()
                    """

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
                    f"Skipping remaining assignments from index [{priority_index}] as they are designated for a  "
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
                app_ws1console_loc = (
                    f"{self.env.get('ws1_console_url')}"
                    f"/AirWatch/#/AirWatch/Apps/Details/Internal/{ws1_app_id}/Assignment"
                )
                if not self.env["ws1_imported_new"]:
                    self.env["ws1_importer_summary_result"] = {
                        "summary_text": "The following new app assignment rules are applied in WS1:",
                        "report_fields": [
                            "name",
                            "version",
                            "new_assignment_rules",
                            "console_location",
                        ],
                        "data": {
                            "name": self.env["NAME"],
                            "version": app_version,
                            "new_assignment_rules": new_assignment_rules,
                            "console_location": app_ws1console_loc,
                        },
                    }
                else:
                    ws1_importer_summary_result = self.env.get("ws1_importer_summary_result")
                    ws1_importer_summary_result["report_fields"].append("new_assignment_rules")
                    ws1_importer_summary_result["data"]["new_assignment_rules"] = new_assignment_rules
                    self.env["ws1_importer_summary_result"] = ws1_importer_summary_result

    def ws1_app_assignment_conf(self, api_base_url, assignment_pushmode, assignment_group, headers):
        """assemble app_assignment to pass in API V1 call"""
        sg_id, sg_uuid = self.get_smartgroup_id(api_base_url, assignment_group, headers)
        if assignment_pushmode == "Auto":
            set_macos_desired_state_management = True
        else:
            set_macos_desired_state_management = False
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
        return app_assignment

    def ws1_app_assign(self, base_url, smart_group, app_assignment, headers, ws1_app_id):
        """Call WS1 API V1 assignments for to smart group(s) with the deployment settings
        MAM (Mobile Application Management) REST API V1  - POST /apps/internal/{applicationId}/assignments
        https://as135.awmdm.com/api/help/#!/InternalAppsV1/InternalAppsV1_AddAssignmentsWithFlexibleDeploymentParametersAsync
        """  # noqa: E501
        try:
            payload = json.dumps(app_assignment)
            self.output(f"App assignments data to send: {app_assignment}", verbose_level=2)
        except ValueError:
            raise ProcessorError("failed to parse App assignment as json")

        try:
            # Make the WS1 API call to assign the App
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
                f"App assignments failed: {result['errorCode']} - {result['message']}",
                verbose_level=2,
            )
            raise ProcessorError(f"Unable to assign the app [{self.env['NAME']}] to the group [{smart_group}]")
        self.env["ws1_app_assignments_changed"] = True
        self.output(f"Successfully assigned the app [{self.env['NAME']}] to the group [{smart_group}]")

    def ws1_app_versions_prune(self, api_base_url, headers, app_name, search_results):
        """
        get ws1_app_versions_to_keep_default, defaults to 5
        """
        keep_versions_default_str = self.env.get("ws1_app_versions_to_keep_default", "5")
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
        if keep_versions_str is not None:
            keep_versions = extract_first_integer_from_string(keep_versions_str)
        else:
            keep_versions = 0
        if keep_versions < 1:
            self.output(
                f"ws1_app_versions_to_keep setting {keep_versions:d} is out of range, "
                f"setting default of {keep_versions_default}."
            )
            keep_versions = keep_versions_default
        else:
            self.output(f"ws1_app_versions_to_keep is set to: {keep_versions}", verbose_level=2)

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
                    raise ProcessorError("API call to get existing app assignment rules failed")
                if not r.status_code == 200:
                    raise ProcessorError(
                        f"WorkSpaceOneImporter: Unable to get existing app assignment rules from WS1 "
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
        self.output("Updating prune status", verbose_level=4)
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
                    try:
                        r = requests.delete(
                            f"{api_base_url}/api/mam/apps/internal/{row['App_ID']}",
                            headers=headers,
                        )
                    except requests.exceptions.RequestException as err:
                        raise ProcessorError(
                            f"ws1_app_versions_prune - delete of pre-existing app failed, error: {err}, aborting."
                        )
                    if not r.status_code == 202 and not r.status_code == 204:
                        self.output(f"App delete status code: {r.status_code}", verbose_level=4)
                        self.output(f"App delete response: {r.text}", verbose_level=4)
                        result = r.json()
                        self.output(f"App delete result: {result}", verbose_level=3)
                        raise ProcessorError("ws1_app_versions_prune - delete of old app version failed, aborting.")
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
                self.env["ws1_importer_summary_result"] = {
                    "summary_text": "Old software versions pruned",
                    "report_fields": ["name", "pruned_versions", "pruned_versions_num"],
                    "data": {
                        "name": app_name,
                        "pruned_versions": pruned_versions,
                        "pruned_versions_num": str(num_pruned),
                    },
                }

    def main(self):
        """Rebuild Munki catalogs in repo_path"""

        # clear any pre-existing summary result
        if "ws1_importer_summary_result" in self.env:
            del self.env["ws1_importer_summary_result"]
        self.env["ws1_imported_new"] = False
        self.env["ws1_app_assignments_changed"] = False

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
