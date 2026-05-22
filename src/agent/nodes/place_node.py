from src.agent.state import AgentState
from src.tourist.naver_local import search_local
from src.cheapest_date.iata import get_iata, is_domestic as iata_is_domestic


_MOCK_RESTAURANTS = [
    {"title": "해운대 암소갈비집 (Mock)", "address": "부산 해운대구 구남로 35", "category": "한식"},
    {"title": "광안리 횟집 (Mock)", "address": "부산 수영구 광안해변로 219", "category": "해산물"},
]
_MOCK_ATTRACTIONS = [
    {"title": "해운대해수욕장 (Mock)", "address": "부산 해운대구 우동", "category": "관광명소"},
    {"title": "해동용궁사 (Mock)", "address": "부산 기장군 기장읍 용궁길 86", "category": "사찰"},
]


def place_node(state: AgentState) -> dict:
    """국내 → Naver Local API / 해외 → Google Places API 자동 분기."""
    intent = state["intent"]
    dest = intent["destination"]
    is_rainy = state.get("is_rainy", False)

    iata = get_iata(dest)
    domestic = iata_is_domestic(iata) if iata else False

    print(f"\n📍 [4/5] 장소 검색 중 — {dest} ({'국내→Naver' if domestic else '해외→Google Places'})")

    if domestic:
        r_query = f"{dest} 맛집"
        a_query = f"{dest} 카페 박물관" if is_rainy else f"{dest} 명소 관광지"

        def _naver(places):
            return [
                {"title": p.title, "address": p.road_address or p.address, "category": p.category}
                for p in places[:2]
            ]

        print(f"  → 맛집: '{r_query}' / 명소: '{a_query}'")
        try:
            restaurants = _naver(search_local(r_query, display=2))
        except Exception as e:
            print(f"  ✗ 맛집 Naver 실패 ({e}) → Mock 사용")
            restaurants = _MOCK_RESTAURANTS

        try:
            attractions = _naver(search_local(a_query, display=2))
        except Exception as e:
            print(f"  ✗ 명소 Naver 실패 ({e}) → Mock 사용")
            attractions = _MOCK_ATTRACTIONS

    else:
        from src.tourist.google_places import search_places

        r_query = f"{dest} best restaurants"
        a_query = f"{dest} indoor museum cafe" if is_rainy else f"{dest} tourist attractions"

        def _google(places):
            return [
                {"title": p.name, "address": p.address, "category": ""}
                for p in places[:2]
            ]

        print(f"  → 맛집: '{r_query}' / 명소: '{a_query}'")
        try:
            restaurants = _google(search_places(r_query))
        except Exception as e:
            print(f"  ✗ 맛집 Google Places 실패 ({e})")
            restaurants = []

        try:
            attractions = _google(search_places(a_query))
        except Exception as e:
            print(f"  ✗ 명소 Google Places 실패 ({e})")
            attractions = []

    print(f"  ✓ 맛집: {[r['title'] for r in restaurants]}")
    print(f"  ✓ 명소: {[a['title'] for a in attractions]}")
    return {"restaurants": restaurants, "attractions": attractions}
