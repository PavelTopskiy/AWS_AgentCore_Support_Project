import boto3
import pytest
from moto import mock_aws

from scripts.seed import seed
from support_agent.store import Store


@pytest.fixture
def store():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="eu-west-1")
        client.create_table(
            TableName="support-test",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        )
        seed(client, "support-test", "customer-001")
        yield Store(client, "support-test", "customer-001")
