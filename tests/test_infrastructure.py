from infra.generate import template


def test_gateway_is_iam_and_policy_fail_closed():
    resources = template()["Resources"]
    gateway = resources["Gateway"]["Properties"]
    assert gateway["AuthorizerType"] == "AWS_IAM"
    assert gateway["PolicyEngineConfiguration"]["Mode"] == "ENFORCE"
    for name in ("ReadPolicy", "RefundPolicy"):
        assert resources[name]["Properties"]["ValidationMode"] == "FAIL_ON_ANY_FINDINGS"
        assert resources[name]["DependsOn"] == "Target"
    assert "DenyPolicy" not in resources

    refund_statement = resources["RefundPolicy"]["Properties"]["Definition"]["Cedar"]["Statement"][
        "Fn::Sub"
    ]
    assert "context.input.amount_cents > 0" in refund_statement
    assert "context.input.amount_cents <= 100000" in refund_statement


def test_runtime_cannot_bypass_gateway_or_modify_policy():
    statements = template()["Resources"]["RuntimeRole"]["Properties"]["Policies"][0][
        "PolicyDocument"
    ]["Statement"]
    actions = {action for s in statements for action in s["Action"]}
    assert "bedrock-agentcore:InvokeGateway" in actions
    assert not any(x.startswith(("lambda:", "dynamodb:", "iam:")) for x in actions)
    assert not any("Policy" in x or x.endswith(":*") for x in actions)


def test_three_business_tools_and_no_model_identity():
    tools = template()["Resources"]["Target"]["Properties"]["TargetConfiguration"]["Mcp"]["Lambda"][
        "ToolSchema"
    ]["InlinePayload"]
    assert len(tools) == 3
    assert all("customer_id" not in t["InputSchema"]["Properties"] for t in tools)


def test_gateway_has_all_policy_evaluation_permissions():
    statements = template()["Resources"]["GatewayRole"]["Properties"]["Policies"][0][
        "PolicyDocument"
    ]["Statement"]
    actions = {action for statement in statements for action in statement["Action"]}
    assert {
        "bedrock-agentcore:GetPolicyEngine",
        "bedrock-agentcore:AuthorizeAction",
        "bedrock-agentcore:PartiallyAuthorizeActions",
    } <= actions
    assert all(statement["Resource"] != "*" for statement in statements)
