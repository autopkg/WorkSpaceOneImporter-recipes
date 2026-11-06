import glob
import os
import sys

import yaml

os.chdir("/Users/MAVE/dev/codeskipper/WorkSpaceOneImporter-recipes")
errors = 0
files = sorted(glob.glob("ws1-recipes/*.ws1-assigner.recipe.yaml"))
print(f"Validating {len(files)} assigner recipes...")
for f in files:
    try:
        with open(f) as fh:
            data = yaml.safe_load(fh)
        assert "Identifier" in data, "Missing Identifier"
        assert "Input" in data, "Missing Input"
        assert "Process" in data, "Missing Process"
        assert "NAME" in data["Input"], "Missing NAME in Input"
        assert "ParentRecipe" not in data, "Should NOT have ParentRecipe"
        assert (
            data["Process"][0]["Processor"]
            == "com.github.codeskipper.OMNISSA-WorkSpaceOneAssigner/WorkSpaceOneAssigner"
        ), "Wrong Processor"
        print(f"  OK {os.path.basename(f)}")
    except Exception as e:
        print(f"  FAIL {os.path.basename(f)}: {e}")
        errors += 1
print(f"\nResult: {len(files)} files validated, {errors} errors.")
sys.exit(errors)
