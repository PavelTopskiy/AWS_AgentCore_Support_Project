from concurrent.futures import ThreadPoolExecutor

import pytest

from scripts.seed import seed
from support_agent.backend import dispatch
from support_agent.domain import BusinessError
from support_agent.store import Store


def refund(store, amount=50000, key="operation-123", order="123"):
    return dispatch(
        store,
        "refund_customer",
        {
            "order_id": order,
            "amount_cents": amount,
            "idempotency_key": key,
        },
    )


def test_order_and_customer(store):
    assert "weather" in dispatch(store, "check_order", {"order_id": "123"})["delay_reason"]
    assert dispatch(store, "get_customer", {})["customer_id"] == "customer-001"


@pytest.mark.parametrize("amount", [1, 99999, 100000])
def test_refund_allowed_boundary(store, amount):
    assert refund(store, amount)["amount_cents"] == amount
    assert store.order("123")["refundable_cents"] == 200000 - amount


@pytest.mark.parametrize("amount", [100001, 500000])
def test_refund_denied_even_without_model_or_gateway(store, amount):
    with pytest.raises(BusinessError, match="REFUND_LIMIT_EXCEEDED"):
        refund(store, amount)
    assert store.order("123")["refundable_cents"] == 200000
    assert not store.get("CUSTOMER#customer-001#REFUND#operation-123")


@pytest.mark.parametrize("amount", [True, False, 1.5, "50000", 0, -1, None])
def test_invalid_money(store, amount):
    with pytest.raises(BusinessError, match="INVALID_PARAMETERS"):
        refund(store, amount)


def test_response_lost_after_commit_and_retry(store):
    receipt = refund(store)  # Imagine the network drops this response.
    assert refund(store) == receipt
    assert store.order("123")["refundable_cents"] == 150000


def test_concurrent_retries(store):
    with ThreadPoolExecutor(max_workers=8) as executor:
        receipts = list(executor.map(lambda _: refund(store), range(16)))
    assert all(receipt == receipts[0] for receipt in receipts)
    assert store.order("123")["refundable_cents"] == 150000


def test_conflicting_key(store):
    refund(store)
    with pytest.raises(BusinessError, match="IDEMPOTENCY_CONFLICT"):
        refund(store, 49999)
    with pytest.raises(BusinessError, match="IDEMPOTENCY_CONFLICT"):
        refund(store, order="boundary")


def test_insufficient_balance_transaction_leaves_no_receipt(store):
    refund(store, 100000, "a")
    refund(store, 100000, "b")
    with pytest.raises(BusinessError, match="INSUFFICIENT_REFUNDABLE_BALANCE"):
        refund(store, 1, "c")
    assert not store.get("CUSTOMER#customer-001#REFUND#c")
    assert store.order("123")["refundable_cents"] == 0


def test_cross_customer_cannot_read_order(store):
    other = Store(store.client, store.table, "customer-002")
    with pytest.raises(BusinessError, match="ORDER_NOT_FOUND"):
        dispatch(other, "check_order", {"order_id": "123"})


def test_model_cannot_supply_customer_identity(store):
    with pytest.raises(BusinessError, match="INVALID_PARAMETERS"):
        dispatch(store, "get_customer", {"customer_id": "customer-002"})


def test_seed_does_not_reset_balance(store):
    refund(store)
    seed(store.client, store.table, store.customer)
    assert store.order("123")["refundable_cents"] == 150000


@pytest.mark.parametrize(
    "tool,args,code",
    [
        ("unknown", {}, "UNKNOWN_TOOL"),
        ("check_order", {"order_id": "404"}, "ORDER_NOT_FOUND"),
        ("check_order", {"order_id": "../123"}, "INVALID_PARAMETERS"),
        ("refund_customer", {}, "INVALID_PARAMETERS"),
    ],
)
def test_business_failures(store, tool, args, code):
    with pytest.raises(BusinessError, match=code):
        dispatch(store, tool, args)
