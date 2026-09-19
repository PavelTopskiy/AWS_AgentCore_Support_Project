"""Direct MCP call to demonstrate enforcement independently of the language model."""

import argparse
import asyncio
import json
import uuid

import boto3

from support_agent.reliability import ReliableMCPClient
from support_agent.transport import transport

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument(
        "--tool", required=True, choices=["check_order", "get_customer", "refund_customer"]
    )
    parser.add_argument("--arguments", default="{}")
    args = parser.parse_args()
    region = boto3.Session().region_name
    with ReliableMCPClient(lambda: transport(args.url, region)) as client:
        result = asyncio.run(
            client.call_tool_async(
                tool_use_id=str(uuid.uuid4()),
                name=f"SupportTools___{args.tool}",
                arguments=json.loads(args.arguments),
            )
        )
        print(json.dumps(result, indent=2))
