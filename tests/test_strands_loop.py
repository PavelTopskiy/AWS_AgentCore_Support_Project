import pytest
from strands import Agent, tool
from strands.types.exceptions import EventLoopException

from scripts.scripted_model import ScriptedModel
from support_agent.controls import Controls, is_loop_limit


@tool
def check_order(order_id: str) -> str:
    """Return a synthetic order for the offline model drill."""
    return f"Order {order_id} is delayed"


def test_real_strands_loop_stops_after_six_model_calls():
    model = ScriptedModel(arguments={"order_id": "123"})
    controls = Controls()
    agent = Agent(model=model, tools=[check_order], hooks=[controls], callback_handler=None)
    with pytest.raises(EventLoopException) as error:
        agent("Check my order forever")
    assert is_loop_limit(error.value)
    assert model.calls == 6
    assert controls.selected == ["check_order"] * 6


def test_real_strands_wrong_tool_selection_is_logged(capsys):
    model = ScriptedModel(arguments={"order_id": "123"}, loop=False)
    controls = Controls(expected_tool="get_customer")
    agent = Agent(model=model, tools=[check_order], hooks=[controls], callback_handler=None)
    agent("Retrieve customer details")
    assert "wrong_tool_selection" in capsys.readouterr().out
    assert model.calls == 2
