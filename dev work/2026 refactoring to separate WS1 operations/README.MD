Refactoring was needed to adopt cloud-autopkg-runner.
This prompted the need to separate out the Importer functions because execution is cut short with this library if there are no new imports.

Therefore, started creating a library with base functions.

Slacker being the first consumer of the library, it is the first to use the new Importer base functions

Pruning functions were separated out into its own recipes.

Assignment staging recipes are next.



