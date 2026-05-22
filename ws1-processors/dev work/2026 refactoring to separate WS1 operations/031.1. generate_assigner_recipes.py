#!/usr/bin/env python3
"""Generate assigner recipes for all ws1 recipes. Kept in repository for reference and future reuse."""

import os

# Script location: ws1-processors/dev work/2026 refactoring to separate WS1 operations/
# Output recipes to: ws1-recipes/ (at repo root level)
BASE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../ws1-recipes"))

TEMPLATE = (
    "Comment: |\n"
    "  recipe with ws1_assignments for AppsV2 API style assignment-rules\n"
    "  See https://as135.awmdm.com/API/help/#!/apis/10001?!%2FAppsV2%2FAppsV2_UpdateAssignmentRuleAsync\n"
    "Description: Assigns {description_name} to smart groups in WorkSpace ONE UEM using assignment rules.\n"
    "Identifier: com.github.codeskipper.ws1-assigner.{identifier_suffix}\n"
    "\n"
    "MinimumVersion: '2.3'\n"
    "\n"
    "Input:\n"
    "  NAME: {app_display_name}\n"
    "\n"
    "  # WS1 specific input,  secrets\n"
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
    "  WS1_SMART_GROUP_NAME: SMART_GROUP_NAME_HERE\n"
    "  WS1_PUSH_MODE: PUSH_MODE_SETTING\n"
    "\n"
    "  # WS1 - AppsV2 advanced assignments input\n"
    "  # NOTE: This key must be lowercase to match the processor's input_variables key name directly.\n"
    "  # Complex types (lists/dicts) cannot use AutoPkg's %VAR% string substitution in Arguments.\n"
    "  ws1_app_assignments:\n"
    "      - distribution:\n"
    "          name: ASSIGNMENT_NAME\n"
    "          description: ASSIGNMENT_DESCRIPTION\n"
    "          smart_group_names:\n"
    "            - SMART_GROUP_NAME1\n"
    "            - SMART_GROUP_NAME2\n"
    "          app_delivery_method: AUTO_OR_ON_DEMAND\n"
    "          distr_delay_days: DISTRIBUTION_DELAY_DAYS\n"
    "          display_in_app_catalog: true\n"
    "          is_default_assignment: false\n"
    "          keep_app_updated_automatically: true\n"
    "        restriction:\n"
    "            remove_on_unenroll: false\n"
    "            managed_access: false\n"
    "            desired_state_management: false\n"
    "            prevent_removal: false\n"
    "\n"
    "Process:\n"
    "- Processor: com.github.codeskipper.OMNISSA-WorkSpaceOneAssigner/WorkSpaceOneAssigner\n"
    "  Arguments:\n"
    "    ws1_oauth_client_id: '%WS1_OAUTH_CLIENT_ID%'\n"
    "    ws1_oauth_client_secret: '%WS1_OAUTH_CLIENT_SECRET%'\n"
    "    ws1_oauth_token_url: '%WS1_OAUTH_TOKEN_URL%'\n"
    "    ws1_api_token: '%WS1_API_TOKEN%'\n"
    "    ws1_api_username: '%WS1_API_USERNAME%'\n"
    "    ws1_api_password: '%WS1_API_PASSWORD%'\n"
    "    ws1_b64encoded_api_credentials: '%WS1_B64ENCODED_API_CREDENTIALS%'\n"
    "    ws1_api_url: '%WS1_API_URL%'\n"
    "    ws1_console_url: '%WS1_CONSOLE_URL%'\n"
    "    ws1_groupid: '%WS1_GROUPID%'\n"
    "    ws1_smart_group_name: '%WS1_SMART_GROUP_NAME%'\n"
    "    ws1_push_mode: '%WS1_PUSH_MODE%'\n"
    "\n"
)

