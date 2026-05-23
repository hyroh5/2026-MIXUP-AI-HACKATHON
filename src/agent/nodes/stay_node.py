import json
import os

from langgraph.types import interrupt

from src.agent.state import AgentState
from src.hotel.search import search_google_hotels
from src.hotel.models import HotelSearchRequest, Hotel

HOTEL_BUDGET_RATIO = 0.6

_MOCK_HOTELS = [
    {
        "name": "해운대 그랜드 호텔 (Mock)",
        "address": "부산광역시 해운대구 해운대해변로 20",
        "description": "바다 전망과 조식 포함, 도보로 해운대 해변 접근 가능",
        "image_url": "https://example.com/mock1.jpg",
        "amenities": ["조식", "Wi-Fi", "피트니스", "무료 주차"],
        "details_link": "https://example.com/mock1",
        "cost": 150000,
        "rating": 4.5,
    },
    {
        "name": "파크 하얏트 부산 (Mock)",
        "address": "부산광역시 해운대구 해운대해변로 24",
        "description": "럭셔리 룸과 스파 시설, 도심 최고의 전망 제공",
        "image_url": "https://example.com/mock2.jpg",
        "amenities": ["스파", "실내 수영장", "바/라운지", "컨시어지"],
        "details_link": "https://example.com/mock2",
        "cost": 220000,
        "rating": 4.8,
    },
    {
        "name": "노보텔 앰배서더 부산 (Mock)",
        "address": "부산광역시 해운대구 우동 1411-1",
        "description": "가족 여행에 적합한 객실과 실내 수영장을 갖춘 합리적 가격대 호텔",
        "image_url": "https://example.com/mock3.jpg",
        "amenities": ["실내 수영장", "가족룸", "조식", "무료 Wi-Fi"],
        "details_link": "https://example.com/mock3",
        "cost": 120000,
        "rating": 4.2,
    },
]

# ── Google Hotels 필터 옵션 스키마 ─────────────────────────────────────────────
# 프론트엔드가 이 구조를 그대로 렌더링한다.
# value 값은 SerpAPI google_hotels 파라미터 값과 1:1 대응한다.
HOTEL_PREFS_SCHEMA = [
    {
        "key": "sort_by",
        "label": "정렬 기준",
        "multi": False,
        "options": [
            {"value": 3,  "label": "가격 낮은순"},
            {"value": 8,  "label": "별점 높은순"},
            {"value": 13, "label": "추천순"},
        ],
        "default": 3,
    },
    {
        "key": "min_rating",
        "label": "최소 별점",
        "multi": False,
        "options": [
            {"value": None, "label": "제한 없음"},
            {"value": 7,    "label": "3.5점 이상"},
            {"value": 8,    "label": "4.0점 이상"},
            {"value": 9,    "label": "4.5점 이상"},
        ],
        "default": None,
    },
    {
        "key": "hotel_class",
        "label": "호텔 등급",
        "multi": True,
        "options": [
            {"value": "2", "label": "2성"},
            {"value": "3", "label": "3성"},
            {"value": "4", "label": "4성"},
            {"value": "5", "label": "5성"},
        ],
        "default": [],
    },
    {
        "key": "amenities",
        "label": "원하는 시설",
        "multi": True,
        "options": [
            {"value": 35, "label": "조식 포함"},
            {"value": 9,  "label": "수영장"},
            {"value": 14, "label": "무료 주차"},
            {"value": 4,  "label": "스파"},
            {"value": 12, "label": "헬스장"},
            {"value": 19, "label": "무료 Wi-Fi"},
            {"value": 31, "label": "키즈 프렌들리"},
            {"value": 44, "label": "반려동물 허용"},
        ],
        "default": [],
    },
    {
        "key": "free_cancellation",
        "label": "무료 취소",
        "multi": False,
        "options": [
            {"value": False, "label": "상관없음"},
            {"value": True,  "label": "가능한 곳만"},
        ],
        "default": False,
    },
    {
        "key": "vacation_rentals",
        "label": "숙소 유형",
        "multi": False,
        "options": [
            {"value": False, "label": "호텔만"},
            {"value": True,  "label": "에어비앤비·민박 포함"},
        ],
        "default": False,
    },
]

_PREFS_DEFAULTS: dict = {s["key"]: s["default"] for s in HOTEL_PREFS_SCHEMA}


def _parse_prefs(raw) -> dict:
    """interrupt 응답을 검증·정제해 prefs dict를 반환한다."""
    if not raw:
        return dict(_PREFS_DEFAULTS)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return dict(_PREFS_DEFAULTS)
    if not isinstance(raw, dict):
        return dict(_PREFS_DEFAULTS)
    prefs = dict(_PREFS_DEFAULTS)
    for k in _PREFS_DEFAULTS:
        if k in raw:
            prefs[k] = raw[k]
    return prefs


