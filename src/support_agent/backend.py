"""Lambda Gateway target. Identity is deployment configuration, never tool input."""

import json
import os
import time
from decimal import Decimal

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from support_agent.domain import BusinessError, validate
from support_agent.store import Store

RETRYABLE = {
    "ProvisionedThroughputExceededException",
    "ThrottlingException",
    "InternalServerError",
    "TransactionConflictException",
    "TransactionCanceledException",
}


def dispatch(store, tool, args):
    validate(tool, args)
    if tool == "get_customer":
        return store.customer_info()
    if tool == "check_order":
        item = store.order(args["order_id"])
        return {k: item[k] for k in ("order_id", "status", "delay_reason", "refundable_cents")}
    return store.refund(**args)


def handler(event, context):
    # This context is supplied by Gateway, not a tool argument named 'tool'.
    tool = context.client_context.custom.get("bedrockAgentCoreToolName", "").split("___")[-1]
    mode = os.environ.get("FAULT_MODE", "none")
    if os.environ.get("STAGE") != "test" and mode != "none":
        raise RuntimeError("Fault injection is forbidden outside the test stage")
    try:
        from aws_xray_sdk.core import patch, xray_recorder

        patch(["boto3"])
        with xray_recorder.in_subsegment(f"business.{tool}") as segment:
            segment.put_annotation("tool", tool)
            return _execute(event, context, tool, mode, segment)
    except ImportError:
        # Useful for dependency-light local execution; deployed zip includes the SDK.
        if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            raise
        return _execute(event, context, tool, mode, None)


def _execute(event, context, tool, mode, segment):
    started = time.monotonic()
    code = "OK"
    try:
        validate(tool, event)
        if mode == "timeout":
            time.sleep(30)  # Lambda timeout is 10s; caller observes a failed invocation.
        if mode == "backend_500":
            code = "UPSTREAM_500"
            return {"ok": False, "error": {"code": code, "retryable": True}}
        store = Store(
            boto3.client(
                "dynamodb",
                config=Config(
                    retries={"mode": "standard", "total_max_attempts": 3},
                    connect_timeout=2,
                    read_timeout=3,
                ),
            ),
            os.environ["TABLE_NAME"],
            os.environ["CUSTOMER_ID"],
        )
        result = dispatch(store, tool, event)
        if mode == "lost_response" and tool == "refund_customer":
            # Commit already happened. Retrying with the same key must recover the receipt.
            code = "RESPONSE_LOST_AFTER_COMMIT"
            return {"ok": False, "error": {"code": code, "retryable": True}}
        return json.loads(json.dumps({"ok": True, "result": result}, default=_json_number))
    except BusinessError as exc:
        code = exc.code
        return {"ok": False, "error": {"code": code, "retryable": False}}
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        return {
            "ok": False,
            "error": {"code": "STORAGE_UNAVAILABLE", "retryable": code in RETRYABLE},
        }
    except Exception:
        code = "INTERNAL_ERROR"
        raise
    finally:
        if segment and code != "OK":
            segment.put_annotation("error_code", code)
            segment.add_error_flag()
        print(
            json.dumps(
                {
                    "event": "business_tool",
                    "tool": tool,
                    "error_code": code,
                    "request_id": context.aws_request_id,
                    "trace_id": segment.trace_id if segment else None,
                    "span_id": segment.id if segment else None,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            )
        )


def _json_number(value):
    if isinstance(value, Decimal):
        return int(value)
    raise TypeError(type(value).__name__)
