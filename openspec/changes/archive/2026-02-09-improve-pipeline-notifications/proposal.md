## Why

The pipeline's macOS notification only reports `processed` and `failed` counts, ignoring retried successes, dry-run skips, and the empty-run edge case. This makes it hard to tell at a glance whether a run actually did anything meaningful or just had nothing to do.

## What Changes

- Notification message includes retried and skipped counts when non-zero
- Empty runs (0 processed, 0 failed) get a distinct "No items to process" message
- Dry runs are explicitly labeled so they aren't confused with empty real runs

## Capabilities

### New Capabilities
- `pipeline-notifications`: Richer, context-aware macOS notification messages from pipeline runs

### Modified Capabilities
<!-- none — this is a new capability carved out of the existing monolithic pipeline -->

## Impact

- `src/pipeline.py`: `send_notification()` function rewritten (~15 lines)
- No API changes, no new dependencies, no database changes
