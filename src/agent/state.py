from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """그래프 전체에서 공유되는 상태.

    messages: 대화 히스토리. add_messages reducer가 자동으로 누적한다.
    """
    messages: Annotated[list, add_messages]
