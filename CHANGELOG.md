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
 * clean up code, consistent use of f-strings
 * clean up code, confirm to Autopkg codestyle standards, added pre-commit
 * refactor recipes to remove duplicate parent recipes found in main Autopkg repos
 * add to main Autopkg repo recipe subfolder
 * make macsesh optional
