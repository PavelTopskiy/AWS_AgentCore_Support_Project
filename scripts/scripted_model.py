"""Offline deterministic Strands model for tool-selection and loop failure drills."""

import json

from strands.models.model import Model


class ScriptedModel(Model):
    def __init__(self, name="check_order", arguments=None, loop=True):
        self.name, self.arguments, self.loop = name, arguments or {}, loop
        self.calls = 0

    def get_config(self):
        return {"model_id": "offline-scripted-model"}

    def update_config(self, **model_config):
        raise NotImplementedError("This offline model has a fixed script")

    async def structured_output(self, *args, **kwargs):
        raise NotImplementedError("Not used by these drills")
        yield  # pragma: no cover -- preserve the async-generator interface

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.calls += 1
        yield {"messageStart": {"role": "assistant"}}
        if self.loop or self.calls == 1:
            yield {
                "contentBlockStart": {
                    "start": {
                        "toolUse": {
                            "name": self.name,
                            "toolUseId": f"offline-call-{self.calls}",
                        }
                    }
                }
            }
            yield {
                "contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(self.arguments)}}}
            }
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": "Offline drill complete"}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                "metrics": {"latencyMs": 1},
            }
        }
