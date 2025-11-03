### WorkSpaceOneImporter processor and recipes
___

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A set of recipes and a custom processor for use with Omnissa Workspace ONE UEM. Formerly known as a VMware business and product. Going back further, Airwatch was the product name for the MDM product.

WorkSpaceOneImporter is a custom AutoPkg Processor for automating import of Mac product installer packages into Workspace ONE UEM. It can also assign them to one or multiple smart groups, and set certain deployment options such as Push Mode. It has support for automated staging to assignment groups.  Automated pruning of old versions can also be enabled and configured in detail if needed.

Adapted from [jprichards/AirWatchImporter](https://github.com/jprichards/AirWatchImporter).

___

## Heads up 

# duplicate app issues

Workspace ONE UEM version 2410 introduced a change to the internal macOS native app bundle ID from the leading "com.vmw.macos." to "com.ws1.macos.".  When uploading manually hrough the browser, UEM checks for pre-existing software titles, and if found, it uses the same bundle ID for the new app version.  This check is not done for uploads using the API, and this results in duplicate native apps.  

This leads to multiple issues installing and updating the affected apps.  Firstly , it's confusing for both the end-user and the admin.  Secondly, app updates are not installing as expected.  Last but not least, when all the old versions of the app with the bundle ID with leading "com.vmw.macos." are purged as they are deactivated/deleted from UEM, uninstall is triggered for the new version as well and it is thus removed from the end user Mac.

Omnissa has recognized the root cause for the duplicate macOS native apps and has announced a fix to be released in a future version.

# unexpected uninstall of apps and issue reinstalling

In the situation where duplicate apps were created and later pruned from UEM, and on modern stack, there have been incidents in at least one environment after a batch of app removals that were paused, and later Dismissed from UEM, this has triggered release of other batches of app removals for the same apps and also other apps with the duplicate issue.  
 
When the unexpected app removals occurred on the end-user Mac computers, the (Re)Install button did not result in the app getting reinstalled, it button status just kept spinning in the Hub and users had to download and install the missing apps manually.  
 
The Omnissa service case for these issues is under analysis by the engineering team and is not resolved yet.  Some remediation scripts are being tested and are slated to become part of the upcoming release of Hub, version 24.11.4.

---
### Roadmap

Project is working stable in production. You can reach me as @Martinus in MacAdmins Slack. Issues and PRs welcome in GitHub.

Done:
 * testing API calls involved for WS1 using Postman -> success
 * forked this repo from [jprichards/AirWatchImporter](https://github.com/jprichards/AirWatchImporter)
 * add roadmap to Readme.md
 * rename files, classes, functions, variable names, and comments to reflect update to WS1 from Airwatch, update license, copyright
 * added stub recipe so shared processor can be found in recipes from other repos
 * get call as Autopkg Shared Processor stub to work from other repo
 * try library dependency install for Autopkg as suggested [here](https://blog.eisenschmiede.com/posts/install-python-modules-in-autopkg-context/) -> working
 * update for Python3
 * update API calls for WS1 as tested with Postman
 * **milestone: get POC working**
 * test new input "ws1_console_url" and code that produces link to imported app
 * get force_import working
 * add code to find icon file to upload
 * merged PR#1 from @SoxIn4 - ability to supply base64 pre-encoded api username and password
 * added support for Oauth
 * added support to specify advanced app assignment (API v.2) settings and update on schedule
 * added production ready example recipes (moved from my autopkg-recipe repo)
 * added support for re-using OAuth tokens
 * new feature to prune old software versions from WS1 UEM
 * cleanup code, consistent use of f-strings
 * cleanup code, confirm to Autopkg codestyle standards, added pre-commit
 * refactor recipes to remove duplicate parent recipes found in main Autopkg repos
 * add to main Autopkg repo recipe subfolder

ToDo:
 * copy wiki from [old repo and wiki location](https://github.com/codeskipper/WorkSpaceOneImporter/wiki) and expand usage documentation
 * establish separate demo repo

---

## Dependencies

### Server Side
You _must_ be running AirWatch Console 9.3.0.0 or higher.

### Client/AutoPkg Side

Currently, in order to run AirWatchImporter, you must first install two Python libraries:

* The `requests` library
* The `requests_toolbelt` library

These can be installed by running: [(Thanks)](https://blog.eisenschmiede.com/posts/install-python-modules-in-autopkg-context/)

```
sudo -H /Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/pip3 install requests
sudo -H /Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/pip3 install requests_toolbelt
```

---
## AutoPkg Shared Processor

As of AutoPkg 0.4.0 you can use this processor as a shared processor.

Add the processor repo:

```
autopkg repo-add https://github.com/codeskipper/WorkSpaceOneImporter.git
```

Then use this as the processor in your recipes:

```
com.github.codeskipper.WorkSpaceOneImporter/WorkSpaceOneImporter
```

---
## Sensitive input variables
The processor currently requires sensitive keys like password and API token to be populated in your recipe (override) Input variables, or by command line keys.

Instead of keeping secrets in plain text recipe override files, they can be added to a macOS keychain. I took a peek at - [this](https://stackoverflow.com/questions/57838889/manage-keychain-to-codesign-macos-ios-app-with-xcodebuild-unattended) and now have a working launcher shell script for a Python wrapper, and I'll share when I can  - it's currently in a private repo for GitHub CI as described below. This is useful for testing, in production I use a CI/CD pipeline on a self-hosted GitHub runner.


### best with CI/CD
You can use a CI/CD tool like GitHub actions to wrap credentials securely as secrets and inject to your Autopkg action(script). I'm running an adapted version of [the example provided by Gusto](https://engineering.gusto.com/running-autopkg-in-github-actions/) in production. Sharing a public version of the adapted code as documentation and/or demo is on the roadmap.


---
## Available Input Variables

### All start with "ws1_"
When working to set up GitHub CI with this processor, it became clear consistent naming for input variables will make reading logs etc. much easier.

### Choose your input vars
You'll need to specify credentials for either Oauth or Basic authentication.
<br><br>`ws1_force_import` and `ws1_import_new_only` are intended for troubleshooting (new) recipes.

`ws1_console_url` is there as a convenience, so you can get a direct link to a newly imported package in the WS1 console.

`ws1_smart_group_name` and `ws1_push_mode` let you make simple App Assignments to Assignment Groups, while `ws1_app_assignments` gives you complete control over the App Assignment settings, but needs more settings in the recipe override.

`ws1_app_versions_prune` lets you prune old software versions, it is set to `dry_run` per default. Behaviour can be controlled in detail by setting `ws1_app_versions_to_keep` and `ws1_app_versions_to_keep_default`.


* [`ws1_api_url`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_api_url)
* [`ws1_console_url`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_console_url)
* [`ws1_oauth_client_id`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_oauth_client_id)
* [`ws1_oauth_client_secret`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_oauth_client_secret)
* [`ws1_oauth_token_url`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_oauth_token_url)
* [`ws1_api_token`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_api_token)
* [`ws1_api_username`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_api_username)
* [`ws1_api_password`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_api_password)
* [`ws1_b64encoded_api_credentials`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_b64encoded_api_credentials)
* [`ws1_force_import`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_force_import)
* [`ws1_import_new_only`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_import_new_only)
* [`ws1_groupid`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_groupid)
* [`ws1_smart_group_name`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_smart_group_name)
* [`ws1_push_mode`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_push_mode)
* [`ws1_app_assignments`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_app_assignments)
* [`ws1_update_assignments`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_update_assignments)
* [`ws1_app_versions_to_keep`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_app_versions_to_keep)
* [`ws1_app_versions_to_keep_default`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_app_versions_to_keep_default)
* [`ws1_app_versions_prune`](https://github.com/codeskipper/WorkSpaceOneImporter/wiki/ws1_app_versions_prune)


### List available input variables
You can list the custom processor info, including input variables from cli like so:

````
autopkg processor-info WorkSpaceOneImporter --recipe com.github.codeskipper.WorkSpaceOneImporter
````

---

## Sample Processor
```
<key>Process</key>
<array>
	<dict>
		<key>Processor</key>
		<string>com.github.codeskipper.WorkSpaceOneImporter/WorkSpaceOneImporter</string>
		<key>Arguments</key>
		<dict>
			<key>ws1_munki_repo_path</key>
			<string>MUNKI_REPO_PATH_HERE</string>
			<key>ws1_api_token</key>
			<string>API_TOKEN_HERE</string>
			<key>ws1_api_url</key>
			<string>WORKSPACEONE_API_URL_HERE</string>
			<key>ws1_console_url</key>
			<string>WORKSPACEONE_CONSOLE_URL_HERE</string>
			<key>ws1_api_username</key>
			<string>API_USERNAME_HERE</string>
			<key>ws1_api_password</key>
			<string>API_PASSWORD_HERE</string>
			<key>ws1_b64encoded_api_credentials</key>
		    <string>Basic QVBJX1VTRVJOQU1FX0hFUkU6QVBJX1BBU1NXT1JEX0hFUkU=</string>
			<key>ws1_groupid</key>
			<string>GROUP_ID_HERE</string>
			<key>ws1_smart_group_name</key>
			<string>SMART_GROUP_NAME</string>
			<key>ws1_push_mode</key>
			<string>PUSH_MODE, Auto or On-Demand</string>
		</dict>
	</dict>
</array>
```

## Example AutoPkg Recipe

Example recipe below for Suspicious Package.ws1.recipe  is from:
https://github.com/codeskipper/WorkSpaceOneImporter/blob/main/ws1-plist/SuspiciousPackage.ws1-plist.recipe

```
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Description</key>
	<string>Creates a munki package for Suspicious Package, imports it into WorkSpace ONE.</string>
	<key>Identifier</key>
	<string>com.github.codeskipper.ws1.SuspiciousPackage</string>
	<key>Input</key>
	<dict>
		<key>WS1_API_TOKEN</key>
		<string>API_TOKEN_HERE</string>
		<key>WS1_API_USERNAME</key>
		<string>API_USERNAME_HERE</string>
		<key>WS1_API_PASSWORD</key>
		<string>API_PASSWORD_HERE</string>
		<key>WS1_MUNKI_REPO_PATH</key>
		<string>MUNKI_REPO_PATH_HERE</string>
		<key>WS1_API_URL</key>
		<string>WORKSPACEONE_API_URL_HERE</string>
		<key>WS1_CONSOLE_URL</key>
		<string>WORKSPACEONE_CONSOLE_URL_HERE</string>
		<key>WS1_GROUPID</key>
		<string>GROUP_ID_HERE</string>
		<key>WS1_SMART_GROUP_NAME</key>
		<string>SMART_GROUP_NAME_HERE</string>
		<key>WS1_PUSH_MODE</key>
		<string>PUSH_MODE</string>
	</dict>
	<key>ParentRecipe</key>
	<string>com.github.codeskipper.munki.SuspiciousPackage</string>
	<key>MinimumVersion</key>
	<string>0.4.0</string>
	<key>Process</key>
	<array>
		<dict>
			<key>Processor</key>
			<string>com.github.codeskipper.WorkSpaceOneImporter/WorkSpaceOneImporter</string>
			<key>Arguments</key>
			<dict>
				<key>ws1_munki_repo_path</key>
				<string>%WS1_MUNKI_REPO_PATH%</string>
				<key>ws1_api_token</key>
				<string>%WS1_API_TOKEN%</string>
				<key>ws1_api_username</key>
				<string>%WS1_API_USERNAME%</string>
				<key>ws1_api_password</key>
				<string>%WS1_API_PASSWORD%</string>
				<key>ws1_api_url</key>
				<string>%WS1_API_URL%</string>
				<key>ws1_groupid</key>
				<string>%WS1_GROUPID%</string>
				<key>ws1_console_url</key>
				<string>%WS1_CONSOLE_URL%</string>
				<key>ws1_smart_group_name</key>
				<string>%WS1_SMART_GROUP_NAME%</string>
				<key>ws1_push_mode</key>
				<string>%WS1_PUSH_MODE%</string>
			</dict>
		</dict>
	</array>
</dict>
</plist>
```

---
### yaml format in recipes
My ws1 recipes are in yaml format thanks to the convincing examples from [Graham Pugh's recipes](https://github.com/autopkg/grahampugh-recipes/tree/main#wait-these-are-all-yaml-files).  His [plist-yaml-plist conversion tool](https://github.com/grahampugh/plist-yaml-plist) has helped me as well, especially when writing new recipes.


___
Create a recipe override like this first (if you prefer plist format):
```autopkg make-override SuspiciousPackage.ws1.recipe```

Again yaml format is easier to deal with, especially if you leave only the input variables you need to override and strip away the rest.
```autopkg make-override --format=yaml SuspiciousPackage.ws1.recipe.yaml```

<br/>
Edit it for settings to fit your environment

```open -a bbedit SuspiciousPackage.ws1.recipe.yaml```

<br/>

### Testing
You can run autopkg like this, but be aware: verbose level > 2 will show your password etc. in plaintext on screen
```
autopkg run -vvvv --key ws1_import_new_only=false --key ws1_update_assignments=true SuspiciousPackage.ws1.recipe.yaml
```

When testing, you may need to specify an increasing number of settings. You may find it helpful to set these like shell environment variables like so.
```
export AUTOPKG_verbose=2
export AUTOPKG_ws1_import_new_only=false
export AUTOPKG_ws1_update_assignments=True
autopkg run SuspiciousPackage.ws1.recipe.yaml
```

During development, I've used a launcher script to store (secret) settings in a dedicated keychain and fetch just before calling autopkg. Sharing this script is on the roadmap.

---
### code-style and pre-commit hooks
Uses the same environment as Autopkg.

Install the pre-commit hook like so:
````
/Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/pre-commit install --install-hooks
````

isort needed `profile = "black"`  in [.isort.cfg](.isort.cfg) and `args: ["--profile", "black"]` in [.pre-commit-config.yaml](.pre-commit-config.yaml) to avoid conflict with black

line-length was set at 120 in [.isort.cfg](.isort.cfg) and in [.flake8](.flake8) just because it was the default I got used to in PyCharm

Found a useful hint to integrate flake8 in PyCharm as external tool [here](https://gist.github.com/tossmilestone/23139d870841a3d5cba2aea28da1a895).

Check all the files:
```
/Library/AutoPkg/Python3/Python.framework/Versions/Current/bin/pre-commit run --all-files
```
