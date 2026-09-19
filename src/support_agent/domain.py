"""Pure validation shared by the backend and tests. All money is integer USD cents."""

import re

MAX_REFUND_CENTS = 100_000
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")


class BusinessError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def identifier(value: object) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise BusinessError("INVALID_PARAMETERS")
    return value


def validate(tool: str, args: dict) -> dict:
    fields = {
        "check_order": {"order_id"},
        "get_customer": set(),
        "refund_customer": {"order_id", "amount_cents", "idempotency_key"},
    }
    if tool not in fields:
        raise BusinessError("UNKNOWN_TOOL")
    if not isinstance(args, dict) or set(args) != fields[tool]:
        raise BusinessError("INVALID_PARAMETERS")
    for field in ("order_id", "idempotency_key"):
        if field in args:
            identifier(args[field])
    if tool == "refund_customer":
        amount = args["amount_cents"]
        if type(amount) is not int or amount <= 0:
            raise BusinessError("INVALID_PARAMETERS")
        if amount > MAX_REFUND_CENTS:
            raise BusinessError("REFUND_LIMIT_EXCEEDED")
    return args
