"""IAM authenticated invocation; session IDs are explicit and reusable."""

import argparse
import json
import uuid

import boto3
from botocore.config import Config


def invoke(arn, prompt, session, operation=None, expected_tool=None):
    payload = {"prompt": prompt}
    if operation:
        payload["operation_id"] = operation
    if expected_tool:
        payload["expected_tool"] = expected_tool
    # Never blindly retry a whole LLM turn. The caller reuses operation_id if uncertain.
    result = boto3.client(
        "bedrock-agentcore",
        config=Config(
            read_timeout=300,
            retries={"total_max_attempts": 1},
        ),
    ).invoke_agent_runtime(
        agentRuntimeArn=arn,
        runtimeSessionId=session,
        contentType="application/json",
        payload=json.dumps(payload).encode(),
    )
    return json.loads(result["response"].read())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--arn", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--session", default=str(uuid.uuid4()))
    parser.add_argument("--operation")
    parser.add_argument("--expected-tool")
    args = parser.parse_args()
    print(
        json.dumps(
            {
                "session_id": args.session,
                "response": invoke(
                    args.arn,
                    args.prompt,
                    args.session,
                    args.operation,
                    args.expected_tool,
                ),
            },
            indent=2,
        )
    )
