#!/usr/bin/env python3
"""Offline structural recipe lint; not AutoPkg runtime or deployment validation."""
import argparse
import plistlib
import re
import sys
from pathlib import Path


def load_recipe(path):
    if path.suffix not in (".yaml", ".yml"):
        with path.open("rb") as stream:
            return plistlib.load(stream)
    try:
        import yaml
    except ImportError as exc:
        raise ValueError("YAML lint requires PyYAML in the selected interpreter") from exc

    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in result:
                raise ValueError(f"duplicate YAML key {key!r}")
            result[key] = loader.construct_object(value_node, deep=deep)
        return result

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)


def lint(recipe, ws1=False):
    errors, warnings = [], []
    if not isinstance(recipe, dict):
        return ["recipe must be a mapping"], warnings
    if not isinstance(recipe.get("Identifier"), str) or not recipe["Identifier"].strip():
        errors.append("Identifier must be a nonempty string")
    minimum = recipe.get("MinimumVersion")
    if minimum is not None and not isinstance(minimum, str):
        errors.append("MinimumVersion must be a string")
    parent = recipe.get("ParentRecipe")
    if parent is not None and (not isinstance(parent, str) or not parent.strip()):
        errors.append("ParentRecipe must be a nonempty string")
    inputs = recipe.get("Input", {})
    process = recipe.get("Process", [])
    if not isinstance(inputs, dict):
        errors.append("Input must be a mapping")
        inputs = {}
    if not isinstance(process, list):
        errors.append("Process must be a list")
        process = []
    if "Process" not in recipe and not parent:
        warnings.append("no Process or ParentRecipe; confirm this is a processor registration stub")

    def walk(value, location):
        if value is None:
            errors.append(f"{location}: null values are not portable to plist")
        elif isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    errors.append(f"{location}: dictionary keys must be strings")
                walk(child, f"{location}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{location}[{index}]")
        elif isinstance(value, str) and re.search(r"\{\{[A-Z_]+\}\}|@[A-Z_]+@", value):
            errors.append(f"{location}: unresolved template token")

    walk(recipe, "recipe")
    pkginfo = inputs.get("pkginfo", {})
    if isinstance(pkginfo, dict):
        for key in ("version", "minimum_os_version", "maximum_os_version"):
            if key in pkginfo and not isinstance(pkginfo[key], str):
                errors.append(f"pkginfo.{key} must be a string")
    for index, step in enumerate(process):
        if not isinstance(step, dict):
            errors.append(f"Process[{index}] must be a mapping")
            continue
        if not isinstance(step.get("Processor"), str) or not step["Processor"].strip():
            errors.append(f"Process[{index}].Processor must be a nonempty string")
        arguments = step.get("Arguments", {})
        if not isinstance(arguments, dict):
            errors.append(f"Process[{index}].Arguments must be a mapping")
            continue
        if ws1:
            for key, value in arguments.items():
                if isinstance(key, str) and key.startswith("ws1_"):
                    if key == "ws1_app_assignments":
                        if not isinstance(value, list):
                            errors.append("ws1_app_assignments must be a list, not a substitution string")
                    elif not isinstance(value, str):
                        errors.append(f"{key} must be a string for this WS1 processor family")
                    if isinstance(value, str):
                        for var in re.findall(r"%([A-Z][A-Z0-9_]*)%", value):
                            if var not in inputs:
                                warnings.append(f"{var} is not defined locally; verify inheritance or override")
    if ws1:
        name = inputs.get("NAME")
        if not isinstance(name, str) or not name.strip():
            errors.append("WS1 recipes must explicitly set a human-readable Input.NAME")
        for key in (
            "WS1_APP_VERSIONS_TO_KEEP",
            "ws1_app_versions_to_keep",
            "WS1_APP_VERSIONS_PRUNE",
            "ws1_app_versions_prune",
            "WS1_SAFEGUARD_HALT_ON_ASSIGNED",
            "ws1_safeguard_halt_on_assigned",
        ):
            if key in inputs and not isinstance(inputs[key], str):
                errors.append(f"{key} must be a string")
        if isinstance(pkginfo, dict) and "name" in pkginfo and pkginfo["name"] not in ("%NAME%", name):
            warnings.append("pkginfo.name differs from Input.NAME; check Hub naming")
    return errors, warnings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ws1", action="store_true", help="Also enforce reference WS1 processor conventions")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)
    failed = False
    for path in args.files:
        try:
            errors, warnings = lint(load_recipe(path), args.ws1)
        except Exception as exc:
            errors, warnings = [f"cannot parse recipe: {exc}"], []
        for message in warnings:
            print(f"{path}: warning: {message}")
        for message in errors:
            print(f"{path}: error: {message}")
        if not errors:
            print(f"{path}: structural lint passed")
        failed |= bool(errors)
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
