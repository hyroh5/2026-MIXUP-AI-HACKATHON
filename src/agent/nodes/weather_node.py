from datetime import datetime, timedelta

from src.agent.state import AgentState
from src.weather import get_weather


def weather_node(state: AgentState) -> dict:
    """체크인~체크아웃 전 기간 날씨를 조회한다.

    date_optimizer가 이미 날씨를 계산해 state에 넣었으면 재호출 없이 재사용한다.
    """
    intent = state["intent"]
    dest = intent["destination"]

    if not intent.get("check_in"):
        print(f"\n⛅ [2/5] 날씨 조회 스킵 — check_in 미확정")
        return {"is_rainy": False, "weather_summary": "날짜 미확정으로 날씨 조회 불가"}

    # date_optimizer에서 이미 계산한 경우 재사용
    existing = state.get("weather_summary", "")
    if existing:
        print(f"\n⛅ [2/5] 날씨 재사용 — {dest} {intent['check_in']} ~ {intent['check_out']}")
        for line in existing.splitlines():
            print(f"  ✓ {line}")
        return {}

    check_in = datetime.strptime(intent["check_in"], "%Y-%m-%d").date()
    check_out = datetime.strptime(intent["check_out"], "%Y-%m-%d").date()
    nights = (check_out - check_in).days

    print(f"\n⛅ [2/5] 날씨 조회 중 — {dest} {intent['check_in']} ~ {intent['check_out']} ({nights}박)")

    daily_summaries = []
    any_rainy = False

    for i in range(nights + 1):
        target_date = (check_in + timedelta(days=i)).isoformat()
        try:
            result = get_weather(dest, target_date, silent=True)
            if result and result.daily and result.daily.temp_max is not None:
                d = result.daily
                prob = d.precipitation_probability_max
                rain = d.rain_sum or d.precipitation_sum or 0
                if (prob is not None and prob >= 50) or rain > 1.0:
                    any_rainy = True

                parts = [f"{target_date}:"]
                parts.append(f"최고 {d.temp_max}°C / 최저 {d.temp_min}°C")
                if prob is not None:
                    parts.append(f"강수확률 {prob:.0f}%")
                if rain:
                    parts.append(f"강우 {rain:.1f}mm")
                line = " ".join(parts)
                daily_summaries.append(line)
                print(f"  ✓ {line}")
            else:
                print(f"  ✗ {target_date}: 예보 없음 (범위 초과)")
        except Exception as e:
            daily_summaries.append(f"{target_date}: 조회 실패")
            print(f"  ✗ {target_date}: 오류 - {e}")

    return {"is_rainy": any_rainy, "weather_summary": "\n".join(daily_summaries)}
