# AWS evidence index

The sanitized live report `scenarios-1789823541.json` was produced by
`scripts.live_scenarios` against the `support-agent` test stack in `us-east-1` on
2026-09-19. Its top-level `status` is `PASS` and it records 16 scenarios:

- order and customer retrieval through MCP and through the Strands runtime;
- a $500 refund and its duplicate retry with the same receipt;
- an exactly $1,000 refund allowed by Cedar;
- $1,000.01 and $5,000 refunds denied by Gateway policy;
- invalid input, missing order, and conflicting idempotency-key failures;
- prompt-injection resistance with no $5,000 refund record;
- preference storage, asynchronous extraction, and retrieval in a second session.

The data is synthetic. Account and resource identifiers are deployment metadata,
not credentials. Add CloudWatch screenshots and the completed trace/span failure
matrix here after enabling AgentCore trace and application-log delivery.

Cloud fault drills recorded after observability was enabled:

- `failure-timeout.md`: Lambda timeout with Runtime trace ID and recovery record.
- `failure-upstream-500.md`: simulated upstream failure envelope with Runtime trace
  ID and an explicit note that it is not a real Gateway HTTP 500.
