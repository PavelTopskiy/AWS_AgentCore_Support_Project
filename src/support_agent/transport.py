"""Per-request SigV4 with refreshable role credentials, including MCP POST bodies."""

from contextlib import asynccontextmanager

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from mcp.client.streamable_http import streamable_http_client


class SigV4(httpx.Auth):
    requires_request_body = True

    def __init__(self, region, session=None):
        self.region = region
        self.session = session or boto3.Session(region_name=region)

    def auth_flow(self, request):
        credentials = self.session.get_credentials()
        if credentials is None:
            raise RuntimeError("Use AWS SSO locally or an IAM execution role in AWS")
        aws_request = AWSRequest(
            method=request.method,
            url=str(request.url),
            data=request.content,
            headers=dict(request.headers),
        )
        SigV4Auth(credentials.get_frozen_credentials(), "bedrock-agentcore", self.region).add_auth(
            aws_request
        )
        request.headers.update(dict(aws_request.headers))
        yield request


@asynccontextmanager
async def transport(url, region):
    async with httpx.AsyncClient(
        auth=SigV4(region), timeout=httpx.Timeout(25, connect=5), follow_redirects=False
    ) as client:
        async with streamable_http_client(url, http_client=client) as streams:
            yield streams
