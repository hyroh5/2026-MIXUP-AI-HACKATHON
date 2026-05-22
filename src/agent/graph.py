from langgraph.graph import StateGraph, START, END

from .state import AgentState
from .llm import get_llm
from .nodes import (
    make_intent_router,
    make_date_optimizer_node,
    weather_node,
    stay_node,
    place_node,
    make_synthesizer_node,
)


def build_graph(model: str = "solar-pro3", temperature: float = 0.7, interactive: bool = True):
    """6-노드 여행 플래너 LangGraph 그래프.

    날짜 확정:  START → intent_router → weather → stay → place → synthesizer → END
    날짜 미정:  START → intent_router → date_optimizer → weather → stay → place → synthesizer → END

    Args:
        interactive: True(기본) = date_optimizer에서 TOP 10 표시 후 사용자 확인.
                     False = 1위 자동 선택 (FastAPI 서버 모드).
    """
    llm = get_llm(model=model, temperature=temperature)

    def _route_after_intent(state: AgentState) -> str:
        return "weather" if state.get("date_fixed", True) else "date_optimizer"

    graph = StateGraph(AgentState)
    graph.add_node("intent_router", make_intent_router(llm))
    graph.add_node("date_optimizer", make_date_optimizer_node(interactive=interactive))
    graph.add_node("weather", weather_node)
    graph.add_node("stay", stay_node)
    graph.add_node("place", place_node)
    graph.add_node("synthesizer", make_synthesizer_node(llm))

    graph.add_edge(START, "intent_router")
    graph.add_conditional_edges(
        "intent_router",
        _route_after_intent,
        {"weather": "weather", "date_optimizer": "date_optimizer"},
    )
    graph.add_edge("date_optimizer", "weather")
    graph.add_edge("weather", "stay")
    graph.add_edge("stay", "place")
    graph.add_edge("place", "synthesizer")
    graph.add_edge("synthesizer", END)

    return graph.compile()
