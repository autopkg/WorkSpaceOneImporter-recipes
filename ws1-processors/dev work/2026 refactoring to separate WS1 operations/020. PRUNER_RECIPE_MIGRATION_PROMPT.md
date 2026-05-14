# Migration Prompt: Extract Pruning Operations into Separate Recipes

## Objective

Migrate the pruning operation from each existing `.ws1.recipe.yaml` file into a corresponding **separate** `.ws1-pruner.recipe.yaml` file that uses the `WorkSpaceOnePruner` processor. This decouples version management from app import/assignment workflows, allowing teams to prune old app versions independently via the AutoPkg scheduler or manual triggers.

## Target Example

Use **`MicrosoftEdge.ws1-pruner.recipe.yaml`** as the reference template for all new pruner recipes. This recipe demonstrates:
- Simple, focused responsibility: delete old app versions only
- Required metadata: `NAME`, versioning-related inputs, and WS1 authentication credentials
- Minimal configuration: no app assignments, parent recipe chains, or app-specific settings
- Standardized (`WorkSpaceOnePruner`) processor usage across all pruner recipes

## Key Differences: Regular `.ws1.recipe.yaml` vs. `.ws1-pruner.recipe.yaml`

| Aspect | Regular `.ws1.recipe.yaml` | `.ws1-pruner.recipe.yaml` |
|--------|---------------------------|------------------------|
| **Purpose** | Download, package, import app, assign to smart groups | Prune old versions only |
| **Processor** | `com.github.codeskipper.OMNISSA-WorkSpaceOneImporter/WorkSpaceOneImporter` | `com.github.codeskipper.OMNISSA-WorkSpaceOnePruner/WorkSpaceOnePruner` |
| **ParentRecipe** | References community munki recipe (e.g., `com.github.autopkg.munki.firefox-rc-en_US`) | **None** — standalone recipe |
| **Inputs** | NAME, LOCALE, RELEASE, ws1_app_assignments, auth credentials | NAME, WS1_APP_VERSIONS_TO_KEEP, auth credentials |
| **Process Block** | Single importer step with app assignments | Single pruner step with version limits |
| **Run Frequency** | Typically when app version changes (triggered by download step) | Scheduled independently (e.g., weekly, monthly) |

## Critical Rules

1. **`WS1_APP_VERSIONS_TO_KEEP` must be a STRING** — not an integer. This is mandatory even in recipe overrides. Passing an integer causes a runtime error: `'expected string or bytes-like object'`. See `AGENTS.md` § "Key Conventions."

2. **Naming Convention**:
   - Source recipe: `{AppName}.ws1.recipe.yaml`
   - Pruner recipe: `{AppName}.ws1-pruner.recipe.yaml`
   - Identifier: `com.github.codeskipper.ws1-pruner.{AppName}` (replacing spaces with empty string or using camelCase as needed)

3. **Authentication Must Match**: All `WS1_*` credentials in the pruner recipe must correspond to the same WS1 environment (API URL, organization group, etc.) as the importer recipe.

4. **No Parent Recipe**: Pruner recipes are **standalone** and do **not** chain a parent Munki recipe. They interact directly with Workspace ONE.

5. **Processor Identifier**: The processor block must reference the **exact identifier** registered in `WorkSpaceOnePruner.recipe.yaml`:
   ```yaml
   Processor: com.github.codeskipper.OMNISSA-WorkSpaceOnePruner/WorkSpaceOnePruner
   ```

## Step-by-Step Migration Instructions

### For Each Existing `.ws1.recipe.yaml` Recipe

#### Step 1: Gather Information
- **App Name** (`NAME` field): Extract from the original recipe's Input section
- **Identifier**: Create a new unique identifier in the format `com.github.codeskipper.ws1-pruner.{AppName}`
- **Processor Path**: Reference `com.github.codeskipper.OMNISSA-WorkSpaceOnePruner/WorkSpaceOnePruner`

