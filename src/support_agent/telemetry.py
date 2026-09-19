"""Structured, content-free correlation logs; ADOT owns the tracer provider."""

import json

from opentelemetry import trace

tracer = trace.get_tracer("support-agent")


def emit(event, **fields):
    span = trace.get_current_span()
    context = span.get_span_context()
    span.add_event(
        event,
        attributes={k: v for k, v in fields.items() if isinstance(v, (str, int, float, bool))},
    )
    print(
        json.dumps(
            {
                "event": event,
                "trace_id": f"{context.trace_id:032x}",
                "span_id": f"{context.span_id:016x}",
                **fields,
            }
        ),
        flush=True,
    )
