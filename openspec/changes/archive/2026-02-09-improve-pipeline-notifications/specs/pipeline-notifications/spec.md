## ADDED Requirements

### Requirement: Successful run notification
The notification SHALL report all non-zero result counts (processed, retried) in a single message.

#### Scenario: Normal run with retries
- **WHEN** pipeline completes with processed=5, retried=2, failed=0
- **THEN** notification message includes "Processed 5 items (2 retried)"

#### Scenario: Normal run without retries
- **WHEN** pipeline completes with processed=3, retried=0, failed=0
- **THEN** notification message reads "Processed 3 items"

### Requirement: Failed run notification
The notification SHALL report both processed and failed counts, plus the first failure title.

#### Scenario: Run with failures
- **WHEN** pipeline completes with processed=3, failed=2
- **THEN** notification message reads "Processed 3, Failed 2"
- **AND** the first failure title (truncated to 30 chars) is appended

### Requirement: Empty run notification
The notification SHALL distinguish between "nothing to process" and a real zero-result run.

#### Scenario: No items available
- **WHEN** pipeline completes with processed=0, failed=0, skipped=0
- **THEN** notification message reads "No items to process"

### Requirement: Dry run notification
The notification SHALL clearly label dry runs so they aren't confused with real runs.

#### Scenario: Dry run
- **WHEN** pipeline completes with skipped > 0 (dry run mode)
- **THEN** notification message reads "Dry run: {skipped} items previewed"
