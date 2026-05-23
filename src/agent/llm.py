import os
from langchain_upstage import ChatUpstage


def get_llm(model: str = "solar-pro", temperature: float = 0.7) -> ChatUpstage:
    """ChatUpstage 인스턴스를 반환한다.

    Args:
        model:       사용할 모델 이름 (기본: "solar-pro")
        temperature: 생성 다양성 (0.0 ~ 1.0)

    Returns:
        ChatUpstage 인스턴스

    Requires:
        UPSTAGE_API_KEY 환경변수
    """
    api_key = os.getenv("UPSTAGE_API_KEY")
    if not api_key:
        raise EnvironmentError("UPSTAGE_API_KEY 환경변수가 설정되지 않았습니다.")
    return ChatUpstage(api_key=api_key, model=model, temperature=temperature)
