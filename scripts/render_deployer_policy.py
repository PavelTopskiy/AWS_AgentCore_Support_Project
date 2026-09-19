"""Render the administrator policy template without embedding account details in Git."""

import argparse
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--stack", default="support-agent")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not (args.account.isdigit() and len(args.account) == 12):
        raise SystemExit("--account must be a 12-digit AWS account ID")
    source = Path("infra/deployer-policy.template.json").read_text()
    rendered = source.replace("${ACCOUNT_ID}", args.account)
    rendered = rendered.replace("${REGION}", args.region).replace("${STACK}", args.stack)
    Path(args.output).write_text(rendered)
    print(f"Wrote {args.output}; have an AWS administrator review and attach it to the deployer.")
