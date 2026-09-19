# AWS setup and deployment

These instructions provision resources when you execute them. No AWS resources
were created during preparation of this repository. Start with a dedicated test
account/stack and synthetic data. Bedrock, Memory, Runtime, logs and retained
artifacts incur charges.

## 1. Prepare the account and workstation

1. Install AWS CLI v2, Python 3.12, `uv`, and Docker Desktop (or another Docker
   installation with Buildx and Linux ARM64 support). Start Docker.
2. Configure IAM Identity Center/SSO; do not create long-lived IAM access keys:

   ```bash
   aws configure sso --profile support-deployer
   aws sso login --profile support-deployer
   export AWS_PROFILE=support-deployer
   export AWS_REGION=us-east-1
   export AWS_DEFAULT_REGION="$AWS_REGION"
   aws sts get-caller-identity
   ```

3. In the AWS console, verify that **AgentCore Runtime, Gateway, Memory and Policy**
   are available in the selected region. Keep all project resources in that region.
   `eu-west-1` in the memory scenario is a preference, not a deployment requirement.
4. In **Amazon Bedrock → Model catalog**, select a regional model with tool use and
   on-demand inference. The template deliberately grants one exact model ARN.
   For example, verify availability of Nova Lite in the chosen region:

   ```bash
   export MODEL_ID=amazon.nova-lite-v1:0
   aws bedrock get-foundation-model --model-identifier "$MODEL_ID"
   export MODEL_ARN="arn:aws:bedrock:$AWS_REGION::foundation-model/$MODEL_ID"
   ```

   Complete any model subscription/use-case requirements shown by Bedrock. If you
   choose a cross-region inference profile, change the template to allow its exact
   profile ARN **and each routed foundation-model ARN**; do not grant all models.

   `scripts/deploy.sh` now reads the region from the active AWS profile when
   `AWS_REGION`/`AWS_DEFAULT_REGION` is unset. It defaults to Nova Lite and derives
   its regional foundation-model ARN. Set `MODEL_ID` and `MODEL_ARN` only when you
   intentionally choose another model. The script performs a read-only model
   availability check before creating resources.
5. Ask your account administrator for a **deployment role** authorized to manage
   the project stacks and their IAM roles, Lambda, DynamoDB, S3/ECR, AgentCore
   resources and CloudWatch configuration. `iam:PassRole` should be restricted to
   the project's execution roles with the appropriate passed-to-service condition.
   Initial AgentCore setup may need permission to create its service-linked roles.
   The application roles created by the template are narrower than this deployment
   identity. SCPs, permission boundaries and account quotas must permit the resources.
   The policy-creation identity also needs `bedrock-agentcore:InvokeGateway` on the
   project's Gateway: AWS policy validation invokes it. The template separately
   grants the Gateway service role all three policy-evaluation actions.

   A reviewable policy template is provided at
   `infra/deployer-policy.template.json`. Render it without committing account data:

   ```bash
   mkdir -p build
   uv run python scripts/render_deployer_policy.py \
     --account "$(aws sts get-caller-identity --query Account --output text)" \
     --region "$AWS_REGION" --stack support-agent \
     --output build/deployer-policy.json
   ```

   Give `build/deployer-policy.json` to the AWS administrator. They should attach
   it to a dedicated deployment role (preferred) or your deployment identity after
   review. The deployer policy is broader than application runtime policies because
   it provisions and deletes infrastructure; do not attach it to Runtime, Gateway,
   Lambda, or ordinary support operators.

## 2. Validate locally

From the root of this separate project:

```bash
uv sync --frozen --extra dev
uv run ruff check .
uv run ruff format --check .
uv run python infra/generate.py
uv run cfn-lint infra/stack.json infra/bootstrap.json
uv run pytest -q
```

The template is generated from `infra/generate.py` and `policies/*.cedar`. Commit
both source and generated JSON after edits. The runtime container installs
`requirements.lock.txt`, exported from `uv.lock`; regenerate it when dependencies
change with `uv export --frozen --no-dev --no-emit-project -o requirements.lock.txt`.
The Lambda has a smaller separately pinned requirements file in `infra/`.

