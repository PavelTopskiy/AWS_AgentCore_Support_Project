import boto3
import httpx

from support_agent.transport import SigV4


def test_each_body_gets_its_own_signature_with_temporary_credentials():
    session = boto3.Session(
        aws_access_key_id="TESTKEY",
        aws_secret_access_key="not-a-real-secret",
        aws_session_token="test-session-token",
        region_name="eu-west-1",
    )
    auth = SigV4("eu-west-1", session)
    signatures = []
    for body in (b'{"amount_cents":100000}', b'{"amount_cents":500000}'):
        request = httpx.Request("POST", "https://example.invalid/mcp", content=body)
        signed = next(auth.auth_flow(request))
        assert signed.headers["x-amz-security-token"] == "test-session-token"
        assert "/eu-west-1/bedrock-agentcore/aws4_request" in signed.headers["authorization"]
        signatures.append(signed.headers["authorization"])
    assert signatures[0] != signatures[1]
