## 1. Rewrite send_notification

- [x] 1.1 Add dry-run branch: when `skipped > 0`, message = "Dry run: {skipped} items previewed"
- [x] 1.2 Add empty-run branch: when `processed == 0` and `failed == 0` and `skipped == 0`, message = "No items to process"
- [x] 1.3 Add failure branch: include processed + failed counts, append first failure title
- [x] 1.4 Add success branch: "Processed {n} items", append "(X retried)" when retried > 0

## 2. Verify

- [x] 2.1 Run existing tests to confirm no regressions
- [x] 2.2 Manually verify message strings match spec scenarios
