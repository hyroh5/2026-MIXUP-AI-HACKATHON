import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.state import AgentState
from src.cheapest_date.iata import get_iata, is_domestic as iata_is_domestic


# ──────────────────────────────────────────────
# 박수 → 목표 장소 수
# ──────────────────────────────────────────────

def _place_counts(trip_nights: int) -> tuple[int, int]:
    """(맛집 목표 수, 명소 목표 수) 반환."""
    n = max(1, trip_nights)
    r = min(n + 1, 6)       # 맛집: 2~6
    a = min(n * 2 + 1, 10)  # 명소: 3~10 (하루 2곳 페이스)
    return r, a


# ──────────────────────────────────────────────
# 검색 쿼리 풀
# ──────────────────────────────────────────────

def _build_queries(
    dest: str, trip_nights: int, is_rainy: bool, domestic: bool
) -> tuple[list[str], list[str]]:
    """(맛집 쿼리 목록, 명소 쿼리 목록) 반환 — 최대 6/10개."""
    n = max(1, trip_nights)

    if domestic:
        r_pool = [
            f"{dest} 맛집 추천",
            f"{dest} 카페 브런치",
            f"{dest} 저녁 식당",
            f"{dest} 향토 음식 로컬 맛집",
            f"{dest} 해산물 고기 맛집",
            f"{dest} 고급 레스토랑 파인다이닝",
        ]
        a_pool_clear = [
            f"{dest} 관광명소",
            f"{dest} 자연 경관 뷰포인트",
            f"{dest} 야경 명소",
            f"{dest} 박물관 미술관",
            f"{dest} 쇼핑 거리 전통시장",
            f"{dest} 역사 유적지 문화재",
            f"{dest} 체험 액티비티",
            f"{dest} 공원 산책로",
            f"{dest} 테마파크 놀이공원",
            f"{dest} 온천 스파",
        ]
        a_pool_rainy = [
            f"{dest} 실내 박물관 미술관",
            f"{dest} 실내 카페 디저트",
            f"{dest} 쇼핑몰 백화점",
            f"{dest} 수족관 아쿠아리움",
            f"{dest} 실내 전시회 갤러리",
            f"{dest} 영화관 공연장 뮤지컬",
            f"{dest} 찜질방 스파 온천",
            f"{dest} 실내 체험관",
            f"{dest} 실내 놀이시설",
            f"{dest} 전통 문화 체험관",
        ]
    else:
        r_pool = [
            f"{dest} best local restaurants",
            f"{dest} cafes brunch spots",
            f"{dest} dinner restaurants",
            f"{dest} local street food",
            f"{dest} seafood traditional cuisine",
            f"{dest} fine dining rooftop",
        ]
        a_pool_clear = [
            f"{dest} tourist attractions",
            f"{dest} historical landmarks",
            f"{dest} parks gardens viewpoints",
            f"{dest} local neighborhoods walking",
            f"{dest} markets bazaars",
            f"{dest} outdoor adventure activities",
            f"{dest} beaches waterfront",
            f"{dest} religious sites temples",
            f"{dest} art districts",
            f"{dest} nightlife entertainment",
        ]
        a_pool_rainy = [
            f"{dest} museums",
            f"{dest} art galleries",
            f"{dest} indoor shopping malls",
            f"{dest} aquarium",
            f"{dest} theaters concert halls",
            f"{dest} spas wellness centers",
            f"{dest} indoor markets",
            f"{dest} historical indoor sites",
            f"{dest} escape rooms entertainment",
            f"{dest} cooking classes workshops",
        ]

    r_count, a_count = _place_counts(n)
    a_pool = a_pool_rainy if is_rainy else a_pool_clear
    return r_pool[:r_count], a_pool[:a_count]


# ──────────────────────────────────────────────
# 병렬 API 호출
# ──────────────────────────────────────────────

