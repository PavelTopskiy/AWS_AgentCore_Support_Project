"""Generate plain CloudFormation JSON; no CDK bootstrap or custom-resource code."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ref(name):
    return {"Ref": name}


def att(name, attribute):
    return {"Fn::GetAtt": [name, attribute]}


def sub(value):
    return {"Fn::Sub": value}


def allow(actions, resources, **extra):
    return {"Effect": "Allow", "Action": actions, "Resource": resources, **extra}


def role(service, statements, source_kind=None):
    trust = {"Effect": "Allow", "Principal": {"Service": service}, "Action": "sts:AssumeRole"}
    if source_kind:
        trust["Condition"] = {
            "StringEquals": {"aws:SourceAccount": ref("AWS::AccountId")},
            "ArnLike": {
                "aws:SourceArn": sub(
                    "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:"
                    + source_kind
                    + "/*"
                )
            },
        }
    return {
        "Type": "AWS::IAM::Role",
        "Properties": {
            "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [trust]},
            "Policies": [
                {
                    "PolicyName": "ScopedPermissions",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": statements,
                    },
                }
            ],
        },
    }


def template():
    params = {
        k: {"Type": "String"}
        for k in (
            "CodeBucket",
            "CodeKey",
            "RuntimeImage",
            "RepositoryArn",
            "ModelId",
            "ModelArn",
        )
    }
    params.update(
        {
            "CustomerId": {
                "Type": "String",
                "Default": "customer-001",
                "AllowedPattern": "[A-Za-z0-9_-]{1,80}",
            },
            "Stage": {"Type": "String", "Default": "prod", "AllowedValues": ["test", "prod"]},
            "FaultMode": {
                "Type": "String",
                "Default": "none",
                "AllowedValues": ["none", "timeout", "backend_500", "lost_response"],
            },
        }
    )
    r = {}
    r["Table"] = {
        "Type": "AWS::DynamoDB::Table",
        "DeletionPolicy": "Retain",
        "UpdateReplacePolicy": "Retain",
        "Properties": {
            "BillingMode": "PAY_PER_REQUEST",
            "AttributeDefinitions": [{"AttributeName": "pk", "AttributeType": "S"}],
            "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}],
            "SSESpecification": {"SSEEnabled": True},
            "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
        },
    }
    r["ToolLogs"] = {
        "Type": "AWS::Logs::LogGroup",
        "Properties": {
            "LogGroupName": sub("/aws/lambda/${AWS::StackName}-tools"),
            "RetentionInDays": 30,
        },
    }
    r["ToolRole"] = role(
        "lambda.amazonaws.com",
        [
            # DynamoDB authorizes transaction members using PutItem/UpdateItem, not an IAM
            # action named TransactWriteItems. LeadingKeys prevents cross-customer access.
            allow(
                ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"],
                att("Table", "Arn"),
                Condition={
                    "ForAllValues:StringLike": {
                        "dynamodb:LeadingKeys": [sub("CUSTOMER#${CustomerId}#*")]
                    }
                },
            ),
            allow(["logs:CreateLogStream", "logs:PutLogEvents"], att("ToolLogs", "Arn")),
            allow(["xray:PutTraceSegments", "xray:PutTelemetryRecords"], "*"),
        ],
    )
    r["Tools"] = {
        "Type": "AWS::Lambda::Function",
        "Properties": {
            "FunctionName": sub("${AWS::StackName}-tools"),
            "Runtime": "python3.12",
            "Architectures": ["arm64"],
            "Handler": "support_agent.backend.handler",
            "Role": att("ToolRole", "Arn"),
            "Timeout": 10,
            "MemorySize": 256,
            "TracingConfig": {"Mode": "Active"},
            "Code": {"S3Bucket": ref("CodeBucket"), "S3Key": ref("CodeKey")},
            "Environment": {
                "Variables": {
                    "TABLE_NAME": ref("Table"),
                    "CUSTOMER_ID": ref("CustomerId"),
                    "STAGE": ref("Stage"),
                    "FAULT_MODE": ref("FaultMode"),
                }
            },
        },
    }
    r["Engine"] = {
        "Type": "AWS::BedrockAgentCore::PolicyEngine",
        "Properties": {"Name": "SupportRefundPolicy"},
    }
    r["GatewayRole"] = role(
        "bedrock-agentcore.amazonaws.com",
        [
            allow(["lambda:InvokeFunction"], att("Tools", "Arn")),
            allow(["bedrock-agentcore:GetPolicyEngine"], att("Engine", "PolicyEngineArn")),
            allow(
                [
                    "bedrock-agentcore:AuthorizeAction",
                    "bedrock-agentcore:PartiallyAuthorizeActions",
                ],
                [
                    att("Engine", "PolicyEngineArn"),
                    # Gateway's generated ID is unavailable until after its role exists.
                    # Limit the suffix wildcard to this stack's unique gateway-name prefix.
                    sub(
                        "arn:${AWS::Partition}:bedrock-agentcore:${AWS::Region}:"
                        "${AWS::AccountId}:gateway/${AWS::StackName}-gateway-*"
                    ),
                ],
            ),
        ],
        "gateway",
    )
    r["Gateway"] = {
        "Type": "AWS::BedrockAgentCore::Gateway",
        "Properties": {
            "Name": sub("${AWS::StackName}-gateway"),
            "AuthorizerType": "AWS_IAM",
            "ProtocolType": "MCP",
            "RoleArn": att("GatewayRole", "Arn"),
            "PolicyEngineConfiguration": {
                "Arn": att("Engine", "PolicyEngineArn"),
                "Mode": "ENFORCE",
            },
        },
    }
    tool_schemas = []
    for name, description, fields in [
        (
            "check_order",
            "Check order status and reason for delay for the authorized customer.",
            {"order_id": ("string", "Order identifier, for example 123")},
        ),
        ("get_customer", "Retrieve the authorized customer's name and support tier.", {}),
        (
            "refund_customer",
            "Process one USD refund. Amount is integer cents. Reuse the operation key on retries.",
            {
                "order_id": ("string", "Order identifier"),
                "amount_cents": ("integer", "USD cents; $1000 = 100000"),
                "idempotency_key": ("string", "Stable caller operation identifier"),
            },
        ),
    ]:
        schema = {
            "Type": "object",
            "Properties": {k: {"Type": v[0], "Description": v[1]} for k, v in fields.items()},
        }
        if fields:
            schema["Required"] = list(fields)
        tool_schemas.append({"Name": name, "Description": description, "InputSchema": schema})
    r["Target"] = {
        "Type": "AWS::BedrockAgentCore::GatewayTarget",
        "Properties": {
            "Name": "SupportTools",
            "GatewayIdentifier": ref("Gateway"),
            "CredentialProviderConfigurations": [{"CredentialProviderType": "GATEWAY_IAM_ROLE"}],
            "TargetConfiguration": {
                "Mcp": {
                    "Lambda": {
                        "LambdaArn": att("Tools", "Arn"),
                        "ToolSchema": {"InlinePayload": tool_schemas},
                    }
                }
            },
        },
    }
    for name, file in [
        ("ReadPolicy", "read"),
        ("RefundPolicy", "refund"),
    ]:
        r[name] = {
            "Type": "AWS::BedrockAgentCore::Policy",
            "DependsOn": "Target",
            "Properties": {
                "Name": name,
                "PolicyEngineId": att("Engine", "PolicyEngineId"),
                "ValidationMode": "FAIL_ON_ANY_FINDINGS",
                "EnforcementMode": "ACTIVE",
                "Definition": {
                    "Cedar": {"Statement": sub((ROOT / "policies" / f"{file}.cedar").read_text())}
                },
            },
        }
    r["Memory"] = {
        "Type": "AWS::BedrockAgentCore::Memory",
        "Properties": {
            "Name": "SupportPreferences",
            "EventExpiryDuration": 30,
            "IndexedKeys": [
                {"Key": "stateType", "Type": "STRING"},
                {"Key": "agentId", "Type": "STRING"},
            ],
            "MemoryStrategies": [
                {
                    "UserPreferenceMemoryStrategy": {
                        "Name": "UserPreferences",
                        "Namespaces": ["/preferences/{actorId}/"],
                    }
                }
            ],
        },
    }
    runtime_logs = sub(
        "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/bedrock-agentcore/runtimes/*"
    )
    r["RuntimeRole"] = role(
        "bedrock-agentcore.amazonaws.com",
        [
            allow(["bedrock-agentcore:InvokeGateway"], att("Gateway", "GatewayArn")),
            allow(
                [
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:GetEvent",
                    "bedrock-agentcore:DeleteEvent",
                    "bedrock-agentcore:ListEvents",
                    "bedrock-agentcore:RetrieveMemoryRecords",
                    "bedrock-agentcore:ListMemoryRecords",
                ],
                att("Memory", "MemoryArn"),
            ),
            allow(
                ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"], ref("ModelArn")
            ),
            allow(["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"], ref("RepositoryArn")),
            allow(["ecr:GetAuthorizationToken"], "*"),
            allow(
                [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams",
                ],
                runtime_logs,
            ),
            allow(["logs:DescribeLogGroups"], "*"),
            allow(
                [
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets",
                ],
                "*",
            ),
            allow(
                ["cloudwatch:PutMetricData"],
                "*",
                Condition={"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}},
            ),
        ],
        "runtime",
    )
    r["Runtime"] = {
        "Type": "AWS::BedrockAgentCore::Runtime",
        "DependsOn": ["ReadPolicy", "RefundPolicy"],
        "Properties": {
            "AgentRuntimeName": "SupportProductionAgent",
            "RoleArn": att("RuntimeRole", "Arn"),
            "AgentRuntimeArtifact": {
                "ContainerConfiguration": {"ContainerUri": ref("RuntimeImage")}
            },
            "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
            "ProtocolConfiguration": "HTTP",
            "EnvironmentVariables": {
                "CUSTOMER_ID": ref("CustomerId"),
                "MEMORY_ID": att("Memory", "MemoryId"),
                "MODEL_ID": ref("ModelId"),
                "GATEWAY_URL": att("Gateway", "GatewayUrl"),
                "OTEL_SERVICE_NAME": "support-agent",
                "OTEL_PYTHON_DISTRO": "aws_distro",
                "OTEL_PYTHON_CONFIGURATOR": "aws_configurator",
                "OTEL_TRACES_SAMPLER": "always_on",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
                "OTEL_PROPAGATORS": "xray,tracecontext,baggage",
                "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false",
                "OTEL_SEMCONV_STABILITY_OPT_IN": (
                    "gen_ai_latest_experimental,gen_ai_unredacted_attributes="
                ),
            },
        },
    }
    # Attach this narrowly scoped policy to the operator's SSO permission set/role.
    r["CallerPolicy"] = {
        "Type": "AWS::IAM::ManagedPolicy",
        "Properties": {
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    allow(
                        ["bedrock-agentcore:InvokeAgentRuntime"],
                        [
                            att("Runtime", "AgentRuntimeArn"),
                            sub("${Runtime.AgentRuntimeArn}/runtime-endpoint/DEFAULT"),
                        ],
                    ),
                ],
            },
        },
    }
    r["ToolErrorsAlarm"] = {
        "Type": "AWS::CloudWatch::Alarm",
        "Properties": {
            "AlarmDescription": "Lambda failures/timeouts; configure an SNS action for paging",
            "Namespace": "AWS/Lambda",
            "MetricName": "Errors",
            "Statistic": "Sum",
            "Dimensions": [{"Name": "FunctionName", "Value": ref("Tools")}],
            "Period": 60,
            "EvaluationPeriods": 1,
            "Threshold": 1,
            "ComparisonOperator": "GreaterThanOrEqualToThreshold",
            "TreatMissingData": "notBreaching",
        },
    }
    outputs = {
        "RuntimeArn": att("Runtime", "AgentRuntimeArn"),
        "GatewayUrl": att("Gateway", "GatewayUrl"),
        "GatewayArn": att("Gateway", "GatewayArn"),
        "GatewayId": ref("Gateway"),
        "PolicyEngineId": att("Engine", "PolicyEngineId"),
        "MemoryId": att("Memory", "MemoryId"),
        "TableName": ref("Table"),
        "ToolFunction": ref("Tools"),
        "CallerPolicyArn": ref("CallerPolicy"),
        "CustomerId": ref("CustomerId"),
    }
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Customer support assessment stack",
        "Parameters": params,
        "Rules": {
            "NoProductionFaults": {
                "RuleCondition": {"Fn::Equals": [ref("Stage"), "prod"]},
                "Assertions": [
                    {
                        "Assert": {"Fn::Equals": [ref("FaultMode"), "none"]},
                        "AssertDescription": "Production cannot enable fault injection",
                    }
                ],
            }
        },
        "Resources": r,
        "Outputs": {k: {"Value": v} for k, v in outputs.items()},
    }


if __name__ == "__main__":
    (ROOT / "infra" / "stack.json").write_text(json.dumps(template(), indent=2) + "\n")
