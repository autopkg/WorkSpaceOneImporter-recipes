# Feature: Safeguard Slack Notifications for WorkSpaceOnePruner

## Summary

Added the ability to send Slack notifications when the pruning safeguard is triggered (when app versions are still assigned to devices). This provides a graceful alternative to hard-stopping the recipe execution.

## Problem Statement

Previously, when `WorkSpaceOnePruner` encountered versions still assigned to devices, it would immediately raise a `ProcessorError`, stopping recipe execution. This prevented:
- Slack notifications from being sent (via `WorkSpaceOneSlacker`)
- Any downstream processors from running
- Clear communication to teams about why pruning was halted

## Solution Overview

### 1. New Input Variable: `ws1_safeguard_halt_on_assigned`

**Location:** `WorkSpaceOnePruner.py`

- **Type:** String (converts to boolean)
- **Default:** `"True"` (maintains current behavior)
- **Values:**
  - `True` (default): Hard stop with `ProcessorError` (current behavior)
  - `False`: Gracefully exit and allow Slack notifications

When set to `False`, the pruner:
1. Detects the safeguard condition (version with active assignments)
2. Sets `ws1_slack_failure_message` with warning details
3. Sets `ws1_safeguard_triggered = True`
4. Creates a `ws1_pruner_summary_result` with safeguard details
5. Returns gracefully without raising an error
6. Allows downstream processors (like `WorkSpaceOneSlacker`) to run

### 2. Enhanced WorkSpaceOneSlacker

**Location:** `WorkSpaceOneSlacker.py`

#### New Input Variable: `ws1_safeguard_triggered`
- Detects when a safeguard was triggered
- Treats as warning (yellow color) rather than error (red color)

#### Improved Scenario Chain
Added new scenario for safeguard warnings:
- **Title:** `⚠️ Pruning safeguard — {app_name}`
- **Color:** `warning` (yellow)
- **Message:** Includes version, assigned device count, and action taken

#### Updated Variable Handling
- `safeguard_triggered` is now factored into error determination
- `has_error` is now False if only `ws1_slack_failure_message` is set AND `safeguard_triggered` is True
- This prevents safeguard warnings from being displayed as errors

### 3. Helper Method in WorkSpaceOnePruner

**Method:** `_create_safeguard_summary_result(app_name, version, assigned_count)`

Creates a structured summary result containing:
- `summary_text`: "Pruning safeguard triggered — version has active assignments"
- `report_fields`: name, version, assigned_device_count, action
- `data`: Structured data for reporting

This result is used by `WorkSpaceOneSlacker` to populate Slack messages.

## Usage Example

### Enable Slack Notifications on Safeguard

Create or modify a pruner recipe with:

```yaml
Process:
- Processor: com.github.codeskipper.OMNISSA-WorkSpaceOnePruner/WorkSpaceOnePruner
  Arguments:
    ws1_safeguard_halt_on_assigned: 'False'  # Enable graceful handling
    # ... other arguments ...

- Processor: com.github.codeskipper.OMNISSA-WorkSpaceOneSlacker/WorkSpaceOneSlacker
  Arguments:
    ws1_slack_webhook_url: '%WS1_SLACK_WEBHOOK_URL%'
```

See `Apparency.ws1-pruner-slack.recipe.yaml` for a complete example.

### Environment Variables

Can also be set via environment:
```bash
export AUTOPKG_ws1_safeguard_halt_on_assigned=False
export AUTOPKG_ws1_slack_webhook_url=https://hooks.slack.com/...
autopkg run MyApp.ws1-pruner.recipe.yaml
```

## Code Changes

### WorkSpaceOnePruner.py

1. **Added input variable:**
   ```python
   "ws1_safeguard_halt_on_assigned": {
       "required": False,
       "default": "True",
       "description": "Whether to halt (raise ProcessorError) when a safeguard detects versions..."
   }
   ```

2. **Updated safeguard logic in `ws1_app_versions_prune()` method:**
   - Checks `ws1_safeguard_halt_on_assigned` setting
   - If True: raises `ProcessorError` (current behavior)
   - If False: gracefully sets environment variables and returns

3. **Added helper method `_create_safeguard_summary_result()`:**
   - Creates structured summary for Slack integration

### WorkSpaceOneSlacker.py

1. **Added input variable:**
   ```python
   "ws1_safeguard_triggered": {
       "required": False,
       "description": "Set to True if a pruning safeguard was triggered..."
   }
   ```

2. **Updated `_gather_state_from_env()` method:**
   - Now extracts `ws1_safeguard_triggered` from environment

3. **Updated `main()` method:**
   - Added `safeguard_triggered` variable extraction
   - Modified `has_error` logic to exclude safeguard-only cases
   - Added new scenario branch for safeguard warnings
   - Updated color determination to use `warning` for safeguard cases

## Backward Compatibility

✅ **Fully backward compatible**

- Default behavior unchanged (`ws1_safeguard_halt_on_assigned` defaults to `"True"`)
- Existing recipes continue to work as before
- No breaking changes to existing processors
- Graceful handling of safeguard only activates when explicitly enabled

## Testing

### Test Case 1: Default Behavior (Hard Stop)
```bash
autopkg run -vvvv Apparency.ws1-pruner.recipe.yaml
# Expected: ProcessorError when version has active assignments
```

### Test Case 2: Graceful with Slack Notification
```bash
export AUTOPKG_ws1_safeguard_halt_on_assigned=False
export AUTOPKG_ws1_slack_webhook_url=<your-webhook>
autopkg run -vvvv Apparency.ws1-pruner.recipe.yaml
# Expected: Slack notification sent, no error raised
```

### Test Case 3: Environment Variable Override
```bash
autopkg run -vvvv -k ws1_safeguard_halt_on_assigned=False Apparency.ws1-pruner.recipe.yaml
# Expected: Same as Test Case 2
```

## Slack Notification Example

### When Safeguard is Triggered (with ws1_safeguard_halt_on_assigned = False)

**Title:** ⚠️ Pruning safeguard — Firefox

**Color:** Yellow (warning)

**Message:**
```
Pruning was skipped due to active device assignments.
Assigned device count: 5
Version: 121.0.1
Action: Skipped — cannot delete version with active assignments
```

## Files Modified

1. **WorkSpaceOnePruner.py**
   - Added input variable
   - Updated safeguard logic
   - Added helper method

2. **WorkSpaceOneSlacker.py**
   - Added input variable
   - Updated scenario chain
   - Updated color logic
   - Updated error handling

## Files Created

1. **Apparency.ws1-pruner-slack.recipe.yaml**
   - Example recipe showing new feature usage

## Integration with Cloud-AutoPkg-Runner (CAR)

This enhancement maintains CAR compatibility:
- Input variables follow standard naming conventions
- No breaking changes to processor signatures
- Environment variable support via `AUTOPKG_*` prefix

## Future Enhancements

Potential future improvements:
1. Configurable Slack message templates
2. Automatic retry logic for assigned versions
3. Device/assignment details in Slack message
4. Integration with device lifecycle management to auto-unassign

## Documentation

See AGENTS.md for:
- Code style guidelines (Black, isort, flake8)
- Pre-commit hooks setup
- Dependency installation
- Recipe validation

## Version

- **Date Added:** June 24, 2026
- **Processor:** WorkSpaceOnePruner v1.x + WorkSpaceOneSlacker v1.x
- **AutoPkg Python:** 3.10+

---

**Related Issues/PRs:** None yet
**Ticket:** Feature request - Safeguard Slack notifications
**Author:** GitHub Copilot