## 3. Build and deploy

```bash
export STACK=support-agent
export STAGE=test
bash scripts/deploy.sh
```

With an AWS profile region configured, the minimal command is simply:

```bash
bash scripts/deploy.sh
```

The script runs tests, provisions a private versioned S3 bucket and immutable ECR
repository, builds the Lambda zip using **Linux ARM64 wheels**, builds/pushes the
ARM64 runtime container, resolves its immutable digest, and deploys the main stack.
Docker credentials come from a temporary ECR login token.

The stack creates the table, roles, Lambda, Memory preference strategy, enforcing
Policy Engine, IAM Gateway, three MCP tools, two Cedar permit policies, Runtime,
operator managed policy and Lambda error alarm. It does not attach the operator
policy to arbitrary people or modify your SSO permission sets.

The refund permit applies only when `amount_cents` is positive and no greater than
100000. AgentCore Policy uses default deny when no permit matches, so larger refunds
are denied without an explicit `forbid` policy. This also avoids AgentCore's policy
validator rejecting the deployment as overly restrictive.

This version uses fixed AgentCore resource names (`SupportProductionAgent`,
`SupportPreferences`, `SupportRefundPolicy`), so deploy **one instance per
account/region**, or change those names in the generator for another environment.
Use a short stack name such as `support-agent` so the generated Gateway name fits
its length limit.

If deployment fails, inspect **CloudFormation → stack → Events**. Fix the reported
permission, model, quota or resource error before retrying. Never disable policy
enforcement to work around a deployment failure. If the stack rolls back to
`ROLLBACK_COMPLETE`, remove the failed stack after reviewing its retained resources
before a fresh deployment.

For a stack in `ROLLBACK_COMPLETE` or `ROLLBACK_FAILED`, remove the failed stack
record and wait for deletion before rerunning. A `ROLLBACK_FAILED` caused by
AgentCore Memory still being created can be retried once Memory reaches `ACTIVE`:

```bash
aws cloudformation delete-stack --stack-name support-agent
aws cloudformation wait stack-delete-complete --stack-name support-agent
bash scripts/deploy.sh
```

The table uses `DeletionPolicy: Retain`, so a failed create can leave an orphaned,
empty synthetic table. Review it in DynamoDB before deleting it. For the first
failed deployment on 2026-09-19, CloudFormation reported the generated table name
`support-agent-Table-1U9ZUJDHXZVN2`. Delete it only after confirming it contains no
required records; deleting a DynamoDB table is irreversible.

## 4. Capture outputs and seed synthetic data

```bash
output() {
  aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text
}
export RUNTIME_ARN="$(output RuntimeArn)"
export GATEWAY_URL="$(output GatewayUrl)"
export TABLE_NAME="$(output TableName)"
export MEMORY_ID="$(output MemoryId)"
uv run python -m scripts.seed --table "$TABLE_NAME"
```

Seeding requires the deployment/data-admin identity's `dynamodb:PutItem` permission
on this table. It inserts only absent records and **never resets** a refunded order.
Fixtures include customer `customer-001` and orders `123`, `boundary`, `retry`, and
`concurrent`, each initially with $2,000 refundable balance. There is no real payment.

## 5. Grant invocation access

Read the `CallerPolicyArn` output. In **IAM Identity Center → Permission sets**, or
through your administrator's role-management workflow, grant the operator the
policy's two Runtime resources. Do not give an ordinary operator `InvokeGateway`,
`lambda:InvokeFunction`, DynamoDB write permissions or policy-management permissions.
Reauthenticate using the operator's SSO profile and try:

```bash
uv run python -m scripts.invoke --arn "$RUNTIME_ARN" \
  --prompt 'Why is my order 123 delayed?' --expected-tool check_order
uv run python -m scripts.invoke --arn "$RUNTIME_ARN" \
  --prompt 'Retrieve my customer information.' --expected-tool get_customer
uv run python -m scripts.invoke --arn "$RUNTIME_ARN" \
  --prompt 'Refund $500 for order 123.' --operation operation-123
```

