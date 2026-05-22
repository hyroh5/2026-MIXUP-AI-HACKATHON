from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage

from .state import AgentState
from .llm import get_llm


def build_graph(model: str = "solar-pro3", temperature: float = 0.7):
    """단일 노드 LangGraph 그래프를 빌드하고 컴파일해 반환한다.

    그래프 구조:
        START → chat → END

    Args:
        model:       LLM 모델 이름
        temperature: LLM temperature

    Returns:
        컴파일된 CompiledStateGraph

    Usage:
        app = build_graph()
        result = app.invoke({"messages": [HumanMessage(content="안녕?")]})
        print(result["messages"][-1].content)
    """
    llm = get_llm(model=model, temperature=temperature)

    def chat_node(state: AgentState) -> dict:
        """메시지를 LLM에 전달하고 응답을 반환하는 단일 노드."""
        response = llm.invoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("chat", chat_node)
    graph.add_edge(START, "chat")
    graph.add_edge("chat", END)

    return graph.compile()
