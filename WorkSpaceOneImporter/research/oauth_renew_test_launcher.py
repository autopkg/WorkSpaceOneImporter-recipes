#!/usr/local/autopkg/python

"""
Launcher script for OAuth renewal script used in Research/testing when and how to renew the oauth token.

Fetch the secrets (passwords) from the dedicated macOS keychain used in the launcher tool used for development of
Autopkg processor.
Then pass the secrets as environment variables to the OAuth renewal script, like a CI/CD would to Autopkg
"""

import os
import subprocess


def get_password_from_keychain(keychain, service, account):
    command = f"/usr/bin/security find-generic-password -w -s '{service}' -a '{account}' '{keychain}'"
    result = subprocess.run(command, shell=True, capture_output=True)
    if result.returncode == 0:
        password = result.stdout.decode().strip()
        return password
    else:
        return None


def main():
    # keychain = "login.keychain"
    keychain = "autopkg_tools_launcher_keychain"
    # service = "Autopkg_WS1_OAUTH"
    service = "autopkg_tool_launcher"

    ws1_oauth_token_url = get_password_from_keychain(keychain, service, "WS1_OAUTH_TOKEN_URL")
    if ws1_oauth_token_url is None:
        print(f"Failed to get WS1_OAUTH_TOKEN_URL from keychain {keychain} - aborting")
        exit(code=1)
    print(f"Retrieved WS1_OAUTH_TOKEN_URL from keychain {keychain}")
    os.environ["AUTOPKG_ws1_oauth_token_url"] = ws1_oauth_token_url

    client_id = get_password_from_keychain(keychain, service, "WS1_OAUTH_CLIENT_ID")
    if client_id is None:
        print(f"Failed to get WS1_OAUTH_CLIENT_ID from keychain {keychain} - aborting")
        exit(code=1)
    print(f"Retrieved WS1_OAUTH_CLIENT_ID from keychain {keychain}")
    os.environ["AUTOPKG_ws1_oauth_client_id"] = client_id

    client_secret = get_password_from_keychain(keychain, service, "WS1_OAUTH_CLIENT_SECRET")
    if client_secret is None:
        print(f"Failed to get WS1_OAUTH_CLIENT_SECRET from keychain {keychain} - aborting")
        exit(code=1)
    print(f"Retrieved WS1_OAUTH_CLIENT_SECRET from keychain {keychain}")
    os.environ["AUTOPKG_ws1_oauth_client_secret"] = client_secret

    # launch oauth_renew_test.py
    subprocess.run(["/usr/local/autopkg/python", "oauth_renew_test.py"])


if __name__ == "__main__":
    main()
