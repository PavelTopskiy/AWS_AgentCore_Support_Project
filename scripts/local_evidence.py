"""Real local OpenTelemetry spans around injected failures, NOT AWS execution evidence."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from strands import Agent, tool

from scripts.scripted_model import ScriptedModel
from support_agent.controls import Controls, is_loop_limit
from support_agent.domain import BusinessError, validate
from support_agent.reliability import retry_call
from support_agent.telemetry import emit


@tool
def get_customer() -> str:
    """Return a synthetic customer for the offline failure drills."""
    return "Alex Example"


def main():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("local-failure-drills")
    success = {"status": "success", "content": [{"text": '{"ok":true}'}]}
    roots = {}
    causes = {
        "tool_timeout": "Injected transport ReadTimeout; bounded retry succeeded on attempt 2.",
        "http_500": "Injected HTTP 500 response; bounded retry succeeded on attempt 2.",
        "invalid_parameters": (
            "Order identifier contains forbidden path characters; rejected before backend access."
        ),
        "wrong_tool_selection": (
            "Injected get_customer selection when the evaluator expected check_order."
        ),
        "llm_loop": "Seventh model attempt rejected by the six-call runtime budget.",
    }
    for scenario in causes:
        with tracer.start_as_current_span(f"drill.{scenario}") as span:
            span.set_attribute("evidence.environment", "local-injected")
            span.set_attribute("scenario", scenario)
            roots[scenario] = f"{span.get_span_context().trace_id:032x}"
            if scenario == "tool_timeout":
                asyncio.run(
                    retry_call(
                        AsyncMock(side_effect=[httpx.ReadTimeout("injected"), success]),
                        sleep=AsyncMock(),
                    )
                )
            elif scenario == "http_500":
                request = httpx.Request("POST", "https://example.invalid/mcp")
                error = httpx.HTTPStatusError(
                    "injected", request=request, response=httpx.Response(500, request=request)
                )
                asyncio.run(retry_call(AsyncMock(side_effect=[error, success]), sleep=AsyncMock()))
            elif scenario == "invalid_parameters":
                try:
                    validate("check_order", {"order_id": "../123"})
                except BusinessError as exc:
                    span.set_status(StatusCode.ERROR)
                    emit("invalid_parameters", code=exc.code)
            elif scenario == "wrong_tool_selection":
                Agent(
                    model=ScriptedModel(name="get_customer", loop=False),
                    tools=[get_customer],
                    hooks=[Controls(expected_tool="check_order")],
                    callback_handler=None,
                )("Why is order 123 delayed?")
                span.set_status(StatusCode.ERROR)
            else:
                controls = Controls()
                model = ScriptedModel(name="get_customer")
                try:
                    Agent(
                        model=model, tools=[get_customer], hooks=[controls], callback_handler=None
                    )("Repeat forever")
                except Exception as exc:
                    if not is_loop_limit(exc):
                        raise
                    assert model.calls == 6
                    span.set_status(StatusCode.ERROR)
    spans = [json.loads(s.to_json()) for s in exporter.get_finished_spans()]
    evidence = {
        "environment": "local-injected",
        "aws_deployed": False,
        "root_causes": causes,
        "trace_ids": roots,
        "spans": spans,
    }
    Path("evidence/local-traces.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print("Wrote evidence/local-traces.json (local injected failures only)")


if __name__ == "__main__":
    main()
