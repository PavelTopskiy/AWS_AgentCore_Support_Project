# Acceptance and submission

## What is already verified

The repository includes executed local test results and locally generated OTel
traces. Tests use Moto for DynamoDB and injected model/transport failures. They
do not execute Cedar, deploy CloudFormation, call Bedrock, or prove AWS Memory
extraction. CloudFormation is schema-linted and runtime imports are checked.

## Required evidence to collect after deployment

| Requirement | Test/evidence | Current evidence status |
|---|---|---|
| Runtime + Strands | Runtime READY screenshot; successful agent invocation | Live invocation passed; screenshot pending |
| Gateway + MCP, 3 tools | Target schema and tools/list; order/customer replies | Live direct and agent calls passed; screenshot pending |
| Order 123 delay | `live_scenarios` agent_order; check_order span | Live scenario passed; cloud span pending |
| Customer lookup | `live_scenarios` agent_customer; get_customer span | Live scenario passed; cloud span pending |
| Refund succeeds | $500 receipt and order balance; simulated status visible | Live scenario passed |
| Memory across 2 sessions | Two distinct UUIDs, extracted memory record, answer in session B | Live extraction and session-B retrieval passed |
| $1,000 ALLOW | Exactly 100000-cent direct MCP call and receipt | Live Cedar execution passed |
| >$1,000 DENY | 100001 and 500000-cent Gateway calls; policy DENY, no Lambda/receipt | Live default-deny checks passed |
| Injection cannot bypass cap | Injection prompt plus deterministic direct MCP $5,000 test | Live injection and direct policy checks passed; trace pending |
| No duplicate refund | Same operation-123 returns same receipt; one balance decrement | Live idempotent retry passed |
| At least 3 failures | Invalid arguments, missing order, conflicting retry; timeout/500 drills | Three live business failures passed; timeout/500 drills pending |
| All 5 failure types traceable | `local-traces.json`; cloud trace records per runbook | Local spans present; cloud spans pending |
| Least privilege | Role policies, denied direct-Lambda attempt by operator | Template tests passed; AWS IAM negative test pending |
| No secrets | Review tracked files and sanitized evidence before publishing | No real credentials included |

## Run and save

```bash
mkdir -p evidence/live
uv run pytest -q --junitxml=evidence/junit.xml
uv run python -m scripts.live_scenarios --stack "$STACK"
```

The live runner saves results as it progresses and exits on a failed assertion.
No `status: PASS` appears until all its assertions pass. Reusing its fixed refund
keys makes reruns non-destructive to the fixture balances. Run it on clean synthetic
fixtures initially; do not reuse those keys for different amounts.

For live concurrency, start multiple direct Gateway calls with the **same** refund
arguments (e.g. order `concurrent`, 100 cents, key `concurrent-123`). Save all receipts
and a strongly consistent before/after DynamoDB read. Expect one receipt identity
and only a 100-cent decrement. Local thread tests are not a substitute for that
service-level record.

Capture screenshots or export logs for:

1. Runtime READY and Gateway target with the three tools.
2. Order, customer and refund agent interactions.
3. Session A preference and session B retrieval with different session IDs.
4. Exact $1,000 ALLOW and $5,000 DENY policy traces.
5. Prompt injection input, proposed tool call if any, and no refund ledger entry.
6. `operation-123` retried, same receipt and one balance decrement.
7. At least three live failures with root causes and their actual trace/span IDs.
8. Failure investigation matrix for all five required categories, clearly marking
   any category demonstrated only by local injection.

Use `docs/OBSERVABILITY.md` for drills. A simulated upstream failure envelope should
not be labeled an actual Gateway HTTP 500. If your assessor requires every failure
on AWS, complete an approved HTTP fault/proxy drill and a deterministic test-model
loop drill in a separate test deployment before declaring that requirement complete.

## Publish as one separate repository

Use **this directory** as the repository root; do not include the neighboring
`CustomerSupport` project, virtual environment, build artifacts or AWS caches.

```bash
git init -b main  # only if this directory has not already been initialized
git add README.md pyproject.toml uv.lock requirements.lock.txt Dockerfile .dockerignore .gitignore
git add src infra policies scripts tests docs .github evidence
git diff --cached --stat
git diff --cached
git commit -m "Implement AgentCore customer support assessment"
git remote add origin YOUR_GITHUB_OR_EPAM_GITLAB_REPOSITORY_URL
git push -u origin main
```

Create the empty GitHub/EPAM GitLab repository using your organization's normal
workflow. The GitHub Actions workflow runs local checks; on GitLab run the same
commands in your approved Python/uv CI image. No cloud deployment credentials are
needed for these tests.

Raw live output is ignored by default. Copy **reviewed and sanitized** evidence
into `evidence/submission/`, include an index describing the screenshots/logs and
their scenarios, then commit it. Do not claim the AWS-pending rows are complete
until the genuine cloud evidence is attached.