Use the same `--operation operation-123` when retrying that refund, including from
a new session. New legitimate business operations need new IDs generated by the
trusted caller. A refund without an operation ID is blocked by the runtime hook.

## 6. Enable service observability in the console

1. Open **CloudWatch → Application Signals → Transaction search**, enable it, and
   allow the console to configure required X-Ray/CloudWatch delivery permissions.
   This is an account/region setting; coordinate with your account administrator.
2. Open **AgentCore → Runtime → SupportProductionAgent → Tracing → Edit → Enable**.
3. Open your **Gateway → Tracing → Edit → Enable**. Configure **Application logs**
   with a CloudWatch destination under `/aws/vendedlogs/bedrock-agentcore/`.
4. Open **Memory → SupportPreferences**, enable tracing and its application-log
   destination as well. Gateway and Memory log destinations are not assumed to be
   created automatically by the application template.
5. Set retention to 30 days on runtime and vended log groups. Lambda's group already
   uses 30 days. Restrict log-reader access; service logs can contain tool arguments.
6. Open the CloudWatch Lambda errors alarm and attach your approved SNS destination
   if alerts are needed. Add alarms for business-error log events as described in
   the observability guide; handled business errors do not increment Lambda Errors.

Runtime uses ADOT and custom OpenTelemetry spans. Lambda uses an X-Ray subsegment.
Service-created spans and their names depend on AgentCore; save the actual span IDs
from the console instead of inventing a fixed service span name.

## 7. Run acceptance tests

Use a separate test evaluator role with these **additional, exact-resource** grants:

- `cloudformation:DescribeStacks` on this stack;
- `bedrock-agentcore:GetGateway` and `bedrock-agentcore:InvokeGateway` on this Gateway;
- `bedrock-agentcore:RetrieveMemoryRecords` on this Memory;
- `dynamodb:GetItem` on this table, scoped to `CUSTOMER#customer-001#*` with LeadingKeys;
- the normal Runtime invocation grant.

```bash
uv run python -m scripts.live_scenarios --stack "$STACK"
```

The runner asserts tool behavior, duplicate refunds, exact $1,000 allowance,
$1,000.01/$5,000 denial, invalid inputs, missing orders, conflicting retries, model
tool selection, injection safety and preference retrieval in a second session.
Memory extraction is polled for up to five minutes. A timeout fails the test; it
does not pretend that same-session history proves long-term memory.

For the direct policy check, use the evaluator identity:

```bash
uv run python -m scripts.gateway_call --url "$GATEWAY_URL" --tool refund_customer \
  --arguments '{"order_id":"123","amount_cents":500000,"idempotency_key":"deny-5000"}'
```

Expected: Gateway policy denial, no business Lambda call for that request, no
refund ledger entry. Capture the actual policy decision and trace in CloudWatch.
Follow [EVIDENCE.md](EVIDENCE.md) for fault drills and submission artifacts.

## 8. Cleanup

When finished, delete the main stack from CloudFormation. **DynamoDB is retained**
to preserve financial audit records. After reviewing/exporting your synthetic
evidence, explicitly delete that retained table if desired. Also remove log delivery
configuration/log groups created through the console when no longer needed.

The artifact stack retains its S3 bucket and ECR repository. Empty/delete all S3
object versions and delete ECR images only when you intend to discard the builds,
then delete those retained resources and the artifact stack. Do not disable shared
Transaction Search or remove account-wide policies used by other applications.

## AWS references used

- [Gateway authorization](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-inbound-auth.html)
- [Cedar semantics and default deny](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-understanding-cedar.html)
- [CloudFormation Gateway policy configuration](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-bedrockagentcore-gateway-gatewaypolicyengineconfiguration.html)
- [CloudFormation Runtime](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-runtime.html)
- [CloudFormation Memory](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrockagentcore-memory.html)
- [Observability setup and service log destinations](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-configure.html)
- [Runtime permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html)

Checked during implementation on 2026-09-18. CloudFormation linting checks schemas;
only a successful deployment and live tests establish account-specific readiness.
