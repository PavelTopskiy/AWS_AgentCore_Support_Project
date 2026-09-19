"""Runtime budget and trusted operation binding; Cedar remains the amount authority."""

from strands.hooks import HookProvider
from strands.hooks.events import BeforeModelCallEvent, BeforeToolCallEvent

from support_agent.telemetry import emit


class LoopLimit(Exception):
    pass


def is_loop_limit(error):
    """Strands wraps hook exceptions in EventLoopException after a tool cycle."""
    seen = set()
    while error is not None and id(error) not in seen:
        if isinstance(error, LoopLimit):
            return True
        seen.add(id(error))
        error = error.__cause__
    return False


class Controls(HookProvider):
    def __init__(self, operation_id=None, expected_tool=None, max_model_calls=6):
        self.operation_id, self.expected_tool = operation_id, expected_tool
        self.calls, self.max_model_calls = 0, max_model_calls
        self.selected = []

    def register_hooks(self, registry):
        registry.add_callback(BeforeModelCallEvent, self.before_model)
        registry.add_callback(BeforeToolCallEvent, self.before_tool)

    def before_model(self, event):
        self.calls += 1
        if self.calls > self.max_model_calls:
            emit("llm_loop", model_calls=self.calls, limit=self.max_model_calls)
            raise LoopLimit("MODEL_CALL_BUDGET_EXCEEDED")

    def before_tool(self, event):
        name = event.tool_use["name"].split("___")[-1]
        self.selected.append(name)
        emit("tool_selected", tool=name)
        if self.expected_tool and name != self.expected_tool:
            emit("wrong_tool_selection", expected=self.expected_tool, actual=name)
        if name == "refund_customer":
            if not self.operation_id:
                event.cancel_tool = "Refunds require a caller-supplied operation_id."
            else:
                # A model cannot change the key on a retry or split a refund using new keys.
                event.tool_use["input"]["idempotency_key"] = self.operation_id
