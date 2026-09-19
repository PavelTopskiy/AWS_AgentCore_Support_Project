# Security and scope

## Authority

The LLM proposes tool calls; it never authorizes them. Gateway authenticates SigV4
with `AWS_IAM`, then evaluates Cedar in `ENFORCE`. The refund permit uses
`amount_cents <= 100000`, and an explicit forbid rejects larger amounts. The Lambda
backend repeats the limit and strictly validates types, positive amounts, allowed
fields, customer ownership and available balance. Floating-point values, booleans,
negative amounts, unsupported currencies and extra arguments do not create refunds.

The Cedar principal is intentionally generic **within this IAM-protected gateway**.
Only IAM principals with the specific Gateway ARN grant may call it. The ordinary
operator policy grants Runtime invocation only; a separate evaluator may receive a
temporary Gateway grant for deterministic policy tests. Do not use `NONE` or
`AUTHENTICATE_ONLY` inbound authorization with this permission design.

The hook binds the caller's `operation_id` to every proposed refund. It does not
filter an over-limit amount before Gateway: a proposed $5,000 reaches Cedar as
`500000` cents and is denied. A model may instead refuse in text; that alone is not
policy evidence. The live suite also issues the malicious MCP call directly.

## IAM separation

| Role | Allowed access |
|---|---|
| Operator | Invoke only this Runtime and its DEFAULT endpoint |
| Runtime | Invoke this Gateway, use this Memory, invoke one model, pull one ECR repository, emit telemetry |
| Gateway | Invoke only the business Lambda; read/evaluate its Policy Engine |
| Lambda | Get/put/update only this DynamoDB table and configured customer key prefix; emit logs/traces |
| Deployer | Provision/update this stack and pass its roles; never used as the runtime identity |
| Evaluator | Temporary test-only access to Gateway, stack outputs and read-only ledger/Memory evidence |

`Resource: "*"` is limited to APIs without resource-level support: ECR login,
telemetry submission/sampling, log-group discovery and namespace-constrained metric
submission. Runtime log writes are restricted to the AgentCore runtime log prefix.
Service-role trusts use the service principal, same-account condition and matching
AgentCore resource family. The Lambda role has a `dynamodb:LeadingKeys` customer
condition; transaction members require `PutItem`/`UpdateItem`, not a nonexistent
`dynamodb:TransactWriteItems` IAM grant.

Policy evaluation requires `GetPolicyEngine`, `AuthorizeAction` and
`PartiallyAuthorizeActions`. The engine ARN is exact; evaluation's Gateway resource
uses this stack's unique Gateway-name prefix plus the generated-ID suffix wildcard
to avoid a CloudFormation role/Gateway dependency cycle. It does not grant access
to all gateways. See [AWS policy permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-permissions.html).

The refund policy permits only positive amounts up to 100000 cents. Requests above
that limit have no matching permit and are denied by Cedar's default-deny semantics.
This authorization happens at the Gateway and cannot be changed by prompt text.

SSO locally and IAM execution roles in AWS supply short-lived credentials. No
OAuth secret is needed because all integrations are AWS-native. For a future
external CRM/payment service, configure AgentCore Identity OAuth credentials or a
scoped Secrets Manager secret; never place bearer tokens in prompts or environment
files committed to Git.

## Explicit limitations

- All operators of this deployment act for **one configured customer**, including
  shared preference memory. For a multi-customer service, add a verified JWT/identity
  boundary, propagate the verified subject through Gateway, and enforce ownership
  in the backend. A user-supplied `customer_id` is not an identity mechanism.
- The refund result says `SIMULATED_COMPLETED`. Integrating a real payment service
  requires its own durable idempotency key, an outbox/state machine and reconciliation
  for ambiguous provider results. A database transaction cannot atomically commit
  an unrelated external payment.
- The cap applies per refund operation; it is not a daily spending limit. A model
  cannot split one invocation into new keys. Authorized callers can create new
  operations, still bounded by the order balance. Add temporal/customer aggregate
  policy if a cumulative spending limit is required.
- Prompt injection may affect wording or tool selection; this implementation proves
  refund authorization and identity restrictions, not universal injection immunity.
- Concurrency tests use Moto locally. Run live concurrent retries against DynamoDB
  before claiming AWS concurrency evidence.
- Application logs omit prompts and PII; Strands message attributes are redacted.
  Gateway vended logs and Memory still may contain tool/customer data. Use only the
  synthetic fixtures for the assessment, scoped log-reader access and retention.
- Fault injection is an operator-controlled CloudFormation parameter, never a tool
  argument. Both the template and Lambda reject faults in `Stage=prod`.

## Submission hygiene

Keep `.env`, tokens, private keys, SSO caches and raw live logs out of Git. Review
sanitized evidence before committing it. `.gitignore` excludes `evidence/live/` by
default. Dependency versions are locked; review ECR scan findings and dependency
updates before using this with actual customer data.