#### Step 2: Create Pruner Recipe File
Create a new file: `ws1-recipes/{AppName}.ws1-pruner.recipe.yaml`

#### Step 3: Populate Required Structure

Follow this template, replacing placeholders:

```yaml
Comment:
Description: Prune old versions of {AppName} from Workspace ONE, keep the given number of versions.
Identifier: com.github.codeskipper.ws1-pruner.{AppName}
MinimumVersion: '2.3'

Input:
  NAME: {AppName}
  WS1_APP_VERSIONS_TO_KEEP: NUMBER_OF_VERSIONS_TO_KEEP_HERE

  # WS1 specific input, secrets. Only one set of API credentials is needed.
  WS1_OAUTH_CLIENT_ID: OAUTH2_CLIENT_ID_HERE
  WS1_OAUTH_CLIENT_SECRET: OAUTH2_CLIENT_CLIENT_SECRET_HERE
  WS1_OAUTH_TOKEN_URL: OAUTH2_ACCESS_TOKEN_SERVER_URL_HERE
  WS1_API_USERNAME: API_USERNAME_HERE
  WS1_API_PASSWORD: API_PASSWORD_HERE
  WS1_API_TOKEN: API_TOKEN_HERE
  WS1_B64ENCODED_API_CREDENTIALS: B64ENCODED_API_CREDENTIALS_HERE
  WS1_API_URL: WORKSPACEONE_API_URL_HERE
  WS1_CONSOLE_URL: WORKSPACEONE_CONSOLE_URL_HERE
  WS1_GROUPID: GROUP_ID_HERE

Process:
- Processor: com.github.codeskipper.OMNISSA-WorkSpaceOnePruner/WorkSpaceOnePruner
  Arguments:
    ws1_oauth_client_id: '%WS1_OAUTH_CLIENT_ID%'
    ws1_oauth_client_secret: '%WS1_OAUTH_CLIENT_SECRET%'
    ws1_oauth_token_url: '%WS1_OAUTH_TOKEN_URL%'
    ws1_api_token: '%WS1_API_TOKEN%'
    ws1_api_username: '%WS1_API_USERNAME%'
    ws1_api_password: '%WS1_API_PASSWORD%'
    ws1_b64encoded_api_credentials: '%WS1_B64ENCODED_API_CREDENTIALS%'
    ws1_api_url: '%WS1_API_URL%'
    ws1_groupid: '%WS1_GROUPID%'
    ws1_app_versions_to_keep: '%WS1_APP_VERSIONS_TO_KEEP%'
```

#### Step 4: Replace Placeholders

- **`{AppName}`**: The application name from the original recipe (e.g., "Mozilla Firefox", "Google Chrome")
- **`NUMBER_OF_VERSIONS_TO_KEEP_HERE`**: A sensible default string (e.g., `"5"`, `"3"`). Teams can override this per recipe in overrides or via environment variables.

#### Step 5: Validate Against MicrosoftEdge Template

Ensure your new pruner recipe:
- Matches the exact structure of `MicrosoftEdge.ws1-pruner.recipe.yaml`
- Has NO `ParentRecipe` key
- Has NO `ws1_app_assignments` block
- Has NO app-specific inputs like `LOCALE`, `RELEASE`
- Includes all WS1 authentication placeholders (even if unused)
- Uses **string** values for `WS1_APP_VERSIONS_TO_KEEP`

#### Step 6: Lint & Validate

Run the pre-commit hook for recipe validation:
```bash
/Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/pre-commit run --all-files
```

Or manually validate with `autopkg` (dry run):
```bash
export AUTOPKG_verbose=2
autopkg run {AppName}.ws1-pruner.recipe.yaml --check  # (if --check is supported)
# Or verbose test run with overrides
autopkg run {AppName}.ws1-pruner.recipe.yaml \
  --key=WS1_APP_VERSIONS_TO_KEEP="5" \
  --key=WS1_API_URL="https://your-ws1-api.example.com" \
  # ... other credentials
```

