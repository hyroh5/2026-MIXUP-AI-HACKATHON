from datetime import datetime, timedelta, date as date_type

from src.agent.state import AgentState, TravelIntent
from src.weather import get_weather
from src.cheapest_date import get_cheapest_dates
from src.cheapest_date.iata import get_iata, is_domestic as iata_is_domestic


def _make_candidate_dates(target_months: list[str], today: date_type) -> list[str]:
    """target_months에서 4일 간격 후보 날짜 최대 8개를 생성한다."""
    from datetime import date as date_cls
    candidates = []
    for month_str in target_months:
        year, month = int(month_str[:4]), int(month_str[4:])
        d = date_cls(year, month, 1)
        while d.month == month and len(candidates) < 8:
            if (d - today).days > 7:
                candidates.append(d.isoformat())
            d += timedelta(days=4)
    return candidates or [(today + timedelta(days=30)).isoformat()]


def _weather_only_candidates(dest: str, trip_nights: int, today: date_type, intent: TravelIntent) -> dict:
    """항공 API 실패 시 날씨만으로 최적 날짜 3개를 추천한다.

    target_months가 있으면 해당 월의 날짜를 탐색하고,
    없으면 D+14 이내 단기 예보 범위를 탐색한다.
    """
    target_months: list = intent.get("target_months") or []
    if target_months:
        probe_dates = _make_candidate_dates(target_months, today)
    else:
        probe_dates = [(today + timedelta(days=i)).isoformat() for i in range(1, 14, 3)]

    candidates = []
    for check_date in probe_dates:
        try:
            w = get_weather(dest, check_date, silent=True)
        except Exception:
            continue
        if not w or not w.daily or w.daily.temp_max is None:
            continue
        d = w.daily
        prob = d.precipitation_probability_max
        temp_max = d.temp_max
        prob_score = 3 if (prob is None or prob < 50) else 0
        temp_score = 3 if 18 <= temp_max <= 28 else 0
        score = float(prob_score + temp_score)
        prob_str = f"강수확률 {prob:.0f}%" if prob is not None else f"강수 {d.precipitation_sum or 0:.1f}mm"
        check_out = (
            datetime.strptime(check_date, "%Y-%m-%d").date()
            + timedelta(days=trip_nights)
        ).isoformat()
        candidates.append({
            "check_in": check_date,
            "check_out": check_out,
            "flight_price": 0,
            "weather_summary": f"최고 {temp_max}°C, {prob_str}",
            "score": score,
            "reason": f"날씨 기반 추천 · 최고 {temp_max}°C, {prob_str}",
        })
        if len(candidates) >= 5:
            break

    candidates.sort(key=lambda x: x["score"], reverse=True)

    updated_intent = dict(intent)
    if candidates:
        best = candidates[0]
        updated_intent["check_in"] = best["check_in"]
        updated_intent["check_out"] = best["check_out"]
        print(f"  ✓ 날씨 기반 추천 날짜: {best['check_in']} ~ {best['check_out']} ({best['reason']})")
    else:
        fallback = probe_dates[0] if probe_dates else (today + timedelta(days=30)).isoformat()
        updated_intent["check_in"] = fallback
        updated_intent["check_out"] = (
            datetime.strptime(fallback, "%Y-%m-%d").date() + timedelta(days=trip_nights)
        ).isoformat()
        print(f"  ⚠ 날씨 조회 실패, 기본 날짜 설정: {updated_intent['check_in']}")

    return {"candidate_dates": candidates[:3], "intent": updated_intent, "date_fixed": True}


def date_optimizer_node(state: AgentState) -> dict:
    """항공권 최저가 + 날씨를 교차 분석해 최적 여행 날짜 TOP 3를 선정한다.

    점수 기준 (총 13점):
      - 날씨: 맑음(+3) + 적정 기온 18~28°C(+3) + 강수확률 20% 미만(+2) = 최대 8점
      - 가격: 상위 10개 중 순위 기반 0~5점
    """
    intent = state["intent"]
    dest = intent["destination"]
    trip_nights = intent["trip_nights"]
    today = datetime.now().date()

    print(f"\n🗓️  [날짜 최적화] {dest} 항공권 + 날씨 교차 분석 중...")
    iata_dest = get_iata(dest)
    if not iata_dest:
        print(f"  ✗ IATA 코드 없음: '{dest}' — 날씨 기반 추천으로 전환")
        return _weather_only_candidates(dest, trip_nights, today, intent)

    iata_origin = "ICN"
    domestic = iata_is_domestic(iata_dest)
    print(f"  → {iata_origin} → {iata_dest} ({'국내선' if domestic else '국제선'}), {trip_nights}박 기준")

    target_months: list = intent.get("target_months") or []
    if not target_months:
        for i in range(1, 4):
            m = (today.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
            target_months.append(m.strftime("%Y%m"))

    candidate_dates = _make_candidate_dates(target_months, today)
    print(f"  → 후보 날짜 {len(candidate_dates)}개: {candidate_dates[0]} ~ {candidate_dates[-1]}")

    flights = get_cheapest_dates(
        origin=iata_origin,
        destination=iata_dest,
        candidate_dates=candidate_dates,
        trip_nights=trip_nights,
        is_domestic=domestic,
        top_n=10,
    )

    if not flights:
        print("  ✗ 항공권 조회 실패 — 날씨 기반 추천으로 전환")
        return _weather_only_candidates(dest, trip_nights, today, intent)
    print(f"  ✓ 항공권 {len(flights)}건 조회 완료")

    max_price = max(f.price for f in flights)
    min_price = min(f.price for f in flights)
    price_range = max(max_price - min_price, 1)

    candidates = []
    for flight in flights[:10]:
        try:
            w = get_weather(dest, flight.date, silent=True)
        except Exception:
            w = None

        weather_score = 0
        weather_desc = "날씨 조회 불가"
        if w and w.daily:
            d = w.daily
            prob = d.precipitation_probability_max or 0
            temp_max = d.temp_max or 20
            code = d.weather_code or 99
            if code <= 2:
                weather_score += 3
            if 18 <= temp_max <= 28:
                weather_score += 3
            if prob < 20:
                weather_score += 2
            weather_desc = f"최고 {temp_max}°C, 강수확률 {prob}%"

        price_score = round((max_price - flight.price) / price_range * 5, 1)
        total_score = weather_score + price_score

        check_out = (
            datetime.strptime(flight.date, "%Y-%m-%d").date()
            + timedelta(days=trip_nights)
        ).isoformat()

        candidates.append({
            "check_in": flight.date,
            "check_out": check_out,
            "flight_price": flight.price,
            "weather_summary": weather_desc,
            "score": total_score,
            "reason": f"항공 {flight.price:,}원 · {weather_desc}",
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    top3 = candidates[:3]
    print("  ✓ 추천 날짜 TOP 3:")
    for i, c in enumerate(top3, 1):
        print(f"    {i}위) {c['check_in']} ~ {c['check_out']} | 점수 {c['score']} | {c['reason']}")

    best = top3[0]
    updated_intent = dict(intent)
    updated_intent["check_in"] = best["check_in"]
    updated_intent["check_out"] = best["check_out"]

    return {
        "candidate_dates": top3,
        "intent": updated_intent,
        "date_fixed": True,
    }
