#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Martinus Verburg
"""Scaffold WS1 YAML recipes; never execute recipes or overwrite existing files."""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required. Use an interpreter containing it, or install requirements-dev.txt in a venv.")

KINDS = {"importer": "ws1", "assigner": "ws1-assigner", "pruner": "ws1-pruner"}
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", help="Compact filename/identifier suffix, e.g. PolyStudio")
    parser.add_argument("--name", required=True, help="Vendor-prefixed marketing name, including spaces")
    parser.add_argument("--identifier-prefix", required=True, help="Recipe namespace, e.g. com.github.example")
    parser.add_argument(
        "--processor-prefix", default="com.github.codeskipper", help="Verified shared processor namespace"
    )
    parser.add_argument("--parent", help="Munki parent identifier; required when generating an importer")
    parser.add_argument("--only", choices=tuple(KINDS), help="Generate just this type (default: all three)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.app):
        parser.error("app must be a compact filename/identifier suffix, not a path")
    for value in (args.identifier_prefix, args.processor_prefix):
        if not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+", value):
            parser.error("namespace prefixes must be dotted identifiers")
    if not args.name.strip() or any(c in args.name for c in ("\n", "\r", "%")):
        parser.error("name must be a nonempty, single-line literal without AutoPkg substitution markers")
    kinds = [args.only] if args.only else list(KINDS)
    if "importer" in kinds and (not args.parent or not args.parent.strip()):
        parser.error("--parent is required for importer generation")

    # Validate the whole set before writing anything, including types not selected
    # in this invocation, to avoid silently mixing names across staged generation.
    for suffix in KINDS.values():
        path = args.out / f"{args.app}.{suffix}.recipe.yaml"
        if path.exists():
            try:
                existing = yaml.safe_load(path.read_text(encoding="utf-8"))
                name = existing["Input"]["NAME"]
                identifier = existing["Identifier"]
            except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
                parser.error(f"cannot verify existing recipe {path}: {exc}")
            if name != args.name:
                parser.error(f"existing NAME in {path} differs; review naming before generating related recipes")
            if identifier != f"{args.identifier_prefix}.{suffix}.{args.app}":
                parser.error(f"existing Identifier in {path} differs; review the recipe namespace")
            if suffix == "ws1" and args.parent and existing.get("ParentRecipe") != args.parent:
                parser.error(f"existing ParentRecipe in {path} differs; review the parent before proceeding")

    values = {
        "APP": args.app,
        "NAME": args.name,
        "PREFIX": args.identifier_prefix,
        "PROCESSOR_PREFIX": args.processor_prefix,
        "PARENT": args.parent or "",
    }
    pending = []
    for kind in kinds:
        suffix = KINDS[kind]
        path = args.out / f"{args.app}.{suffix}.recipe.yaml"
        if path.exists():
            print(f"Skipped existing: {path}")
            continue
        template = (TEMPLATES / f"{suffix}.recipe.yaml.in").read_text(encoding="utf-8")
        # Each token occupies an entire YAML scalar. JSON quoting safely handles
        # colons, quotes, backslashes, ampersands, and Unicode in marketing names.
        tokens = dict(values)
        tokens["IDENTIFIER"] = f"{args.identifier_prefix}.{suffix}.{args.app}"
        tokens["PROCESSOR"] = f"{args.processor_prefix}.OMNISSA-WorkSpaceOne{kind.title()}/WorkSpaceOne{kind.title()}"
        tokens["DESCRIPTION"] = {
            "importer": f"Downloads {args.name} using its Munki parent and imports it into Workspace ONE.",
            "assigner": f"Assigns {args.name} to smart groups in Workspace ONE.",
            "pruner": f"Prunes old versions of {args.name} from Workspace ONE according to configured retention.",
        }[kind]
        content = re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: json.dumps(tokens[m[1]], ensure_ascii=False), template)
        yaml.safe_load(content)
        pending.append((path, content))
    args.out.mkdir(parents=True, exist_ok=True)
    for path, content in pending:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
        print(f"Created: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