#### Step 7: Git Commit

Commit the new pruner recipe with a message like:
```
feat: add {AppName} pruner recipe for version management

- Extract pruning logic into standalone {AppName}.ws1-pruner.recipe.yaml
- Use WorkSpaceOnePruner processor
- Allows independent scheduling of version cleanup
- Fixes #ISSUE_NUMBER (if applicable)
```

---

## Recipes to Migrate

The following existing `.ws1.recipe.yaml` recipes should have corresponding pruner recipes created:

1. **Apparency.ws1.recipe.yaml** → `Apparency.ws1-pruner.recipe.yaml`
2. **CitrixWorkspace.ws1.recipe.yaml** → `CitrixWorkspace.ws1-pruner.recipe.yaml`
3. **DockerDesktop.ws1.recipe.yaml** → `DockerDesktop.ws1-pruner.recipe.yaml`
4. **Firefox.ws1.recipe.yaml** → `Firefox.ws1-pruner.recipe.yaml`
5. **GPGSuite.ws1.recipe.yaml** → `GPGSuite.ws1-pruner.recipe.yaml`
6. **GitHubCLI.ws1.recipe.yaml** → `GitHubCLI.ws1-pruner.recipe.yaml`
7. **GitHubDesktop.ws1.recipe.yaml** → `GitHubDesktop.ws1-pruner.recipe.yaml`
8. **GoogleChrome.ws1.recipe.yaml** → `GoogleChrome.ws1-pruner.recipe.yaml`
9. **Installomator.ws1.recipe.yaml** → `Installomator.ws1-pruner.recipe.yaml`
10. **JetBrainsToolbox.ws1.recipe.yaml** → `JetBrainsToolbox.ws1-pruner.recipe.yaml`
11. **LastPass-Safari.ws1.recipe.yaml** → `LastPass-Safari.ws1-pruner.recipe.yaml`
12. **LexmarkUniversalDriverColor.ws1.recipe.yaml** → `LexmarkUniversalDriverColor.ws1-pruner.recipe.yaml`
13. **MacAdminsPython.ws1.recipe.yaml** → `MacAdminsPython.ws1-pruner.recipe.yaml`
14. **MicrosoftCompanyPortal.ws1.recipe.yaml** → `MicrosoftCompanyPortal.ws1-pruner.recipe.yaml`
15. **MicrosoftDefender.ws1.recipe.yaml** → `MicrosoftDefender.ws1-pruner.recipe.yaml`
16. **MicrosoftEdge.ws1.recipe.yaml** → `MicrosoftEdge.ws1-pruner.recipe.yaml` ✓ (already exists)
17. **MicrosoftTeams.ws1.recipe.yaml** → `MicrosoftTeams.ws1-pruner.recipe.yaml`
18. **MicrosoftVisualStudioCode.ws1.recipe.yaml** → `MicrosoftVisualStudioCode.ws1-pruner.recipe.yaml`
19. **MunkiAdmin.ws1.recipe.yaml** → `MunkiAdmin.ws1-pruner.recipe.yaml`
20. **NodeJS-LTS.ws1.recipe.yaml** → `NodeJS-LTS.ws1-pruner.recipe.yaml`
21. **PaloAltoNetworksGlobalProtect.ws1.recipe.yaml** → `PaloAltoNetworksGlobalProtect.ws1-pruner.recipe.yaml`
22. **SuspiciousPackage.ws1.recipe.yaml** → `SuspiciousPackage.ws1-pruner.recipe.yaml`
23. **WorkspaceONEIntelligentHub.ws1.recipe.yaml** → `WorkspaceONEIntelligentHub.ws1-pruner.recipe.yaml`
24. **erase-install.ws1.recipe.yaml** → `erase-install.ws1-pruner.recipe.yaml`
25. **iTerm2.ws1.recipe.yaml** → `iTerm2.ws1-pruner.recipe.yaml`

