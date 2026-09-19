# Tool timeout drill

- Environment: AWS test stack `support-agent`, `us-east-1`
- Runtime session ID: `c15f4679-dbd8-4498-bd00-54fefd0e8074`
- Runtime trace ID: `6aaef738158a78ff779cbec510e8d496`
- Tool: `check_order`
- Result: agent returned a controlled internal-error response
- Root cause: test-only `FaultMode=timeout` injected a 30-second backend delay,
  exceeding the Lambda function's 10-second timeout
- Recovery: CloudFormation parameter restored to `FaultMode=none`

Use the trace ID in CloudWatch Transaction Search and attach a screenshot showing
the failed tool/Lambda span and its duration. This file records genuine AWS execution,
but the screenshot is still required to preserve the service-generated span ID.
