"""Atomic local-payment ledger. A real PSP must also honor the operation key."""

import hashlib
import json

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from support_agent.domain import BusinessError


class Store:
    def __init__(self, client, table: str, customer: str):
        self.client, self.table, self.customer = client, table, customer
        self.serializer, self.deserializer = TypeSerializer(), TypeDeserializer()

    def encode(self, item):
        return {k: self.serializer.serialize(v) for k, v in item.items()}

    def get(self, key):
        response = self.client.get_item(
            TableName=self.table, Key=self.encode({"pk": key}), ConsistentRead=True
        )
        return {k: self.deserializer.deserialize(v) for k, v in response.get("Item", {}).items()}

    def order(self, order_id):
        item = self.get(f"CUSTOMER#{self.customer}#ORDER#{order_id}")
        if not item:
            raise BusinessError("ORDER_NOT_FOUND")
        return item

    def customer_info(self):
        item = self.get(f"CUSTOMER#{self.customer}#PROFILE")
        if not item:
            raise BusinessError("CUSTOMER_NOT_FOUND")
        return {k: item[k] for k in ("customer_id", "display_name", "tier")}

    def refund(self, order_id: str, amount_cents: int, idempotency_key: str):
        # One durable key per customer + operation, with no TTL. No stale-lock recovery needed:
        # the ledger insert and balance decrement either both commit or neither commits.
        pk = f"CUSTOMER#{self.customer}#REFUND#{idempotency_key}"
        fingerprint = hashlib.sha256(
            json.dumps(
                [self.customer, order_id, amount_cents, "USD"], separators=(",", ":")
            ).encode()
        ).hexdigest()

        def existing():
            item = self.get(pk)
            if item and item["fingerprint"] != fingerprint:
                raise BusinessError("IDEMPOTENCY_CONFLICT")
            return item.get("result") if item else None

        if result := existing():
            return result
        self.order(order_id)
        result = {
            "refund_id": hashlib.sha256(pk.encode()).hexdigest()[:32],
            "order_id": order_id,
            "amount_cents": amount_cents,
            "currency": "USD",
            "status": "SIMULATED_COMPLETED",
        }
        try:
            self.client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self.table,
                            "Item": self.encode(
                                {"pk": pk, "fingerprint": fingerprint, "result": result}
                            ),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": self.table,
                            "Key": self.encode(
                                {"pk": f"CUSTOMER#{self.customer}#ORDER#{order_id}"}
                            ),
                            "UpdateExpression": "SET refundable_cents = refundable_cents - :amount",
                            "ConditionExpression": (
                                "currency = :usd AND refundable_cents >= :amount"
                            ),
                            "ExpressionAttributeValues": self.encode(
                                {":amount": amount_cents, ":usd": "USD"}
                            ),
                        }
                    },
                ]
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "TransactionCanceledException":
                raise
            # A concurrent request may have won. Strong read returns exactly its receipt.
            if result := existing():
                return result
            reasons = exc.response.get("CancellationReasons", [])
            if any(r.get("Code") == "ConditionalCheckFailed" for r in reasons):
                raise BusinessError("INSUFFICIENT_REFUNDABLE_BALANCE") from exc
            raise  # Conflicts/throttles are retryable, never a successful refund.
        return result
