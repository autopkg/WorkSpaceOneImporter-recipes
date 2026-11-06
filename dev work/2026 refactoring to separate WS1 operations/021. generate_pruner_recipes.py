#!/usr/bin/env python3
"""Generate pruner recipes for all ws1 recipes. Run once, then delete this script."""

import os

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ws1-recipes")

TEMPLATE = (
    "Comment:\n"
    "Description: Prune old versions of {desc_name} from Workspace ONE, keep the given number of versions.\n"
    "Identifier: com.github.codeskipper.ws1-pruner.{identifier}\n"
    "MinimumVersion: '2.3'\n"
    "\n"
    "Input:\n"
    "  NAME: {appname}\n"
    "  WS1_APP_VERSIONS_TO_KEEP: NUMBER_OF_VERSIONS_TO_KEEP_HERE\n"
    "\n"
    "  # WS1 specific input,  secrets.  Only one set of API credentials is needed.\n"
    "  WS1_OAUTH_CLIENT_ID: OAUTH2_CLIENT_ID_HERE\n"
    "  WS1_OAUTH_CLIENT_SECRET: OAUTH2_CLIENT_CLIENT_SECRET_HERE\n"
    "  WS1_OAUTH_TOKEN_URL: OAUTH2_ACCESS_TOKEN_SERVER_URL_HERE\n"
    "  WS1_API_USERNAME: API_USERNAME_HERE\n"
    "  WS1_API_PASSWORD: API_PASSWORD_HERE\n"
    "  WS1_API_TOKEN: API_TOKEN_HERE\n"
    "  WS1_B64ENCODED_API_CREDENTIALS: B64ENCODED_API_CREDENTIALS_HERE\n"
    "  WS1_API_URL: WORKSPACEONE_API_URL_HERE\n"
    "  WS1_CONSOLE_URL: WORKSPACEONE_CONSOLE_URL_HERE\n"
    "  WS1_GROUPID: GROUP_ID_HERE\n"
    "\n"
    "Process:\n"
    "- Processor: com.github.codeskipper.OMNISSA-WorkSpaceOnePruner/WorkSpaceOnePruner\n"
    "  Arguments:\n"
    "    ws1_oauth_client_id: '%WS1_OAUTH_CLIENT_ID%'\n"
    "    ws1_oauth_client_secret: '%WS1_OAUTH_CLIENT_SECRET%'\n"
    "    ws1_oauth_token_url: '%WS1_OAUTH_TOKEN_URL%'\n"
    "    ws1_api_token: '%WS1_API_TOKEN%'\n"
    "    ws1_api_username: '%WS1_API_USERNAME%'\n"
    "    ws1_api_password: '%WS1_API_PASSWORD%'\n"
    "    ws1_b64encoded_api_credentials: '%WS1_B64ENCODED_API_CREDENTIALS%'\n"
    "    ws1_api_url: '%WS1_API_URL%'\n"
    "    ws1_groupid: '%WS1_GROUPID%'\n"
    "    ws1_app_versions_to_keep: '%WS1_APP_VERSIONS_TO_KEEP%'\n"
    "\n"
)

recipes = [
    ("Apparency.ws1-pruner.recipe.yaml", "Apparency", "Apparency", "Apparency"),
    ("CitrixWorkspace.ws1-pruner.recipe.yaml", "Citrix Workspace", "CitrixWorkspace", "Citrix Workspace"),
    ("DockerDesktop.ws1-pruner.recipe.yaml", "Docker Desktop", "DockerDesktop", "Docker Desktop"),
    ("Firefox.ws1-pruner.recipe.yaml", "Mozilla Firefox", "MozillaFirefox", "Mozilla Firefox"),
    ("GPGSuite.ws1-pruner.recipe.yaml", "'GPG Suite'", "GPGSuite", "GPG Suite"),
    ("GitHubCLI.ws1-pruner.recipe.yaml", "GitHub CLI", "GitHubCLI", "GitHub CLI"),
    ("GitHubDesktop.ws1-pruner.recipe.yaml", "GitHub Desktop", "GitHubDesktop", "GitHub Desktop"),
    ("GoogleChrome.ws1-pruner.recipe.yaml", "Google Chrome", "GoogleChrome", "Google Chrome"),
    ("Installomator.ws1-pruner.recipe.yaml", "Installomator", "Installomator", "Installomator"),
    ("JetBrainsToolbox.ws1-pruner.recipe.yaml", "JetBrains Toolbox", "JetBrainsToolbox", "JetBrains Toolbox"),
    ("LastPass-Safari.ws1-pruner.recipe.yaml", "LastPass for Safari", "LastPassSafari", "LastPass for Safari"),
    (
        "LexmarkUniversalDriverColor.ws1-pruner.recipe.yaml",
        "Lexmark Universal Printer Driver - Color",
        "LexmarkUniversalDriverColor",
        "Lexmark Universal Printer Driver - Color",
    ),
    (
        "MacAdminsPython.ws1-pruner.recipe.yaml",
        "MacAdmins Python Recommended",
        "MacAdminsPython",
        "MacAdmins Python Recommended",
    ),
    (
        "MicrosoftCompanyPortal.ws1-pruner.recipe.yaml",
        "Microsoft Company Portal",
        "MicrosoftCompanyPortal",
        "Microsoft Company Portal",
    ),
    ("MicrosoftDefender.ws1-pruner.recipe.yaml", "Microsoft Defender", "MicrosoftDefender", "Microsoft Defender"),
    ("MicrosoftTeams.ws1-pruner.recipe.yaml", "Microsoft Teams", "MicrosoftTeams", "Microsoft Teams"),
    (
        "MicrosoftVisualStudioCode.ws1-pruner.recipe.yaml",
        "Microsoft Visual Studio Code",
        "MicrosoftVisualStudioCode",
        "Microsoft Visual Studio Code",
    ),
    ("MunkiAdmin.ws1-pruner.recipe.yaml", "Munki Admin", "MunkiAdmin", "Munki Admin"),
    ("NodeJS-LTS.ws1-pruner.recipe.yaml", "'Node JS LTS'", "NodeJSLTS", "Node JS LTS"),
    (
        "PaloAltoNetworksGlobalProtect.ws1-pruner.recipe.yaml",
        "Palo Alto Networks GlobalProtect",
        "PaloAltoNetworksGlobalProtect",
        "Palo Alto Networks GlobalProtect",
    ),
    ("SuspiciousPackage.ws1-pruner.recipe.yaml", "Suspicious Package", "SuspiciousPackage", "Suspicious Package"),
    (
        "WorkspaceONEIntelligentHub.ws1-pruner.recipe.yaml",
        "VMWare Workspace ONE Intelligent Hub",
        "WorkspaceONEIntelligentHub",
        "VMWare Workspace ONE Intelligent Hub",
    ),
    ("erase-install.ws1-pruner.recipe.yaml", "Erase-Install", "EraseInstall", "Erase-Install"),
    ("iTerm2.ws1-pruner.recipe.yaml", "iTerm2", "iTerm2", "iTerm2"),
]

for filename, appname, identifier, desc_name in recipes:
    path = os.path.join(BASE, filename)
    content = TEMPLATE.format(appname=appname, identifier=identifier, desc_name=desc_name)
    with open(path, "w") as f:
        f.write(content)
    print(f"Created: {filename}")

print(f"\nTotal: {len(recipes)} pruner recipes created.")
