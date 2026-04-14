#!/usr/local/autopkg/python
#
# WorkSpaceOneImporterBase.py - base class for WS1 Autopkg processors
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
"""Base Autopkg Processor providing WS1 UEM REST API authentication (Basic & OAuth 2.0)."""

import base64
import os
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
from autopkglib import Processor, ProcessorError


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


# validate if a URL was supplied (in input variable) - thanks https://stackoverflow.com/a/52455972
def is_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


class WorkSpaceOneImporterBase(Processor):
    """Base processor that handles WS1 UEM authentication.

    Subclasses should call:
        self.init_tls()
        headers, headers_v2 = self.ws1_auth_prep()
    at the beginning of their main() to obtain authenticated HTTP headers.
    """

    description = __doc__

    input_variables = {
        "ws1_api_url": {
            "required": True,
            "description": "Base url of WorkSpace ONE UEM REST API server " "(eg. https://myorg.awmdm.com)",
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
    }

    output_variables = {}

    def init_tls(self):
        """Initialise TLS certificate trust using REQUESTS_CA_BUNDLE env-var or macsesh."""
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
        fetch new token from Access token server with API, in that sequence.
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
                raise ProcessorError(f"WorkSpaceOneImporterBase: Oauth token server response code: {err}")
            except requests.exceptions.RequestException as e:
                raise ProcessorError(f"WorkSpaceOneImporterBase: Something went wrong when getting Oauth token: {e}")
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
