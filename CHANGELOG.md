Changelog (latest first):
 * optimise for CAR - separate out the WS1 API auth and supporting functions to a library
 * copy wiki from [old repo and wiki location](https://github.com/codeskipper/WorkSpaceOneImporter/wiki)
 * make macsesh optional
 * add to main Autopkg repo recipe subfolder
 * refactor recipes to remove duplicate parent recipes found in main Autopkg repos
 * clean up code, confirm to Autopkg codestyle standards, added pre-commit
 * clean up code, consistent use of f-strings
 * new feature to prune old software versions from WS1 UEM
 * added support for re-using OAuth tokens
 * added production ready example recipes (moved from my autopkg-recipe repo)
 * added support to specify advanced app assignment (API v.2) settings and update on schedule
 * added support for Oauth
 * merged PR#1 from @SoxIn4 - ability to supply base64 pre-encoded api username and password
 * add code to find icon file to upload
 * get force_import working
 * test new input "ws1_console_url" and code that produces link to imported app
 * **milestone: get POC working**
 * update API calls for WS1 as tested with Postman
 * update for Python3
 * try library dependency install for Autopkg as suggested [here](https://blog.eisenschmiede.com/posts/install-python-modules-in-autopkg-context/) -> working
 * get call as Autopkg Shared Processor stub to work from other repo
 * added stub recipe so shared processor can be found in recipes from other repos
 * rename files, classes, functions, variable names, and comments to reflect update to WS1 from Airwatch, update license, copyright
 * add roadmap to Readme.md
 * forked this repo from [jprichards/AirWatchImporter](https://github.com/jprichards/AirWatchImporter)
 * testing API calls involved for WS1 using Postman -> success

