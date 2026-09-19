# Simulated upstream failure drill

- Environment: AWS test stack `support-agent`, `us-east-1`
- Runtime session ID: `290eca06-425a-4262-aa70-46ae4d3ece30`
- Runtime trace ID: `6aaef7bc79ce644577fbd0ac30bc6abd`
- Tool: `check_order`
- Result: agent returned a controlled retryable `UPSTREAM_500` response
- Root cause: test-only `FaultMode=backend_500` returned a simulated upstream
  failure business envelope from the Lambda tool
- Recovery: CloudFormation parameter restored to `FaultMode=none`

This is a genuine AWS tool invocation and trace, but the injected business envelope
is not an actual HTTP 500 emitted by the Gateway. Use the trace ID in CloudWatch and
attach a screenshot showing the tool and business spans. Keep this distinction in
the submitted failure matrix.
