# Parent selection, versions, and validation

## Follow the actual chain

A WS1 importer typically parents a community Munki recipe. That parent may consume a download recipe directly or chain through a pkg recipe. Only outputs from the selected chain are inherited.

Inspect the parent and current processor source for:

- NAME-dependent application paths versus hard-coded real bundle names.
- pkginfo.name and display_name behavior.
- Package path and available-version outputs.
- CFBundleVersion versus CFBundleShortVersionString and the installed-version comparison key.
- Signature identities, architecture support, and minimum OS detection.
- Custom installcheck, preinstall, and uninstall scripts.
- EndOfCheckPhase placement and processors that can write to a remote service.

A .pkg parent does not necessarily provide the installs array, minimum OS data, or other metadata a Munki child needs. Conversely, re-reading a version already supplied by the selected parent may be unnecessary. Trace actual values rather than assuming a filename or receipt version is reliable.

## Munki detection and sessions

AutoPkg determines the offered version when processing the artifact. Munki's endpoint metadata determines whether that offered version is already installed. Those are different tasks.

An installcheck_script takes precedence over normal installs/receipt detection. A script used to require a user session must therefore also make a correct installed-version decision; returning 0 merely because someone is logged in can request an unnecessary reinstall.

unattended_install controls silent background installation, not a universal requirement that a user be logged in. Upstream Munki can install non-unattended items at the login window. SuppressLoginwindowInstall is a client preference with an exception for unattended items. Embedded implementations may differ: verify their preference domain and invocation rather than claiming upstream behavior proves UEM behavior.

An inherited assertion about a vendor installer is evidence of recipe intent, not independent vendor documentation. Distinguish that from a tested requirement. Preserve deliberate session gating until a change has been evaluated. A preinstall script can refuse closer to installation, but failure there is not a graceful deferral and does not automatically justify replacing an installcheck script.

## Validation boundaries

Structural lint does not execute processors, resolve parent recipes, validate all API schemas, discover the vendor marketing name, or establish trust. AutoPkg info resolves the chain and inputs, but does not discover a runtime version or test installation.

A successful generator test proves script behavior, not that Pi/Copilot selected the skill or followed it. Check discovery and referenced-resource access in each host separately.

Inspect native AutoPkg's --help for the installed version. Use the project's preferences for supported commands, not an unrelated global default. Keep exported preference files, environment credentials, private overrides, logs, and trust records out of public examples.

No test in this tooling runs live imports, assignments, or pruning. A production test needs explicit approval, a defined tenant/test scope, and a reviewed rollback or cleanup plan.

## Further reading

- AutoPkg: https://github.com/autopkg/autopkg/wiki
- Munki pkginfo keys: https://github.com/munki/munki/wiki/Supported-Pkginfo-Keys
- Munki installed-state decisions: https://github.com/munki/munki/wiki/How-Munki-Decides-What-Needs-To-Be-Installed
- Munki preferences: https://github.com/munki/munki/wiki/Preferences
- Optional general recipe creation workflow: https://github.com/autopkg/homebysix-recipes/blob/master/.claude/skills/create-autopkg-recipes/SKILL.md

The homebysix workflow has its own repository conventions. It is linked, not copied or installed by this skill. Do not apply its identifiers or metadata policies blindly to WS1 recipes.
