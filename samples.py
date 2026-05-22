from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import HumanMessage
from src.agent import build_graph

SAMPLES = [
    # 날씨
    "서울 오늘 날씨 어때?",
    "다음 주 도쿄 날씨 알려줘",
    # 항공
    "서울에서 도쿄 가는 항공편 추천해줘",
    "ICN에서 CDG 가는 편도 비행기 있어?",
    # 교통
    "서울역에서 부산역까지 기차로 얼마나 걸려?",
    "인천공항에서 강남역 가는 방법 알려줘",
    # 호텔
    "도쿄 신주쿠 근처 호텔 추천해줘",
    "파리 에펠탑 근처 5성급 호텔 알려줘",
    # 관광
    "오사카에서 꼭 가봐야 할 곳 추천해줘",
    "방콕 맛집 알려줘",
    # 종합 여행 플랜
    "3박 4일 도쿄 여행 일정 짜줘",
    "혼자 유럽 여행 처음인데 어디서 시작하면 좋아?",
]


def run_samples(indices: list[int] | None = None) -> None:
    """샘플 질문들을 에이전트에 순서대로 던지고 답변을 출력한다.

    Args:
        indices: 실행할 샘플 번호 목록 (None이면 전체 실행)
    """
    app = build_graph()
    targets = [(i, SAMPLES[i]) for i in (indices or range(len(SAMPLES)))]

    for i, question in targets:
        print(f"[Q{i + 1}] {question}")
        result = app.invoke({"messages": [HumanMessage(content=question)]})
        print(f"[A{i + 1}] {result['messages'][-1].content}")
        print("-" * 60)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # 예: python samples.py 0 3 5  → 1번, 4번, 6번 질문만 실행
        indices = [int(x) for x in sys.argv[1:]]
        run_samples(indices)
    else:
        run_samples()
