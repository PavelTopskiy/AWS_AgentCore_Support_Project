"""Insert synthetic fixtures once. Never reset a refunded balance on a rerun."""

import argparse

import boto3
from botocore.exceptions import ClientError

from support_agent.store import Store


def seed(client, table, customer):
    store = Store(client, table, customer)
    items = [
        {
            "pk": f"CUSTOMER#{customer}#PROFILE",
            "customer_id": customer,
            "display_name": "Alex Example",
            "tier": "gold",
        }
    ]
    for order in ("123", "boundary", "retry", "concurrent"):
        items.append(
            {
                "pk": f"CUSTOMER#{customer}#ORDER#{order}",
                "order_id": order,
                "status": "DELAYED",
                "delay_reason": "Carrier weather disruption",
                "currency": "USD",
                "refundable_cents": 200000,
            }
        )
    for item in items:
        try:
            client.put_item(
                TableName=table,
                Item=store.encode(item),
                ConditionExpression="attribute_not_exists(pk)",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True)
    parser.add_argument("--customer", default="customer-001")
    args = parser.parse_args()
    seed(boto3.client("dynamodb"), args.table, args.customer)
    print("Synthetic fixtures present; existing balances preserved.")
