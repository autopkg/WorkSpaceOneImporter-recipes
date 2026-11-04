#!/usr/local/autopkg/python
"""Quick smoke test for the WorkSpaceOneImporterBase refactoring."""

import os
import sys

# Run from ws1-processors directory (parent of ws1_lib)
ws1_processors_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ws1_processors_dir)
sys.path.insert(0, ws1_processors_dir)
sys.path.insert(0, "/Library/AutoPkg")

# Test 1: Import the base module
from ws1_lib.WorkSpaceOneImporterBase import (  # noqa: E402, F401
    HAS_MACSESH,
    HAS_REQUESTS_CA_BUNDLE,
    WorkSpaceOneImporterBase,
    get_password_from_keychain,
    get_timestamp,
    is_url,
    set_password_in_keychain,
)

print("1. Base class imported OK:", WorkSpaceOneImporterBase)
print("   is_url('https://example.com'):", is_url("https://example.com"))
print("   is_url(None):", is_url(None))
print("   HAS_MACSESH:", HAS_MACSESH)
print("   HAS_REQUESTS_CA_BUNDLE:", HAS_REQUESTS_CA_BUNDLE)

# Test 2: Verify base class has the expected auth input_variables
auth_keys = [
    "ws1_api_url",
    "ws1_groupid",
    "ws1_api_token",
    "ws1_api_username",
    "ws1_api_password",
    "ws1_b64encoded_api_credentials",
    "ws1_oauth_client_id",
    "ws1_oauth_client_secret",
    "ws1_oauth_token_url",
    "ws1_oauth_renew_margin",
    "ws1_oauth_keychain",
    "ws1_oauth_token",
    "ws1_oauth_renew_timestamp",
]
for key in auth_keys:
    assert key in WorkSpaceOneImporterBase.input_variables, f"Missing: {key}"
print(f"2. All {len(auth_keys)} auth input_variables present in base class")

# Test 3: Verify base class has the expected methods
for method in ["init_tls", "oauth_keychain_init", "get_oauth_token", "get_oauth_headers", "ws1_auth_prep"]:
    assert hasattr(WorkSpaceOneImporterBase, method), f"Missing method: {method}"
print("3. All 5 auth methods present in base class")

# Test 4: Import the child processor
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("WorkSpaceOneImporter", "WorkSpaceOneImporter.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
WSI = mod.WorkSpaceOneImporter
print("4. Child class imported OK:", WSI)
print("   Child extends base:", issubclass(WSI, WorkSpaceOneImporterBase))

# Test 5: Verify child class has merged input_variables (both auth and non-auth)
assert "ws1_api_url" in WSI.input_variables, "Missing inherited key ws1_api_url"
assert "ws1_oauth_client_id" in WSI.input_variables, "Missing inherited key ws1_oauth_client_id"
assert "ws1_console_url" in WSI.input_variables, "Missing child key ws1_console_url"
assert "ws1_force_import" in WSI.input_variables, "Missing child key ws1_force_import"
assert "ws1_app_versions_prune" in WSI.input_variables, "Missing child key ws1_app_versions_prune"
print(f"5. Child input_variables correctly merged: {len(WSI.input_variables)} total keys")

# Test 6: Verify child class does NOT re-declare auth methods (inherits them)
assert "ws1_auth_prep" not in WSI.__dict__, "ws1_auth_prep should NOT be in child __dict__"
assert "init_tls" not in WSI.__dict__, "init_tls should NOT be in child __dict__"
print("6. Auth methods correctly inherited (not re-declared in child)")

# Test 7: Verify child class still has its own methods
for method in [
    "ws1_import",
    "ws1_app_assignments",
    "ws1_app_assign",
    "ws1_app_versions_prune",
    "get_smartgroup_id",
    "git_run",
    "git_lfs_pull",
    "main",
    "ws1_app_assignment_conf",
]:
    assert hasattr(WSI, method), f"Missing method in child: {method}"
print("7. All business-logic methods present in child class")

print()
print("ALL CHECKS PASSED")
