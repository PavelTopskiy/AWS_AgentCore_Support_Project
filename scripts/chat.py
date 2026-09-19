"""Small interactive client for exploring the deployed support agent."""

import argparse
import re
import uuid

import boto3

from scripts.invoke import invoke


def stack_output(stack, key):
    outputs = boto3.client("cloudformation").describe_stacks(StackName=stack)["Stacks"][0][
        "Outputs"
    ]
    return next(item["OutputValue"] for item in outputs if item["OutputKey"] == key)


def clean_answer(answer):
    return re.sub(r"<thinking>.*?</thinking>\s*", "", answer, flags=re.DOTALL).strip()


def main(stack, arn=None):
    runtime_arn = arn or stack_output(stack, "RuntimeArn")
    session = str(uuid.uuid4())
    last = None
    print("Customer Support Agent")
    print(f"Session: {session}")
    print("Commands: /new, /retry, /session, /quit")
    print("Refund requests receive a trusted operation ID automatically.\n")

    while True:
        try:
            prompt = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return
        if not prompt:
            continue
        if prompt == "/quit":
            print("Goodbye.")
            return
        if prompt == "/session":
            print(f"Session: {session}")
            continue
        if prompt == "/new":
            session = str(uuid.uuid4())
            print(f"Started new session: {session}")
            continue
        if prompt == "/retry":
            if last is None:
                print("Nothing to retry yet.")
                continue
            prompt, operation = last
            print(f"Retrying with operation ID: {operation or '(none)'}")
        else:
            operation = f"play-{uuid.uuid4()}" if "refund" in prompt.lower() else None
            last = (prompt, operation)
            if operation:
                print(f"Operation ID: {operation}")

        response = invoke(runtime_arn, prompt, session, operation)
        if response.get("ok"):
            print(f"agent> {clean_answer(response['answer'])}")
            print(f"tools> {', '.join(response.get('tools', [])) or '(none)'}")
            print(f"trace> {response.get('trace_id', '(none)')}\n")
        else:
            print(f"error> {response.get('error', 'UNKNOWN')}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack", default="support-agent")
    parser.add_argument("--arn", help="Runtime ARN; otherwise read it from the stack outputs")
    args = parser.parse_args()
    main(args.stack, args.arn)