def _parse_cost(raw: str | None) -> int:
    if not raw:
        return 0
    digits = "".join(filter(str.isdigit, raw))
    cost = int(digits) if digits else 0
    return cost if cost >= 10000 else 0


def search_hotel_candidates(
    intent: dict,
    max_per_night: int,
    prefs: dict | None = None,
    limit: int = 10,
) -> list[dict]:
    """SerpAPI로 사용자 선호 조건이 반영된 호텔 후보를 검색한다. 실패 시 Mock 반환."""
    serpapi_key = os.getenv("SERPAPI_KEY")
    if not serpapi_key:
        print("  ✗ SERPAPI_KEY 없음 → Mock 데이터 사용")
        return _build_mock(intent)

    prefs = prefs or {}
    sort_by: int = prefs.get("sort_by", 3)
    min_rating = prefs.get("min_rating")              # None or int (7/8/9)
    hotel_class_list: list = prefs.get("hotel_class", [])
    amenities_list: list = prefs.get("amenities", [])
    free_cancellation: bool = prefs.get("free_cancellation", False)
    vacation_rentals: bool = prefs.get("vacation_rentals", False)

    # vacation_rentals 모드에서는 hotel_class / amenities / rating 필터가
    # SerpAPI 400 에러를 유발하므로 제거한다
    if vacation_rentals:
        hotel_class_str = None
        amenities_str = None
        min_rating = None
    else:
        hotel_class_str = ",".join(str(c) for c in hotel_class_list) if hotel_class_list else None
        amenities_str = ",".join(str(a) for a in amenities_list) if amenities_list else None

    try:
        req = HotelSearchRequest(
            q=f"{intent['destination']} 호텔",
            check_in_date=intent["check_in"],
            check_out_date=intent["check_out"],
            adults=intent["adults"],
            max_price=max_per_night,
            sort_by=sort_by,
            rating=min_rating,
            hotel_class=hotel_class_str,
            amenities=amenities_str,
            free_cancellation=True if free_cancellation else None,
            vacation_rentals=True if vacation_rentals else None,
            gl="kr", hl="ko", currency="KRW",
        )
        result = search_google_hotels(serpapi_key, req)
        if not result.hotels:
            raise ValueError("검색 결과 없음")

        candidates = []
        nights = max(intent.get("trip_nights", 1), 1)
        for h in result.hotels[:limit]:
            cost = _parse_cost(h.total_rate) if h.total_rate else _parse_cost(h.rate_per_night) * nights
            candidates.append({
                "name": h.name,
                "address": h.address or "",
                "description": h.description or "",
                "image_url": h.thumbnail or "",
                "cost": cost,
                "rating": h.overall_rating or 0.0,
                "amenities": h.amenities[:4],
                "details_link": h.details_link or "",
            })
        return candidates

    except Exception as e:
        print(f"  ✗ SerpApi 실패 ({e}) → Mock 데이터 사용")
        return _build_mock(intent)


def _build_mock(intent: dict) -> list[dict]:
    nights = max(intent.get("trip_nights", 1), 1)
    return [
        {
            "name": h["name"],
            "address": h.get("address", ""),
            "description": h.get("description", ""),
            "image_url": h.get("image_url", ""),
            "amenities": h.get("amenities", []),
            "details_link": h.get("details_link", ""),
            "cost": h["cost"] * nights,
            "rating": h.get("rating", 0.0),
        }
        for h in _MOCK_HOTELS
    ]


def _budget_caps(intent: dict) -> tuple[int, int, int]:
    """(after_flight, max_hotel_total, max_per_night) 계산."""
    budget = intent["budget"]
    nights = max(intent.get("trip_nights", 1), 1)
    flight_cost = intent.get("flight_cost", 0)
    after_flight = budget - flight_cost
    if flight_cost > 0:
        max_hotel_total = max(int(after_flight * 0.9), 0)
    else:
        max_hotel_total = int(budget * HOTEL_BUDGET_RATIO)
    return after_flight, max_hotel_total, max_hotel_total // nights


# ── hotel_prefs: 선호 조건 수집 (interrupt) ───────────────────────────────────

