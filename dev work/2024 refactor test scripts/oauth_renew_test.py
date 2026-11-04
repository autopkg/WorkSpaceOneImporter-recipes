#!/usr/local/autopkg/python

"""
Research/testing when and how to renew the oauth token.

Found out the token validity period (expiry_time) is not documented in API from VMWare, but is actually returned along
with the new token.
"""

import os
import subprocess
import time
from datetime import datetime, timedelta

import requests


def get_timestamp():
    timestamp = (datetime.now().astimezone() + timedelta(milliseconds=500)).replace(microsecond=0)
    return timestamp


"""
Fetch the secrets (passwords) from the dedicated macOS keychain used in the launcher tool used for development of
Autopkg processor
"""


def get_password_from_keychain(keychain, service, account):
    command = f"/usr/bin/security find-generic-password -w -s '{service}' -a '{account}' '{keychain}'"
    result = subprocess.run(command, shell=True, capture_output=True)
    if result.returncode == 0:
        password = result.stdout.decode().strip()
        return password
    else:
        return None


def set_password_in_keychain(keychain, service, account, password):
    command = f"/usr/bin/security add-generic-password -s '{service}' -a '{account}'  -w '{password}' '{keychain}'"
    result = subprocess.run(command, shell=True, capture_output=True)
    return result.returncode


def pretty_print_POST(req):
    """
    show what headers were added to POST request, thanks to https://stackoverflow.com/a/23816211

    At this point it is completely built and ready
    to be fired; it is "prepared".

    However pay attention at the formatting used in
    this function because it is programmed to be pretty
    printed and may differ from the actual request.
    """

    print(
        "-----------PREPPED REQUEST START-----------\n"
        f"Method: {req.method}\n"
        + f"url: {req.url}\n"
        + "-----------PREPPED REQUEST HEADERS-----------\n"
        + "".join(f"{k}: {v}\n" for k, v in req.headers.items())
        + "-----------PREPPED REQUEST BODY-----------\n"
        + f"{req.body}\n"
        + "-----------PREPPED REQUEST END-----------\n"
    )


