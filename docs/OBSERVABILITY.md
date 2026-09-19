# Failure investigation

## Existing evidence

`evidence/local-traces.json` contains real OpenTelemetry spans generated locally by
`scripts/local_evidence.py`. Five failures are injected deliberately. Each has a
trace ID, span IDs, recorded events and an explicit root cause. These are **not AWS
traces**, and the HTTP 500 is a mocked transport response. Regenerate them with:

```bash
uv run python -m scripts.local_evidence
```

## Cloud trace workflow

Enable Transaction Search, resource tracing and service log destinations using the
AWS setup guide **before** running scenarios. Note the UTC time, runtime session
ID, test operation ID and returned trace ID. In CloudWatch GenAI observability,
open the session, select its trace, then the failed tool/model/policy span.

Our application spans are `support.request`, `gateway.tool`, `gateway.attempt` and
Lambda's `business.<tool>`. AWS and Strands add service/model spans. For a denied
refund, inspect the Gateway policy decision and prove no corresponding Lambda
invocation exists; an error message in the agent's answer alone is insufficient.

Lambda's X-Ray trace ID uses `1-xxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxx` format. The same
trace ID in W3C/OTel format is the concatenation of those two hexadecimal groups.
First confirm propagation in your deployment's service map. If AWS produces a
separate trace at a service boundary, correlate the Gateway request/tool/time with
Lambda's request ID and preserve **both** trace IDs; do not claim a connected trace
that was not observed.

## Failure matrix

| Failure | Reproduction | Relevant span/event | Root cause / expected behavior |
|---|---|---|---|
| Tool timeout | Test stack `FaultMode=timeout`, then check order | Gateway tool/attempt; Lambda service timeout; runtime `gateway_tool_error` or typed timeout | Injected 30s sleep exceeds Lambda's 10s timeout. Typed MCP/transport timeout retries up to three attempts; opaque Gateway errors fail without guessing from text. |
| Invalid parameters | Direct check_order with `order_id="../123"` | `business.check_order`, `INVALID_PARAMETERS`; gateway attempt | Backend identifier validation fails before storage access; not retryable. Missing/type-invalid schema fields may instead fail in Gateway before Lambda. |
| Wrong tool selection | Local scripted selection of get_customer when check_order was expected; live runner supplies expected tool for order prompt | `wrong_tool_selection` event includes actual and expected tool | Model/evaluation mismatch. It is a semantic error even if the tool's HTTP request succeeds. Investigate descriptions, prompt, prior messages and model choice. |
| HTTP 500 | Local typed HTTP 500 transport injection; cloud `FaultMode=backend_500` simulates an upstream failure envelope | `gateway.attempt`, `http_failure` with 500 locally; `UPSTREAM_500` and Lambda business span in cloud | Transient upstream service failure. Retry at most three times with exponential full jitter. A Lambda business envelope is **not** an actual HTTP 500; label evidence accordingly. |
| LLM loop | Deterministic local seventh model attempt; optionally ask a live agent to perform 20 sequential checks | `llm_loop` event on current request/model span; `MODEL_CALL_BUDGET_EXCEEDED` | Model repeats tool/model cycles; hook stops before the seventh model call. A live prompt is nondeterministic; only claim the loop scenario if the event exists. |

The default tool retry schedule has at most three attempts, with jitter in
`[0,0.25]` and `[0,0.5]` seconds before attempts 2 and 3. SDK calls also have bounded
standard retries. Invalid requests, business denials, authentication failures and
key conflicts are not retried. Whole agent turns are never automatically retried
by the invocation script.

## CloudWatch Logs Insights

Select the runtime log group (plus service groups as appropriate):

```text
fields @timestamp, event, trace_id, span_id, code, tool, attempt, @message
| filter event in ["tool_failure", "http_failure", "gateway_tool_error",
                  "request_failed", "wrong_tool_selection", "llm_loop"]
| sort @timestamp desc
| limit 100
```

For Lambda's `/aws/lambda/<stack>-tools` group:

```text
fields @timestamp, tool, error_code, request_id, trace_id, span_id, duration_ms
| filter event = "business_tool" and error_code != "OK"
| sort @timestamp desc
```

For a specific recorded trace:

```text
fields @timestamp, @message
| filter @message like /PASTE_ACTUAL_TRACE_ID/
| sort @timestamp asc
```

If the service wraps the JSON inside another `message` field, parse that field or
search `@message`; console log layouts can differ. Inspect actual Gateway vended-log
fields to filter policy `DENY` decisions. Enable a metric filter on handled Lambda
errors (`event=business_tool`, `error_code!=OK`) and on runtime `request_failed` or
`llm_loop`, then an alarm. The supplied Lambda `Errors` alarm detects unhandled
failures/timeouts, not successful invocations returning a business-error envelope.

## Test-stack fault drills

Use your deployment role to change the fault mode. The script refuses a prod stack.
Use your operator/evaluator role for the actual tool call:

```bash
uv run python -m scripts.fault_mode --stack "$STACK" --mode timeout
uv run python -m scripts.invoke --arn "$RUNTIME_ARN" --prompt 'Check order 123.'
uv run python -m scripts.fault_mode --stack "$STACK" --mode none

uv run python -m scripts.fault_mode --stack "$STACK" --mode backend_500
uv run python -m scripts.invoke --arn "$RUNTIME_ARN" --prompt 'Check order 123.'
uv run python -m scripts.fault_mode --stack "$STACK" --mode none
```

For lost-response recovery, set `lost_response`, send a $1 refund for order `retry`
using operation `lost-response-123`, then restore `none` and repeat the same request.
While the fault is enabled the call remains unconfirmed even though a receipt was
committed. After recovery the receipt must be returned and the balance must be
`199900` cents, proving only one $1 refund. Keep the receipt, before/after reads,
retry spans and Lambda logs. Do not reset or overwrite the table to make a test pass.

## Evidence record

For each failure, copy this record into the submission and fill it from the actual
trace. Never use placeholder/fabricated IDs as evidence:

```text
Scenario:
Environment (local-injected / AWS stack):
UTC timestamp and session ID:
Trace ID(s):
Failed span ID and name:
Parent span ID:
Error code / policy decision:
Root cause:
Retry count and final outcome:
Ledger side effects (if any):
Screenshot/log filename:
```
