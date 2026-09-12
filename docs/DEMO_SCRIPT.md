# Five-minute Demo

1. Start the API/frontend locally, or use Docker only after `DOCKER_VERIFICATION.md` passes.
2. Select the e-commerce repository and click **SYNC**. Point out the real snapshot and commit; do not imply indexing before sync.
3. Enter: **Add RETURNED as an order status after shipment and allow refunds after successful warehouse inspection.**
4. Expand **Optional proposed Git diff** and paste a patch adding `OrderStatus.RETURNED`, or run without a patch to demonstrate pre-implementation discovery.
5. Click **SIMULATE CHANGE**. Show the measured impact counts and deterministic GO/REVIEW/BLOCK decision.
6. Open **Impact**, select a node, and show the reason path and evidence strength.
7. Open **Risks** and distinguish severity, score, confidence, support status, and evidence strength. Record Confirm/Reject/Not Relevant feedback.
8. Open **Evidence** and inspect file, lines, snippet, snapshot, commit, hash, quality, and validity.
9. Review missing state-transition, authorization, integration-failure, rollback, idempotency, and consistency scenarios.
10. Open **Decision**, review required actions, and export Markdown or JSON.

Use actual displayed counts. Do not promise fixed numbers or generalize fixture benchmark measurements.
