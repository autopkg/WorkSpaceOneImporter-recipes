# Refactoring Prompt: Extract Authentication into WorkSpaceOneImporterBase

## Objective

Separate all authentication-related functions from
`ws1-processors/WorkSpaceOneImporter.py` into a new base-class module
`ws1-processors/ws1_lib/WorkSpaceOneImporterBase.py` containing the class
`WorkSpaceOneImporterBase(Processor)`.

The goal is to create a reusable authentication/session foundation that future
specialised processors (e.g. a standalone App-Uploader, Assignment-Manager,
Version-Pruner) can inherit from, each getting WS1 REST API authentication
"for free."

---

## Context & Constraints

| Item | Detail |
|---|---|
| **Runtime** | `/usr/local/autopkg/python` (AutoPkg's bundled Python 3.10) |
| **Base class** | `autopkglib.Processor` (from `/Library/AutoPkg/autopkglib/__init__.py`) – provides `self.env`, `self.output()`, and the `main()` / `execute_shell()` contract. |
| **Formatter** | Black, line-length 120 (see `pyproject.toml`). |
| **Dependencies** | `requests`, `requests_toolbelt` (already installed); optional `macsesh`. |
| **Package layout** | `ws1_lib/` must become an importable package (add `__init__.py`). |
| **Backwards compat** | `WorkSpaceOneImporter.py` must continue to work identically after the refactor – it will `import` and subclass `WorkSpaceOneImporterBase` instead of `Processor` directly. |

---

## What to Extract into `WorkSpaceOneImporterBase`

### 1. Module-level helper functions (move as-is)

| Function | Current lines | Purpose |
|---|---|---|
| `get_password_from_keychain(keychain, service, account)` | 94–104 | Fetch secret from macOS keychain |
| `set_password_in_keychain(keychain, service, account, password)` | 107–121 | Store secret in macOS keychain |
| `get_timestamp()` | 86–91 | RFC 3339 timestamp rounded to the nearest second |
| `is_url(url)` | 134–139 | URL validation helper |

### 2. Module-level SSL / CA-certificate bootstrap (move as-is)

Lines 32–56: the `REQUESTS_CA_BUNDLE` / `macsesh` detection block and the
`import requests` / `from requests_toolbelt …` imports.
The base module should own these so that every subclass processor automatically
gets correct TLS behaviour.

### 3. Instance methods → move into `WorkSpaceOneImporterBase`

| Method | Current lines | Purpose |
|---|---|---|
| `oauth_keychain_init(self, password)` | 317–393 | Create / unlock dedicated keychain for OAuth token persistence |
| `get_oauth_token(self, oauth_client_id, oauth_client_secret, oauth_token_url)` | 395–498 | Retrieve or refresh an OAuth 2.0 access token |
| `get_oauth_headers(self, oauth_client_id, oauth_client_secret, oauth_token_url)` | 500–507 | Build `Authorization: Bearer …` headers dict |
| `ws1_auth_prep(self)` | 509–553 | Top-level auth orchestrator – returns `(headers, headers_v2)` supporting both OAuth and Basic auth |

### 4. Authentication-related `input_variables` (declare on the base class)

Move **only** the auth-related keys out of `WorkSpaceOneImporter.input_variables`
into `WorkSpaceOneImporterBase.input_variables`:

```text
ws1_api_url              (required – also used for every API call)
ws1_groupid              (required – also needed by every API call to resolve OG)
ws1_api_token
ws1_api_username
ws1_api_password
ws1_b64encoded_api_credentials
ws1_oauth_client_id
ws1_oauth_client_secret
ws1_oauth_token_url
ws1_oauth_renew_margin
ws1_oauth_keychain
ws1_oauth_token
ws1_oauth_renew_timestamp
```

### 5. SSL/TLS initialisation helper (new convenience method)

Extract the `macsesh` / `REQUESTS_CA_BUNDLE` runtime check block (currently
inside `ws1_import()`, lines 628–647) into a new method on the base class:

```python
def init_tls(self):
    """Initialise TLS certificate trust using REQUESTS_CA_BUNDLE env-var or macsesh."""
    ...
```

This way every future child processor can call `self.init_tls()` at the start
of its `main()`.

---

## Target File Layout After Refactoring

```
ws1-processors/
├── WorkSpaceOneImporter.py          # slimmed – subclasses WorkSpaceOneImporterBase
├── WorkSpaceOneImporter.recipe.yaml
├── ws1_lib/
│   ├── __init__.py                  # makes ws1_lib a package; re-exports the base class
│   └── WorkSpaceOneImporterBase.py  # NEW – all auth logic lives here
└── ...
```

---

## Detailed Instructions

### A. Create `ws1_lib/__init__.py`

```python
"""ws1_lib – shared library modules for WorkSpaceOne Autopkg processors."""
from .WorkSpaceOneImporterBase import WorkSpaceOneImporterBase  # noqa: F401

__all__ = ["WorkSpaceOneImporterBase"]
```

### B. Create `ws1_lib/WorkSpaceOneImporterBase.py`

1. **Shebang & licence header** – copy from `WorkSpaceOneImporter.py`, update
   the module docstring:
   ```
   """Base Autopkg Processor providing WS1 UEM REST API authentication (Basic & OAuth 2.0)."""
   ```

2. **Imports** – bring over only what the extracted code needs:
   `base64`, `os`, `subprocess`, `requests`, `datetime`/`timedelta`,
   `urlparse`, `autopkglib.Processor`, `autopkglib.ProcessorError`,
   and the conditional `macsesh` import block.

3. **Module-level helpers** – paste the four functions listed in §1 above,
   unchanged.

4. **Class definition**:
   ```python
   class WorkSpaceOneImporterBase(Processor):
       """Base processor that handles WS1 UEM authentication.

       Subclasses should call:
           self.init_tls()
           headers, headers_v2 = self.ws1_auth_prep()
       at the beginning of their main() to obtain authenticated HTTP headers.
       """

       description = __doc__

       input_variables = { ... }   # auth-related keys only (see §4)
       output_variables = {}       # base class produces no output on its own
   ```

5. **Methods** – paste in the four methods from §3 above, plus the new
   `init_tls()` from §5.  Keep them **byte-for-byte identical** to the
   originals except:
   - References to the removed module-level helpers should still work because
     they live in the same new module.
   - `ProcessorError` messages may optionally be prefixed with
     `"WorkSpaceOneImporterBase:"` instead of `"WorkSpaceOneImporter:"`.

6. **No `main()` override** – the base class deliberately does **not**
   implement `main()` (it inherits the abstract stub from `Processor`).
   This prevents it from being used as a standalone processor by accident.

### C. Modify `WorkSpaceOneImporter.py`

1. **Add import** at the top (after the existing `from autopkglib …` line):
   ```python
   # noinspection PyUnresolvedReferences
   from ws1_lib.WorkSpaceOneImporterBase import (  # noqa: E402
       WorkSpaceOneImporterBase,
       get_password_from_keychain,
       set_password_in_keychain,
       get_timestamp,
       is_url,
       HAS_MACSESH,
       HAS_REQUESTS_CA_BUNDLE,
   )
   ```
   > **Note:** The directory is named `ws1_lib` (with an underscore) so that it
   > is directly importable as a standard Python package without any special
   > import machinery. This works with both regular `import` and AutoPkg's
   > `imp.load_source`-based processor loader.

2. **Change class declaration**:
   ```python
   class WorkSpaceOneImporter(WorkSpaceOneImporterBase):
   ```

3. **Merge `input_variables`** – the child class should declare only its
   *own* input variables (everything that is NOT auth).  At class level, merge
   with the parent:
   ```python
   input_variables = {
       **WorkSpaceOneImporterBase.input_variables,
       # ... remaining non-auth input variables ...
   }
   ```

4. **Remove** the duplicated functions / methods that now live in the base class:
   - Module-level: `get_password_from_keychain`, `set_password_in_keychain`,
     `get_timestamp`, `is_url`, and the SSL/macsesh bootstrap block.
   - Instance methods: `oauth_keychain_init`, `get_oauth_token`,
     `get_oauth_headers`, `ws1_auth_prep`.

5. **Replace** the inline TLS block in `ws1_import()` (lines 628–647) with:
   ```python
   self.init_tls()
   ```

6. **Keep everything else unchanged** – `ws1_import`, `ws1_app_assignments`,
   `ws1_app_assign`, `ws1_app_versions_prune`, `get_smartgroup_id`,
   `git_run`, `git_lfs_pull`, `main`, etc.

---

## Validation Checklist

- [ ] `python -m py_compile ws1_lib/WorkSpaceOneImporterBase.py` passes.
- [ ] `python -m py_compile WorkSpaceOneImporter.py` passes.
- [ ] Black formatting: `black --check --line-length 120 ws1_lib/ WorkSpaceOneImporter.py`.
- [ ] Running an existing `.ws1.recipe.yaml` through `autopkg run -vvv`
      produces identical behaviour to the pre-refactor code.
- [ ] A trivial test subclass can do:
  ```python
  from ws1_lib.WorkSpaceOneImporterBase import WorkSpaceOneImporterBase
  class MyTestProcessor(WorkSpaceOneImporterBase):
      input_variables = {**WorkSpaceOneImporterBase.input_variables}
      output_variables = {}
      def main(self):
          self.init_tls()
          headers, headers_v2 = self.ws1_auth_prep()
          self.output(f"Auth headers obtained: {list(headers.keys())}")
  ```
  and successfully authenticate against the WS1 API.

---

## Future Roadmap (out of scope for this PR)

Once `WorkSpaceOneImporterBase` is stable, further processors can be split out:

| Future Processor | Inherits | Responsibility |
|---|---|---|
| `WorkSpaceOneUploader` | `WorkSpaceOneImporterBase` | Upload blob + create app object |
| `WorkSpaceOneAssigner` | `WorkSpaceOneImporterBase` | Manage app assignments (V1 & V2 APIs) |
| `WorkSpaceOnePruner`   | `WorkSpaceOneImporterBase` | Prune old app versions |

Each will inherit authentication for free and can be composed in recipe chains.