def _search_parallel_naver(queries: list[str], display: int = 3) -> list[dict]:
    """Naver Local API 병렬 호출 → 중복 제거된 후보 목록."""
    from src.tourist.naver_local import search_local

    seen: set[str] = set()
    results: list[dict] = []

    def _fetch(q: str) -> list[dict]:
        places = search_local(q, display=display)
        return [
            {
                "title": p.title,
                "address": p.road_address or p.address,
                "category": p.category,
            }
            for p in places
        ]

    with ThreadPoolExecutor(max_workers=min(len(queries), 5)) as ex:
        futures = {ex.submit(_fetch, q): q for q in queries}
        for fut in as_completed(futures):
            try:
                for item in fut.result():
                    key = item["title"]
                    if key not in seen:
                        seen.add(key)
                        results.append(item)
            except Exception as e:
                print(f"  ✗ Naver 검색 실패 ({futures[fut]}): {e}")

    return results


def _search_parallel_google(queries: list[str]) -> list[dict]:
    """Google Places API 병렬 호출 → 중복 제거된 후보 목록."""
    from src.tourist.google_places import search_places

    seen: set[str] = set()
    results: list[dict] = []

    def _fetch(q: str) -> list[dict]:
        places = search_places(q)
        return [{"title": p.name, "address": p.address, "category": ""} for p in places]

    with ThreadPoolExecutor(max_workers=min(len(queries), 5)) as ex:
        futures = {ex.submit(_fetch, q): q for q in queries}
        for fut in as_completed(futures):
            try:
                for item in fut.result():
                    key = item["title"]
                    if key not in seen:
                        seen.add(key)
                        results.append(item)
            except Exception as e:
                print(f"  ✗ Google Places 검색 실패 ({futures[fut]}): {e}")

    return results


# ──────────────────────────────────────────────
# LLM 큐레이션
# ──────────────────────────────────────────────

def _curate_with_llm(
    llm,
    dest: str,
    trip_nights: int,
    is_rainy: bool,
    hotel_name: str,
    hotel_address: str,
    raw_r: list[dict],
    raw_a: list[dict],
    r_count: int,
    a_count: int,
) -> dict:
    weather_note = (
        "비 또는 눈이 내립니다. 실내 명소를 최우선으로 선택하고, 실외 장소는 꼭 필요한 경우에만 포함하세요."
        if is_rainy
        else "날씨가 좋습니다. 실내·실외 장소를 균형 있게 선택하세요."
    )

    def _fmt(places: list[dict]) -> str:
        if not places:
            return "  (검색 결과 없음)"
        return "\n".join(
            f"  - {p['title']} | {p.get('address', '')} | {p.get('category', '')}"
            for p in places
        )

    system = SystemMessage(content=(
        "너는 전문 여행 큐레이터야. 제공된 장소 후보 목록에서 여행 일정에 최적인 장소를 선별해줘.\n"
        "선별 기준:\n"
        "1. 박수와 동선을 고려해 딱 맞는 수만 선택 (더 많지도 적지도 않게)\n"
        "2. 카테고리 중복 최소화 (같은 유형 장소가 연속으로 나오지 않도록)\n"
        "3. 날씨 지시에 따라 실내/실외 비율 조절\n"
        "4. 숙소에서 이동이 효율적인 동선 우선\n\n"
        "반드시 아래 JSON 형식만 출력 (설명 없이):\n"
        '{"restaurants":[{"title":"...","address":"...","category":"...","description":"한 줄 소개"}],'
        '"attractions":[{"title":"...","address":"...","category":"...","description":"한 줄 소개"}]}'
    ))

    user_content = (
        f"목적지: {dest}\n"
        f"일정: {trip_nights}박\n"
        f"날씨: {weather_note}\n"
        f"숙소: {hotel_name} / {hotel_address}\n\n"
        f"[맛집·카페 후보] → {r_count}곳 선별 필요\n{_fmt(raw_r)}\n\n"
        f"[명소·체험 후보] → {a_count}곳 선별 필요\n{_fmt(raw_a)}\n\n"
        f"위 후보에서 정확히 맛집 {r_count}곳, 명소 {a_count}곳을 선별하고 "
        "각 장소마다 한 줄 소개(description)와 적절한 카테고리를 작성해줘."
    )

    response = llm.invoke([system, HumanMessage(content=user_content)])
    raw = response.content.strip()
    if "```" in raw:
        raw = raw.split("```")[1].strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

    return json.loads(raw)


# ──────────────────────────────────────────────
# Mock 폴백
# ──────────────────────────────────────────────