# Recipe metadata: (filename, app_display_name, identifier_suffix, description_name)
recipes = [
    ("Apparency.ws1-assigner.recipe.yaml", "Apparency", "Apparency", "Apparency"),
    ("CitrixWorkspace.ws1-assigner.recipe.yaml", "Citrix Workspace", "CitrixWorkspace", "Citrix Workspace"),
    ("DockerDesktop.ws1-assigner.recipe.yaml", "Docker Desktop", "DockerDesktop", "Docker Desktop"),
    ("Firefox.ws1-assigner.recipe.yaml", "Mozilla Firefox", "MozillaFirefox", "Mozilla Firefox"),
    ("GPGSuite.ws1-assigner.recipe.yaml", "'GPG Suite'", "GPGSuite", "GPG Suite"),
    ("GitHubCLI.ws1-assigner.recipe.yaml", "GitHub CLI", "GitHubCLI", "GitHub CLI"),
    ("GitHubDesktop.ws1-assigner.recipe.yaml", "GitHub Desktop", "GitHubDesktop", "GitHub Desktop"),
    ("GoogleChrome.ws1-assigner.recipe.yaml", "Google Chrome", "GoogleChrome", "Google Chrome"),
    ("Installomator.ws1-assigner.recipe.yaml", "Installomator", "Installomator", "Installomator"),
    ("JetBrainsToolbox.ws1-assigner.recipe.yaml", "JetBrains Toolbox", "JetBrainsToolbox", "JetBrains Toolbox"),
    ("LastPass-Safari.ws1-assigner.recipe.yaml", "LastPass for Safari", "LastPassSafari", "LastPass for Safari"),
    (
        "LexmarkUniversalDriverColor.ws1-assigner.recipe.yaml",
        "Lexmark Universal Printer Driver - Color",
        "LexmarkUniversalDriverColor",
        "Lexmark Universal Printer Driver - Color",
    ),
    (
        "MacAdminsPython.ws1-assigner.recipe.yaml",
        "MacAdmins Python Recommended",
        "MacAdminsPython",
        "MacAdmins Python Recommended",
    ),
    (
        "MicrosoftCompanyPortal.ws1-assigner.recipe.yaml",
        "Microsoft Company Portal",
        "MicrosoftCompanyPortal",
        "Microsoft Company Portal",
    ),
    ("MicrosoftDefender.ws1-assigner.recipe.yaml", "Microsoft Defender", "MicrosoftDefender", "Microsoft Defender"),
    ("MicrosoftEdge.ws1-assigner.recipe.yaml", "Microsoft Edge", "MicrosoftEdge", "Microsoft Edge"),
    ("MicrosoftTeams.ws1-assigner.recipe.yaml", "Microsoft Teams", "MicrosoftTeams", "Microsoft Teams"),
    (
        "MicrosoftVisualStudioCode.ws1-assigner.recipe.yaml",
        "Microsoft Visual Studio Code",
        "MicrosoftVisualStudioCode",
        "Microsoft Visual Studio Code",
    ),
    ("MunkiAdmin.ws1-assigner.recipe.yaml", "Munki Admin", "MunkiAdmin", "Munki Admin"),
    ("NodeJS-LTS.ws1-assigner.recipe.yaml", "'Node JS LTS'", "NodeJSLTS", "Node JS LTS"),
    (
        "PaloAltoNetworksGlobalProtect.ws1-assigner.recipe.yaml",
        "Palo Alto Networks GlobalProtect",
        "PaloAltoNetworksGlobalProtect",
        "Palo Alto Networks GlobalProtect",
    ),
    ("SuspiciousPackage.ws1-assigner.recipe.yaml", "Suspicious Package", "SuspiciousPackage", "Suspicious Package"),
    (
        "WorkspaceONEIntelligentHub.ws1-assigner.recipe.yaml",
        "VMWare Workspace ONE Intelligent Hub",
        "WorkspaceONEIntelligentHub",
        "VMWare Workspace ONE Intelligent Hub",
    ),
    ("erase-install.ws1-assigner.recipe.yaml", "Erase-Install", "EraseInstall", "Erase-Install"),
    ("iTerm2.ws1-assigner.recipe.yaml", "iTerm2", "iTerm2", "iTerm2"),
]

# Generate each recipe file
for filename, app_display_name, identifier_suffix, description_name in recipes:
    path = os.path.join(BASE, filename)
    content = TEMPLATE.format(
        app_display_name=app_display_name,
        identifier_suffix=identifier_suffix,
        description_name=description_name,
    )
    with open(path, "w") as f:
        f.write(content)
    print(f"Created: {filename}")

print(f"\nTotal: {len(recipes)} assigner recipes created.")
print(f"Output directory: {BASE}")