def make_hotel_prefs_node():
    def hotel_prefs_node(state: AgentState) -> dict:
        """사용자에게 Google Hotels 필터 조건을 묻는다.
        선호 호텔이 이미 명시된 경우 interrupt 없이 스킵한다.
        """
        intent = state["intent"]
        if intent.get("preferred_hotel"):
            return {"hotel_prefs": {}}

        print(f"\n🔍 [3-1/5] 숙소 조건 설정 중...")
        raw = interrupt({
            "type": "hotel_prefs",
            "question": "어떤 조건의 숙소를 원하시나요?",
            "schema": HOTEL_PREFS_SCHEMA,
        })
        prefs = _parse_prefs(raw)

        labels = []
        if prefs.get("sort_by", 3) != 3:
            sort_map = {8: "별점높은순", 13: "추천순"}
            labels.append(sort_map.get(prefs["sort_by"], ""))
        if prefs.get("min_rating"):
            labels.append(f"{prefs['min_rating'] * 0.5:.1f}점 이상")
        if prefs.get("hotel_class"):
            labels.append(f"{'·'.join(prefs['hotel_class'])}성")
        amenity_map = {35:"조식",9:"수영장",14:"무료주차",4:"스파",12:"헬스장",19:"WiFi",31:"키즈",44:"반려동물"}
        for a in prefs.get("amenities", []):
            labels.append(amenity_map.get(a, str(a)))
        if prefs.get("free_cancellation"):
            labels.append("무료취소")
        if prefs.get("vacation_rentals"):
            labels.append("에어비앤비포함")

        summary = " | ".join(labels) if labels else "기본값(가격 낮은순, 조건 없음)"
        print(f"  ✓ 조건: {summary}")
        return {"hotel_prefs": prefs}

    return hotel_prefs_node


# ── hotel_compute: API 호출 (interrupt 없음) ──────────────────────────────────

def make_hotel_compute_node():
    def hotel_compute_node(state: AgentState) -> dict:
        intent = state["intent"]
        preferred = intent.get("preferred_hotel")
        budget = intent["budget"]
        nights = max(intent.get("trip_nights", 1), 1)
        adults = intent.get("adults", 1)
        flight_cost = intent.get("flight_cost", 0)

        print(f"\n🏨 [3-2/5] 숙소 검색 중 — {intent['destination']}")
        print(f"  예산 현황: 총 {budget:,}원 | 항공(왕복×{adults}인) {flight_cost:,}원 차감")

        after_flight, max_hotel_total, max_per_night = _budget_caps(intent)

        if preferred:
            print(f"  ✓ 선호 호텔 사용: {preferred}")
            return {
                "hotel_name": preferred,
                "hotel_address": "",
                "hotel_cost": 0,
                "remaining_budget": after_flight,
                "hotel_candidates": [],
            }

        if flight_cost == 0:
            print(f"  △ 항공비 미확정 — 총 예산의 {int(HOTEL_BUDGET_RATIO*100)}%를 숙박 상한으로 설정")
        print(f"  → 숙박 가용 {max_hotel_total:,}원 ({nights}박) → 1박 상한 {max_per_night:,}원")

        prefs = state.get("hotel_prefs") or {}
        candidates = search_hotel_candidates(intent, max_per_night, prefs=prefs, limit=10)
        return {
            "hotel_candidates": candidates,
            "hotel_name": "",
        }

    return hotel_compute_node


# ── hotel_select: 선택 interrupt ──────────────────────────────────────────────

def make_hotel_select_node():
    def hotel_select_node(state: AgentState) -> dict:
        intent = state["intent"]
        candidates = state.get("hotel_candidates", [])
        budget = intent["budget"]
        nights = max(intent.get("trip_nights", 1), 1)

        _, max_hotel_total, max_per_night = _budget_caps(intent)

        choice = interrupt({
            "type": "hotel_selection",
            "question": (
                f"숙소를 선택해주세요 "
                f"(1박 {max_per_night:,}원 이하, {nights}박 총액 {max_hotel_total:,}원 이내):"
            ),
            "candidates": candidates,
        })

        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(candidates)):
                idx = 0
        except (ValueError, TypeError):
            idx = 0

        chosen = candidates[idx]
        flight_cost = intent.get("flight_cost", 0)
        hotel_cost = chosen["cost"]
        remaining = budget - flight_cost - hotel_cost
        print(
            f"  ✓ 선택: {chosen['name']} | 숙박 {hotel_cost:,}원({nights}박) | "
            f"잔여 예산: {budget:,} - {flight_cost:,}(항공) - {hotel_cost:,}(숙박) = {remaining:,}원"
        )

        return {
            "hotel_name": chosen["name"],
            "hotel_address": chosen.get("address", ""),
            "hotel_cost": hotel_cost,
            "remaining_budget": remaining,
        }

    return hotel_select_node
