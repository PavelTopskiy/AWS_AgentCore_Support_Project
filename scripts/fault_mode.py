"""Change only the CloudFormation fault-mode parameter on an existing TEST stack."""

import argparse

import boto3

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", required=True)
    parser.add_argument(
        "--mode", choices=["none", "timeout", "backend_500", "lost_response"], required=True
    )
    args = parser.parse_args()
    cfn = boto3.client("cloudformation")
    stack = cfn.describe_stacks(StackName=args.stack)["Stacks"][0]
    params = {p["ParameterKey"]: p["ParameterValue"] for p in stack["Parameters"]}
    if params.get("Stage") != "test":
        raise SystemExit("Fault drills require a test stack; production is refused.")
    if params["FaultMode"] == args.mode:
        raise SystemExit("Requested mode already active.")
    cfn.update_stack(
        StackName=args.stack,
        UsePreviousTemplate=True,
        Capabilities=["CAPABILITY_IAM"],
        Parameters=[
            {"ParameterKey": k, "ParameterValue": args.mode}
            if k == "FaultMode"
            else {"ParameterKey": k, "UsePreviousValue": True}
            for k in params
        ],
    )
    cfn.get_waiter("stack_update_complete").wait(StackName=args.stack)
    print(f"Fault mode is now {args.mode}. Restore 'none' after the drill.")
