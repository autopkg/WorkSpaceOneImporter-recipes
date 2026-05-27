#!/usr/bin/env python3
"""
035. cleanup_recipe_input_vars.py

Batch-removes orphaned assignment-related input variables from *.ws1.recipe.yaml recipes.
These variables have been moved to the separate WorkSpaceOneAssigner processor and
*.ws1-assigner.recipe.yaml recipes.

Removes from Input section:
  - WS1_SMART_GROUP_NAME
  - WS1_PUSH_MODE
  - ws1_app_assignments (entire complex block)

Removes from Process Arguments section:
  - ws1_smart_group_name
  - ws1_push_mode

Usage:
  python3 cleanup_recipe_input_vars.py
"""

import glob
import os
import re
import sys

RECIPES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "ws1-recipes")

# Keys to remove from Input section (simple single-line keys)
INPUT_KEYS_TO_REMOVE = [
    "WS1_SMART_GROUP_NAME",
    "WS1_PUSH_MODE",
]

# Complex key that spans multiple lines (ws1_app_assignments block)
COMPLEX_INPUT_KEY = "ws1_app_assignments"

# Keys to remove from Process Arguments section
ARGUMENT_KEYS_TO_REMOVE = [
    "ws1_smart_group_name",
    "ws1_push_mode",
]


def remove_lines_from_recipe(filepath):
    """Remove assignment-related variables from a single recipe file.

    Returns a tuple (modified: bool, details: list[str]) describing changes made.
    """
    with open(filepath, "r") as f:
        lines = f.readlines()

    new_lines = []
    changes = []
    i = 0
    in_ws1_app_assignments_block = False
    ws1_app_assignments_indent = 0
    # removed_comment_line = False

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip("\n")

        # --- Handle ws1_app_assignments multi-line block ---
        if in_ws1_app_assignments_block:
            # The block continues until we hit a line at the same or lesser indent level
            # that isn't blank and isn't a continuation of the nested structure
            if stripped == "":
                # blank line might end the block or be internal; peek ahead
                # If next non-blank line is at base indent or less, block is over
                j = i + 1
                while j < len(lines) and lines[j].strip() == "":
                    j += 1
                if j >= len(lines):
                    # EOF — skip remaining blanks
                    in_ws1_app_assignments_block = False
                    i = j
                    continue
                next_non_blank = lines[j]
                next_indent = len(next_non_blank) - len(next_non_blank.lstrip())
                if next_indent <= ws1_app_assignments_indent:
                    # Block ended, skip blank lines between block and next section
                    in_ws1_app_assignments_block = False
                    i = j
                    continue
                else:
                    # Internal blank line in block, skip it
                    i += 1
                    continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent > ws1_app_assignments_indent:
                # Still inside the block
                i += 1
                continue
            else:
                # Block has ended
                in_ws1_app_assignments_block = False
                # Don't skip this line, process it normally
                # fall through to normal processing below

        # --- Check for comment line preceding ws1_app_assignments ---
        # e.g. "  # WS1 - testing new AppsV2 assignments feature"
        if (
            not in_ws1_app_assignments_block
            and stripped.lstrip().startswith("#")
            and "assignment" in stripped.lower()
            and i + 1 < len(lines)
        ):
            # Peek at next non-blank line to see if it's ws1_app_assignments
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            if j < len(lines) and lines[j].strip().startswith(f"{COMPLEX_INPUT_KEY}:"):
                # This comment line relates to ws1_app_assignments — remove it
                changes.append(f"  Removed comment: {stripped.strip()}")
                # removed_comment_line = True
                i += 1
                continue

        # --- Check for ws1_app_assignments key start ---
        if stripped.lstrip().startswith(f"{COMPLEX_INPUT_KEY}:"):
            ws1_app_assignments_indent = len(line) - len(line.lstrip())
            in_ws1_app_assignments_block = True
            changes.append(f"  Removed Input key: {COMPLEX_INPUT_KEY} (multi-line block)")
            i += 1
            continue

        # --- Check for simple Input keys to remove ---
        removed = False
        for key in INPUT_KEYS_TO_REMOVE:
            if re.match(rf"^\s+{re.escape(key)}\s*:", stripped):
                changes.append(f"  Removed Input key: {key}")
                removed = True
                break
        if removed:
            i += 1
            continue

        # --- Check for Process Argument keys to remove ---
        for key in ARGUMENT_KEYS_TO_REMOVE:
            if re.match(rf"^\s+{re.escape(key)}\s*:", stripped):
                changes.append(f"  Removed Argument: {key}")
                removed = True
                break
        if removed:
            i += 1
            continue

        # --- Keep the line ---
        new_lines.append(line)
        i += 1

    # Remove any trailing blank lines that appear excessive (more than 1 at end)
    while len(new_lines) > 1 and new_lines[-1].strip() == "" and new_lines[-2].strip() == "":
        new_lines.pop()

    # Ensure file ends with a single newline
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    modified = len(changes) > 0
    if modified:
        with open(filepath, "w") as f:
            f.writelines(new_lines)

    return modified, changes


def main():
    recipes_dir = os.path.normpath(RECIPES_DIR)
    pattern = os.path.join(recipes_dir, "*.ws1.recipe.yaml")
    recipe_files = sorted(glob.glob(pattern))

    if not recipe_files:
        print(f"ERROR: No *.ws1.recipe.yaml files found in {recipes_dir}")
        sys.exit(1)

    print(f"Found {len(recipe_files)} recipe(s) to process in:\n  {recipes_dir}\n")

    total_modified = 0
    total_skipped = 0

    for filepath in recipe_files:
        filename = os.path.basename(filepath)
        modified, changes = remove_lines_from_recipe(filepath)
        if modified:
            total_modified += 1
            print(f"MODIFIED: {filename}")
            for change in changes:
                print(change)
            print()
        else:
            total_skipped += 1
            print(f"SKIPPED (already clean): {filename}")

    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {total_modified} modified, {total_skipped} already clean, {len(recipe_files)} total")
    print(f"{'=' * 60}")

    if total_modified > 0:
        print("\nNext steps:")
        print("  1. Review changes with: git diff ws1-recipes/")
        print("  2. Validate with: pre-commit run check-autopkg-recipes --all-files")


if __name__ == "__main__":
    main()