_MOCK_RESTAURANTS = [
    {"title": "현지 맛집 1 (Mock)", "address": "목적지 중심가", "category": "한식", "description": "현지인이 즐겨 찾는 대표 맛집"},
    {"title": "현지 카페 (Mock)", "address": "목적지 중심가", "category": "카페", "description": "분위기 좋은 로컬 카페"},
    {"title": "해산물 식당 (Mock)", "address": "목적지 해안가", "category": "해산물", "description": "신선한 해산물 전문점"},
]
_MOCK_ATTRACTIONS = [
    {"title": "대표 관광지 (Mock)", "address": "목적지 중심", "category": "관광명소", "description": "현지 대표 관광 명소"},
    {"title": "박물관 (Mock)", "address": "목적지 중심", "category": "박물관", "description": "지역 역사와 문화를 담은 박물관"},
    {"title": "자연 경관 (Mock)", "address": "목적지 외곽", "category": "자연", "description": "아름다운 자연 경관"},
    {"title": "쇼핑 거리 (Mock)", "address": "목적지 중심가", "category": "쇼핑", "description": "다양한 기념품과 로컬 상점"},
]


def _mock_for(r_count: int, a_count: int) -> tuple[list[dict], list[dict]]:
    r = (_MOCK_RESTAURANTS * 3)[:r_count]
    a = (_MOCK_ATTRACTIONS * 3)[:a_count]
    return r, a


# ──────────────────────────────────────────────
# Node 팩토리
# ──────────────────────────────────────────────

def make_place_node(llm):
    def place_node(state: AgentState) -> dict:
        intent = state["intent"]
        dest = intent["destination"]
        trip_nights = intent.get("trip_nights", 2)
        is_rainy = state.get("is_rainy", False)
        hotel_name = state.get("hotel_name", "")
        hotel_address = state.get("hotel_address", "")

        iata = get_iata(dest)
        domestic = iata_is_domestic(iata) if iata else False

        r_count, a_count = _place_counts(trip_nights)
        r_queries, a_queries = _build_queries(dest, trip_nights, is_rainy, domestic)

        api_label = "국내→Naver" if domestic else "해외→Google Places"
        weather_label = "☔ 실내 우선" if is_rainy else "☀ 실내·실외 균형"
        print(f"\n📍 [4/5] 장소 검색 중 — {dest} ({api_label}) | {trip_nights}박 | {weather_label}")
        print(f"  → 목표: 맛집 {r_count}곳 ({len(r_queries)}개 쿼리), 명소 {a_count}곳 ({len(a_queries)}개 쿼리)")

        # API 병렬 검색
        try:
            if domestic:
                raw_r = _search_parallel_naver(r_queries, display=3)
                raw_a = _search_parallel_naver(a_queries, display=3)
            else:
                raw_r = _search_parallel_google(r_queries)
                raw_a = _search_parallel_google(a_queries)
            print(f"  ✓ 수집된 후보: 맛집 {len(raw_r)}곳, 명소 {len(raw_a)}곳")
        except Exception as e:
            print(f"  ✗ API 검색 전체 실패 ({e}) → Mock 사용")
            raw_r, raw_a = _mock_for(r_count, a_count)

        # LLM 큐레이션
        if raw_r or raw_a:
            try:
                print(f"  → LLM 큐레이션 중...")
                curated = _curate_with_llm(
                    llm, dest, trip_nights, is_rainy,
                    hotel_name, hotel_address,
                    raw_r, raw_a, r_count, a_count,
                )
                restaurants = curated.get("restaurants", [])[:r_count]
                attractions = curated.get("attractions", [])[:a_count]

                # 부족한 경우 raw로 보충
                if len(restaurants) < r_count:
                    restaurants += raw_r[len(restaurants):r_count]
                if len(attractions) < a_count:
                    attractions += raw_a[len(attractions):a_count]

            except Exception as e:
                print(f"  ✗ LLM 큐레이션 실패 ({e}) → 수집 결과 직접 사용")
                restaurants = raw_r[:r_count]
                attractions = raw_a[:a_count]
        else:
            restaurants, attractions = _mock_for(r_count, a_count)

        print(f"  ✓ 맛집: {[r['title'] for r in restaurants]}")
        print(f"  ✓ 명소: {[a['title'] for a in attractions]}")
        return {"restaurants": restaurants, "attractions": attractions}

    return place_node
