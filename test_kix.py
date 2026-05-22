# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from src.cheapest_date.flight_crawler import _naver_cheapest_dates, _build_naver_headers, _NAVER_URL, _QUERY
import requests, json

# ── 1. 원본 함수로 테스트 ────────────────────────────────────────────
print("=== _naver_cheapest_dates('ICN', 'KIX', ['202607']) ===")
result = _naver_cheapest_dates('ICN', 'KIX', ['202607'], top_n=5)
print(f"결과 건수: {len(result)}")
for r in result[:3]:
    print(f"  {r.date} | {r.price:,}원 | stops={r.stops} | airline={r.airline_codes}")

# ── 2. raw 응답 확인 ─────────────────────────────────────────────────
print("\n=== raw 응답 확인 ===")
headers = _build_naver_headers()
payload = {
    "operationName": "GET_RECOMMEND_BY_CITY",
    "variables": {
        "departureLocationCode": "ICN",
        "departureLocationType": "airport",
        "arrivalLocationCode": "KIX",
        "arrivalLocationType": "airport",
        "departureMonths": ["202607"],
        "isDomestic": False,
        "isNonstop": False,
        "tripType": "RT",
    },
    "query": _QUERY,
}
try:
    res = requests.post(_NAVER_URL, headers=headers, json=payload, timeout=10)
    print(f"HTTP {res.status_code}")
    data = res.json()
    rows = (data.get("data") or {}).get("minPricesByDate") or []
    print(f"minPricesByDate 건수: {len(rows)}")
    if rows:
        from collections import Counter
        print("tripDays 분포:", dict(sorted(Counter(x.get("tripDays") for x in rows).items())))
        print("첫 3건:", [(x["departureDate"], x["minPrice"], x.get("tripDays")) for x in rows[:3]])
    else:
        print("data 내용:", str(data)[:500])
except Exception as e:
    print(f"오류: {e}")

# ── 3. 도착지 타입을 'city'로 변경해서 시도 ──────────────────────────
print("\n=== arrivalLocationType='city' 시도 ===")
payload2 = dict(payload)
payload2["variables"] = dict(payload["variables"])
payload2["variables"]["arrivalLocationType"] = "city"
try:
    res2 = requests.post(_NAVER_URL, headers=headers, json=payload2, timeout=10)
    print(f"HTTP {res2.status_code}")
    data2 = res2.json()
    rows2 = (data2.get("data") or {}).get("minPricesByDate") or []
    print(f"minPricesByDate 건수: {len(rows2)}")
    if rows2:
        print("첫 3건:", [(x["departureDate"], x["minPrice"], x.get("tripDays")) for x in rows2[:3]])
    else:
        print("data 내용:", str(data2)[:300])
except Exception as e:
    print(f"오류: {e}")

# ── 4. IATA 코드 대신 도시 코드로 시도 (OSA = 오사카 도시 코드) ──────
print("\n=== arrivalLocationCode='OSA' (오사카 도시코드) 시도 ===")
payload3 = dict(payload)
payload3["variables"] = dict(payload["variables"])
payload3["variables"]["arrivalLocationCode"] = "OSA"
payload3["variables"]["arrivalLocationType"] = "city"
try:
    res3 = requests.post(_NAVER_URL, headers=headers, json=payload3, timeout=10)
    print(f"HTTP {res3.status_code}")
    data3 = res3.json()
    rows3 = (data3.get("data") or {}).get("minPricesByDate") or []
    print(f"minPricesByDate 건수: {len(rows3)}")
    if rows3:
        print("첫 3건:", [(x["departureDate"], x["minPrice"], x.get("tripDays")) for x in rows3[:3]])
except Exception as e:
    print(f"오류: {e}")
