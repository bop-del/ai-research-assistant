## Context

`send_notification` in `src/pipeline.py` currently builds a message string from only `processed` and `failed` fields of `PipelineResult`, then sends it via `osascript`. The function signature already receives the full `PipelineResult` — all data is available, just unused.

## Goals / Non-Goals

**Goals:**
- Make every run outcome distinguishable from the notification alone
- Keep the notification concise (macOS notifications truncate long messages)

**Non-Goals:**
- Changing the notification mechanism (osascript is fine for this project)
- Adding notification preferences or configuration
- Changing how `PipelineResult` is populated upstream

## Decisions

### Decision 1: Message branching by run type

Use a simple if/elif chain to handle the four distinct scenarios (dry run, empty, failures, success) rather than building a message incrementally. This keeps each case readable and avoids string-building complexity.

### Decision 2: Keep title constant

Title stays "Content Pipeline" for all cases. The message body carries the distinguishing information. This keeps notifications visually grouped in macOS Notification Center.