---

## Testing & Troubleshooting

### Before Deployment

Testing is performed from a **separate AutoPkg CI/CD repository** (e.g., [cloud-autopkg-runner](https://pypi.org/project/cloud-autopkg-runner/)) where WS1 API credentials are available as environment variables or securely injected secrets. The pruner recipes in **this** repository contain only placeholder values — they are never run directly from here.

1. **Validate recipe syntax locally** (no credentials required):
   ```bash
   /Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/pre-commit run --all-files
   ```

2. **Dry-run from CI/CD repository** (credentials available):
   Once the new pruner recipes are committed to this repo and picked up by the CI/CD runner, perform a dry-run to verify the recipe works end-to-end without actually deleting anything:
   ```bash
   autopkg run {AppName}.ws1-pruner.recipe.yaml \
     --key=ws1_app_versions_prune=dry_run \
     --key=WS1_APP_VERSIONS_TO_KEEP="5"
   ```
   Expected outcome: Lists app versions found and marks which would be pruned, but does not delete them.

3. **Verify the app name matches WS1**: The `NAME` field must exactly match what is stored in Workspace ONE, or the app search will fail silently. Confirm by checking the Workspace ONE UEM console.

4. **Promote to live pruning**: After a successful dry-run, switch `ws1_app_versions_prune` to `True` in the CI/CD recipe override or run configuration to enable actual deletion of old versions.

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **`'expected string or bytes-like object'` error** | `WS1_APP_VERSIONS_TO_KEEP` passed as an integer | Use string in recipe override: `WS1_APP_VERSIONS_TO_KEEP: "5"` (note quotes) |
| **"No app versions found"** | App name does not match WS1 database | Verify `NAME` field matches exactly in Workspace ONE console |
| **Authentication failures** | Invalid or expired WS1 credentials | Confirm OAuth client ID/secret or API token in the CI/CD runner's secret store |
| **Recipe validation fails** | Syntax errors in YAML or missing required fields | Compare with `MicrosoftEdge.ws1-pruner.recipe.yaml` line-by-line |
| **Recipe not found by CI/CD runner** | Recipe repo not added to AutoPkg search paths | Ensure the CI/CD runner's `autopkg repo-list` includes this repository |

---

## Additional Resources

- **Processor Documentation**: See `ws1-processors/WorkSpaceOnePruner.py` for input/output variable definitions
- **Architecture Overview**: Ref. `AGENTS.md` § "Architecture" and "Key Conventions"
- **AutoPkg Docs**: https://github.com/autopkg/autopkg/wiki
- **Pre-commit Validation**: See `AGENTS.md` § "Code Style & Linting"

---

## Summary Checklist

- [ ] For **each** recipe in the Migration List above:
  - [ ] Create `.ws1-pruner.recipe.yaml` file in `ws1-recipes/` directory
  - [ ] Set `NAME` from original `.ws1.recipe.yaml`
  - [ ] Create unique `Identifier` (e.g., `com.github.codeskipper.ws1-pruner.{AppName}`)
  - [ ] Use **exact** processor path: `com.github.codeskipper.OMNISSA-WorkSpaceOnePruner/WorkSpaceOnePruner`
  - [ ] Include all WS1 authentication Input placeholders
  - [ ] Set default `WS1_APP_VERSIONS_TO_KEEP` as string (e.g., `"5"`)
  - [ ] Remove any `ParentRecipe`, `ws1_app_assignments`, or app-specific inputs (LOCALE, RELEASE, etc.)
  - [ ] Run linting/validation locally (`pre-commit run --all-files`)
  - [ ] Commit with descriptive message
  - [ ] Dry-run from CI/CD repository to verify end-to-end before enabling live pruning

---

**Status**: Ready for agent or manual execution. Reference `MicrosoftEdge.ws1-pruner.recipe.yaml` as the definitive template.

