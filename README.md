# AgentCore Customer Support

A separate Python project using **Strands + AgentCore Runtime, Gateway/MCP, Memory,
IAM and Cedar**, with three tools: `check_order`, `get_customer`, `refund_customer`.

Refunds of **$0.01–$1,000 inclusive** pass the amount policy; higher amounts are
denied at Gateway. Order existence, customer scope and available balance must also
pass. Money uses integer USD cents. Atomic DynamoDB transactions deduplicate
`operation-123`, including concurrent requests and a lost response after commit.

This is a production-like assessment implementation with **synthetic customer data
and a simulated payment ledger**. The test deployment in `us-east-1` completed on
2026-09-19 and its live acceptance suite passed. The repository contains local trace
evidence plus a sanitized live scenario report; CloudWatch trace screenshots still
need to be captured for the submission.

## Start here

1. Follow [AWS setup and deployment](docs/AWS_SETUP.md).
2. Run the [scenario and submission checklist](docs/EVIDENCE.md).
3. Use the [observability runbook](docs/OBSERVABILITY.md) for failures.
4. Review [architecture](docs/ARCHITECTURE.md) and [security boundaries](docs/SECURITY.md).
5. Follow the [mentor demo script](docs/MENTOR_DEMO.md) for the final walkthrough.

```bash
uv sync --frozen --extra dev
uv run pytest -q
uv run python -m scripts.local_evidence
```

Requires Python 3.12, `uv`, AWS CLI v2 and Docker with ARM64 build support for
deployment. Use SSO/temporary credentials. `scripts/deploy.sh` creates billable AWS
resources when **you run it**; it does not publish a Git repository.

## Play with the deployed agent

Start an interactive terminal client. It resolves the Runtime ARN from the deployed
stack, keeps a session open, and creates trusted operation IDs for refund requests:

```bash
uv run --frozen python -m scripts.chat --stack support-agent
```

Try `Why is order 123 delayed?`, `Show my customer information`, or `Refund $10 for
order retry`. Use `/retry` to repeat the exact last operation and observe idempotency.
Use `/new` to start a second session while keeping AgentCore long-term Memory, and
`/quit` to exit. All orders and payments in this project are synthetic.

## Layout

| Path | Purpose |
|---|---|
| `src/support_agent/` | Runtime, MCP auth/retries, controls, Lambda and ledger |
| `infra/` | Generated CloudFormation, readable generator, build-artifact stack |
| `policies/` | Cedar read and amount-bounded refund permit rules |
| `scripts/` | Deploy, seed, invoke, live scenarios and failure drills |
| `tests/` | Domain, DynamoDB transactions, reliability, IAM structure, signing |
| `evidence/` | Local results and a checklist for genuine cloud evidence |

The application is scoped to one customer per deployment, used by trusted support
operators. It is not an Internet-facing multi-customer service. See the security
document before changing this identity model or integrating a payment provider.
