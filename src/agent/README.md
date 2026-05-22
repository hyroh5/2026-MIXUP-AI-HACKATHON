# Travel Planner Agent — LangGraph 구조

자연어 입력 하나로 목적지·날짜·숙소·장소를 자동 수집하고 여행 일정을 생성하는 6-노드 LangGraph 에이전트입니다.

---

## 그래프 흐름

```
                    ┌─────────────────────────────────────────┐
                    │                                         │
START ──► intent_router ──[날짜 확정]──► weather ──► stay ──► place ──► synthesizer ──► END
                    │
                    └──[날짜 미정]──► date_optimizer ──► weather ──► (위와 동일)
```

| 조건 | 경로 |
|---|---|
| 날짜가 명시된 경우 | `intent_router → weather → stay → place → synthesizer` |
| 날짜가 미정/월만 언급된 경우 | `intent_router → date_optimizer → weather → stay → place → synthesizer` |

---

## 노드 설명

### 1. `intent_router` — 의도 분석
**파일:** `nodes/intent_router.py`

사용자의 자연어 입력을 LLM(Solar Pro3)으로 분석해 여행 파라미터를 추출합니다.

**출력:**
- `intent`: 목적지, 체크인/아웃, 예산, 인원, 숙박 일수, 대상 월
- `date_fixed`: 날짜 확정 여부 (조건부 라우팅 키)

**라우팅 규칙:**
- `date_fixed=True` → `weather` 노드로
- `date_fixed=False` → `date_optimizer` 노드로

---

### 2. `date_optimizer` — 날짜 최적화
**파일:** `nodes/date_optimizer.py`

항공권 최저가와 날씨 데이터를 교차 분석해 최적 여행 날짜 TOP 3를 선정합니다.

**점수 산정 (최대 13점):**
| 항목 | 조건 | 점수 |
|---|---|---|
| 날씨 맑음 | weather_code ≤ 2 | +3 |
| 적정 기온 | 18°C ≤ 최고기온 ≤ 28°C | +3 |
| 낮은 강수확률 | 강수확률 < 20% | +2 |
| 항공 가격 | 상위 10개 순위 기반 | 0 ~ 5 |

**폴백:** 항공 API 실패 시 날씨 점수만으로 추천 (`_weather_only_candidates`)

**출력:**
- `candidate_dates`: TOP 3 날짜 후보 (`check_in`, `check_out`, `flight_price`, `score`, `reason`)
- `intent`: 1위 날짜로 업데이트된 intent
- `date_fixed`: True (이후 노드에서 날짜 확정 처리)

---

### 3. `weather_node` — 날씨 조회
**파일:** `nodes/weather_node.py`

체크인부터 체크아웃까지 전 기간의 일별 날씨를 Open-Meteo API로 조회합니다.

**출력:**
- `is_rainy`: 기간 중 강수 여부 (장소 검색 쿼리 분기에 사용)
- `weather_summary`: 날짜별 최고/최저기온·강수확률·강우량 텍스트

---

### 4. `stay_node` — 숙소 검색
**파일:** `nodes/stay_node.py`

SerpAPI Google Hotels를 통해 목적지·날짜·인원 조건에 맞는 숙소를 검색합니다.

**폴백:** `SERPAPI_KEY` 없거나 검색 실패 시 Mock 데이터 사용

**출력:**
- `hotel_name`, `hotel_address`, `hotel_cost`
- `remaining_budget`: 예산 − 숙박비

---

### 5. `place_node` — 장소 검색
**파일:** `nodes/place_node.py`

국내/해외 여부에 따라 다른 API를 사용해 맛집·명소를 검색합니다.

| 구분 | API |
|---|---|
| 국내 | Naver Local Search API |
| 해외 | Google Places API |

**날씨 분기:** `is_rainy=True`이면 실내 장소(카페·박물관) 위주로 쿼리 조정

**출력:**
- `restaurants`: 맛집 목록 (title, address, category)
- `attractions`: 명소 목록 (title, address, category)

---

### 6. `synthesizer_node` — 일정 합성
**파일:** `nodes/synthesizer_node.py`

수집된 모든 정보(숙소·맛집·명소·날씨·예산)를 LLM에 전달해 최종 여행 일정 마크다운을 생성합니다.

**출력:**
- `final_report`: 한국어 마크다운 여행 일정 (예산 현황·날씨·동선 포함)

---

## 파일 구조

```
src/agent/
├── graph.py              # 그래프 조립 및 컴파일
├── state.py              # AgentState, TravelIntent TypedDict 정의
├── llm.py                # LLM 인스턴스 팩토리 (get_llm)
└── nodes/
    ├── __init__.py
    ├── intent_router.py   # Node 1: 의도 분석 (LLM 사용)
    ├── date_optimizer.py  # Node 2: 날짜 최적화 (항공+날씨 교차)
    ├── weather_node.py    # Node 3: 날씨 조회
    ├── stay_node.py       # Node 4: 숙소 검색
    ├── place_node.py      # Node 5: 장소 검색 (국내/해외 분기)
    └── synthesizer_node.py # Node 6: 일정 합성 (LLM 사용)
```

---

## 외부 API 의존성

| API | 용도 | 환경변수 |
|---|---|---|
| Upstage Solar Pro3 | intent 추출, 일정 합성 | `UPSTAGE_API_KEY` |
| Open-Meteo | 날씨 예보 | — (무료) |
| SerpAPI Google Hotels | 숙소 검색 | `SERPAPI_KEY` |
| Naver Local Search | 국내 맛집·명소 | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` |
| Google Places | 해외 맛집·명소 | `GOOGLE_PLACES_API_KEY` |
| 항공권 크롤러 | 최저가 날짜 탐색 | — |

---

## AgentState 필드 요약

```python
class AgentState(TypedDict):
    messages: list            # 대화 메시지
    intent: TravelIntent      # 여행 파라미터
    date_fixed: bool          # 날짜 확정 여부
    candidate_dates: list     # 날짜 최적화 TOP 3 결과
    is_rainy: bool            # 우천 여부
    weather_summary: str      # 일별 날씨 텍스트
    hotel_name: str
    hotel_address: str
    hotel_cost: int
    remaining_budget: int
    restaurants: list
    attractions: list
    final_report: str         # 최종 여행 일정 마크다운
```
