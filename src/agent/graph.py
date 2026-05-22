from langgraph.graph import StateGraph, START, END

from .state import AgentState
from .llm import get_llm
from .nodes import (
    make_intent_router,
    date_optimizer_node,
    weather_node,
    stay_node,
    place_node,
    make_synthesizer_node,
)


def build_graph(model: str = "solar-pro3", temperature: float = 0.7):
    """6-노드 여행 플래너 LangGraph 그래프.

    날짜 확정:  START → intent_router → weather → stay → place → synthesizer → END
    날짜 미정:  START → intent_router → date_optimizer → weather → stay → place → synthesizer → END
    """
    llm = get_llm(model=model, temperature=temperature)

    def _route_after_intent(state: AgentState) -> str:
        """날짜 확정 여부에 따라 date_optimizer 또는 weather로 분기한다."""
        return "weather" if state.get("date_fixed", True) else "date_optimizer"

    graph = StateGraph(AgentState)
    graph.add_node("intent_router", make_intent_router(llm))
    graph.add_node("date_optimizer", date_optimizer_node)
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
