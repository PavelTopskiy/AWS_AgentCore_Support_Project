# Invalid-parameter drill

- Environment: AWS test stack `support-agent`, `us-east-1`
- Invocation: direct IAM-signed MCP call to `SupportTools___check_order`
- MCP tool-use ID: `8138cb81-d9bf-4324-a916-a5a1a80c40f3`
- Result: `INVALID_PARAMETERS`, `retryable=false`
- Lambda request ID: `776ceffe-09fe-48f7-a66b-905d66e3e0ac`
- X-Ray trace ID: `1-6aaef813-7d9303ec20a4d9db2f255a2a`
- OTel/W3C trace ID: `6aaef8137d9303ec20a4d9db2f255a2a`
- Lambda span ID: `f6c81b86a5243938`
- Duration: 0 ms
- Root cause: `order_id="../bad"` contains forbidden path characters and was
  rejected by domain validation before any DynamoDB access
- Retry decision: non-retryable

The identifiers above were correlated from the Lambda `business_tool` event in
`/aws/lambda/support-agent-tools`. Use either trace-ID representation in CloudWatch,
depending on whether the selected view expects X-Ray or W3C formatting.
