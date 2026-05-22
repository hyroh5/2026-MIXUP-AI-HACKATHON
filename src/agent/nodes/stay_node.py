import os

from src.agent.state import AgentState
from src.hotel.search import search_google_hotels
from src.hotel.models import HotelSearchRequest, Hotel


_MOCK_HOTEL = {
    "name": "부산 해운대 그랜드 호텔 (Mock)",
    "address": "부산광역시 해운대구 해운대해변로 20",
    "cost": 150000,
}


def stay_node(state: AgentState) -> dict:
    intent = state["intent"]
    serpapi_key = os.getenv("SERPAPI_KEY")

    print(f"\n🏨 [3/5] 숙소 검색 중 — {intent['destination']} {intent['check_in']} ~ {intent['check_out']}")

    if not serpapi_key:
        print("  ✗ SERPAPI_KEY 없음 → Mock 데이터 사용")
        cost = _MOCK_HOTEL["cost"]
        return {
            "hotel_name": _MOCK_HOTEL["name"],
            "hotel_address": _MOCK_HOTEL["address"],
            "hotel_cost": cost,
            "remaining_budget": intent["budget"] - cost,
        }

    try:
        req = HotelSearchRequest(
            q=f"{intent['destination']} 호텔",
            check_in_date=intent["check_in"],
            check_out_date=intent["check_out"],
            adults=intent["adults"],
            gl="kr", hl="ko", currency="KRW", sort_by=3,
        )
        result = search_google_hotels(serpapi_key, req)
        if not result.hotels:
            raise ValueError("검색 결과 없음")

        hotel: Hotel = result.hotels[0]
        raw_cost = hotel.total_rate or hotel.rate_per_night or "0"
        digits = "".join(filter(str.isdigit, raw_cost))
        cost = int(digits) if digits else 0
        if cost < 10000:
            cost = 0

        print(f"  ✓ {hotel.name} | 원본 가격 문자열: '{raw_cost}' → {cost:,}원 | 잔여: {intent['budget']-cost:,}원")
        return {
            "hotel_name": hotel.name,
            "hotel_address": "",
            "hotel_cost": cost,
            "remaining_budget": intent["budget"] - cost,
        }
    except Exception as e:
        print(f"  ✗ SerpApi 실패 ({e}) → Mock 데이터 사용")
        cost = _MOCK_HOTEL["cost"]
        return {
            "hotel_name": _MOCK_HOTEL["name"],
            "hotel_address": _MOCK_HOTEL["address"],
            "hotel_cost": cost,
            "remaining_budget": intent["budget"] - cost,
        }