def main():
    """Add variables from environment - inspired by
    https://github.com/autopkg/autopkg/blob/master/Code/autopkg#L2140-L2147"""

    if "AUTOPKG_ws1_oauth_token_url" in os.environ:
        ws1_oauth_token_url = os.environ["AUTOPKG_ws1_oauth_token_url"]
        print(f"Found env var AUTOPKG_ws1_oauth_token_url: {ws1_oauth_token_url}")
    else:
        print("Did not find environment variable AUTOPKG_ws1_oauth_token_url - aborting!")
        exit(code=1)

    if "AUTOPKG_ws1_oauth_client_id" in os.environ:
        ws1_oauth_client_id = os.environ["AUTOPKG_ws1_oauth_client_id"]
        print(f"Found env var AUTOPKG_ws1_oauth_client_id: {ws1_oauth_client_id}")
    else:
        print("Did not find environment variable AUTOPKG_ws1_oauth_client_id - aborting!")
        exit(code=1)

    if "AUTOPKG_ws1_oauth_client_secret" in os.environ:
        ws1_oauth_client_secret = os.environ["AUTOPKG_ws1_oauth_client_secret"]
        print(f"Found env var AUTOPKG_ws1_oauth_client_secret: {ws1_oauth_client_secret}")
    else:
        print("Did not find environment variable AUTOPKG_ws1_oauth_client_secret - aborting!")
        exit(code=1)

    # oauth2 token is to be renewed when a specified percentage of the expiry time is left
    if "AUTOPKG_ws1_oauth_renew_margin" in os.environ:
        try:
            ws1_oauth_renew_margin = float(os.environ["AUTOPKG_ws1_oauth_renew_margin"])
            print(f"Found env var AUTOPKG_ws1_oauth_renew_margin: {ws1_oauth_renew_margin}")
        except ValueError:
            print(
                "Found env var AUTOPKG_ws1_oauth_renew_margin is NOT a float: "
                f"[{os.environ['AUTOPKG_ws1_oauth_renew_margin']}] - aborting!"
            )
            exit(code=1)
    else:
        ws1_oauth_renew_margin = 10
        print(f"Using default for ws1_oauth_renew_margin: {ws1_oauth_renew_margin}")

    if "AUTOPKG_ws1_oauth_keychain" in os.environ:
        ws1_oauth_keychain = os.environ["AUTOPKG_ws1_oauth_keychain"]
        print(f"Found env var AUTOPKG_ws1_oauth_keychain: {ws1_oauth_keychain}")
    else:
        ws1_oauth_keychain = "Autopkg_WS1_OAuth"
        print(f"Using default for ws1_oauth_keychain: {ws1_oauth_keychain}")

    # keychain = "login.keychain"
    service = "Autopkg_WS1_OAUTH"
    # service = "autopkg_tool_launcher"

    # get timestamp, round to nearest whole second
    timestamp_start = get_timestamp()
    print(f"Test START Timestamp: {timestamp_start.isoformat()}")

    # init to test until a bit after the default 3600 seconds token validity period
    time_stop = timestamp_start + timedelta(seconds=4000)

    # check existing or create new dedicated keychain to store the Oauth token and timestamp to trigger renewal"
    command = f"/usr/bin/security list-keychains -u user | grep -q {ws1_oauth_keychain}"
    result = subprocess.run(command, shell=True, capture_output=True)
    if not result.returncode == 0:
        # create new empty keychain
        command = f"/usr/bin/security create-keychain -p {ws1_oauth_client_secret} {ws1_oauth_keychain}"
        subprocess.run(command, shell=True, capture_output=True)

        # add keychain to beginning of user's keychain search list so we can find items in it, delete the newlines and
        # the double quotes
        command = "/usr/bin/security list-keychains -d user"
        result = subprocess.run(command, shell=True, capture_output=True)
        searchlist = result.stdout.decode().replace("\n", "")
        searchlist = searchlist.replace('"', "")
        command = f"/usr/bin/security list-keychains -d user -s {ws1_oauth_keychain} {searchlist}"
        subprocess.run(command, shell=True, capture_output=True)

        # removing relock timeout on keychain, thanks to https://forums.developer.apple.com/forums/thread/690665
        command = f"/usr/bin/security set-keychain-settings {ws1_oauth_keychain}"
        subprocess.run(command, shell=True, capture_output=True)

    oauth_token = get_password_from_keychain(ws1_oauth_keychain, service, "oauth_token")
    if oauth_token is not None:
        print(f"Retrieved existing token from keychain: {oauth_token}")
    oauth_token_renew_timestamp_str = get_password_from_keychain(
        ws1_oauth_keychain, service, "oauth_token_renew_timestamp"
    )
    if oauth_token_renew_timestamp_str is not None:
        oauth_token_renew_timestamp = datetime.fromisoformat(oauth_token_renew_timestamp_str)
        print(f"Retrieved timestamp to renew existing token from keychain: {oauth_token_renew_timestamp.isoformat()}")
    else:
        oauth_token_renew_timestamp = None
    while datetime.now().astimezone() < time_stop:
        timestamp = get_timestamp()
        if oauth_token is None or oauth_token_renew_timestamp is None or timestamp >= oauth_token_renew_timestamp:
            # the Oauth renewal API body payload
            payload = {
                "grant_type": "client_credentials",
                "client_id": ws1_oauth_client_id,
                "client_secret": ws1_oauth_client_secret,
            }

            """
            response = requests.request("POST", url, data=payload)
            check what headers were added automatically to POST request, thanks to https://stackoverflow.com/a/23816211
            """
            req = requests.Request("POST", ws1_oauth_token_url, data=payload)
            prepared_req = req.prepare()
            pretty_print_POST(prepared_req)

            print("Calling API to renew OAuth token.")
            s = requests.Session()
            """
            found out x-www-form-urlencoded is the default, tried making it explicit for clarity, but that causes a
            type-error.
            prepared_req.headers = {"Content-Type": "application/x-www-form-urlencoded"}
            """
            response = s.send(prepared_req)

            print(f"Response status code: {response.status_code}")
            print(f"Response text: {response.text}")

            if response.status_code == 200:
                # get timestamp, round to nearest whole second
                oauth_token_issued_timestamp = get_timestamp()
                print(f"Oauth2 token issued at: {oauth_token_issued_timestamp.isoformat()}")

                result = response.json()
                oauth_token = result["access_token"]
                print(f"Access token: {oauth_token}")
                print(f"Access token length: {len(result['access_token'])}")
                print(f"Access token validity is {result['expires_in']} seconds")

                renew_threshold = round(result["expires_in"] * (100 - ws1_oauth_renew_margin) / 100)
                print(f"Access token threshold for renewal set to {renew_threshold} seconds")
                oauth_token_renew_timestamp = oauth_token_issued_timestamp + timedelta(seconds=renew_threshold)
                print(f"Oauth2 token should be renewed after: {oauth_token_renew_timestamp.isoformat()}")

                # recalculate stop time until a bit after the actual token validity period from the API response
                test_runtime = round(result["expires_in"] * (100 + ws1_oauth_renew_margin) / 100)
                time_stop = timestamp_start + timedelta(seconds=test_runtime)
                print(f"Test stop scheduled for: {time_stop.isoformat()}")

            else:
                print(f"Got a bad response, status code: {response.status_code}")
                print(f"Error: {response.text}")
                exit(code=1)

        print("ToDo: test calling a program that can use the Oauth token")

        result = set_password_in_keychain(ws1_oauth_keychain, service, "oauth_token", oauth_token)
        result = set_password_in_keychain(
            ws1_oauth_keychain,
            service,
            "oauth_token_renew_timestamp",
            oauth_token_renew_timestamp.isoformat(),
        )

        timestamp = get_timestamp()
        print(f"Time: {timestamp.isoformat()}\tSleeping 5 minutes...")
        time.sleep(300)


if __name__ == "__main__":
    main()
