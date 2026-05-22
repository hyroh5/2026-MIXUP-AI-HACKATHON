# -*- coding: utf-8 -*-
import sys, os
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

import requests

headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "ko-KR,ko;q=0.9",
    "content-type": "application/json",
    "origin": "https://flight.naver.com",
    "referer": "https://flight.naver.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}
cookie = os.getenv("NAVER_FLIGHT_COOKIE")
if cookie:
    headers["cookie"] = cookie
    print("[쿠키 있음]")
else:
    print("[쿠키 없음]")

payload = {
    "operationName": "GET_RECOMMEND_BY_CITY",
    "variables": {
        "departureLocationCode": "ICN",
        "departureLocationType": "airport",
        "arrivalLocationCode": "CDG",
        "arrivalLocationType": "airport",
        "departureMonths": ["202607"],
        "isDomestic": False,
        "isNonstop": False,
        "tripType": "RT",
    },
    "query": (
        "query GET_RECOMMEND_BY_CITY("
        "$departureLocationCode: String, $departureLocationType: String, "
        "$arrivalLocationCode: String, $arrivalLocationType: String, "
        "$departureMonths: [String!], "
        "$isDomestic: Boolean, $isNonstop: Boolean, $tripType: String"
        ") {\n"
        "  minPricesByDate(\n"
        "    departureLocationCode: $departureLocationCode\n"
        "    departureLocationType: $departureLocationType\n"
        "    arrivalLocationCode: $arrivalLocationCode\n"
        "    arrivalLocationType: $arrivalLocationType\n"
        "    departureMonths: $departureMonths\n"
        "    isDomestic: $isDomestic\n"
        "    isNonstop: $isNonstop\n"
        "    tripType: $tripType\n"
        "  ) {\n"
        "    departureDate returnDate minPrice tripDays stops\n"
        "  }\n"
        "}"
    ),
}

print("POST https://flight-api.naver.com/graphql ...")
try:
    r = requests.post("https://flight-api.naver.com/graphql", headers=headers, json=payload, timeout=10)
    print(f"HTTP {r.status_code}")
    data = r.json()
    rows = (data.get("data") or {}).get("minPricesByDate") or []
    if rows:
        print(f"결과 {len(rows)}개 (5일 기준 필터 전)")
        filtered = [x for x in rows if x.get("tripDays") == 5]
        print(f"5일(4박5일) 결과: {len(filtered)}개")
        for item in filtered[:5]:
            dep = item['departureDate']
            ret = item['returnDate']
            dep_iso = f"{dep[:4]}-{dep[4:6]}-{dep[6:]}"
            ret_iso = f"{ret[:4]}-{ret[4:6]}-{ret[6:]}"
            print(f"  {dep_iso} ~ {ret_iso} | {item['minPrice']:,}원 | 경유 {item['stops']}회")
    else:
        print("결과 없음. 응답 (첫 300자):", str(data)[:300])
except Exception as e:
    print(f"오류: {e}")

print("\n=== get_cheapest_dates 전체 플로우 ===")
from src.cheapest_date.flight_crawler import get_cheapest_dates
results = get_cheapest_dates("ICN", "CDG", ["202607"], [5], top_n=5)
print(f"최종 결과 {len(results)}개:")
for r in results:
    print(f"  {r.date} ~ {r.return_date} | {r.price:,}원 | stops={r.stops}")
