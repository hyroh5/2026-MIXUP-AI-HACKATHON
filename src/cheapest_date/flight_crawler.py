# -*- coding: utf-8 -*-
"""네이버 항공권 GraphQL API (primary) + SerpAPI Google Flights (fallback)로 날짜별 최저가를 조회한다."""

import os
from datetime import datetime, timedelta, date as date_cls

import requests

from .models import FlightPrice

_NAVER_URL = "https://flight-api.naver.com/graphql"
_SERPAPI_URL = "https://serpapi.com/search.json"

_QUERY = (
    "query GET_RECOMMEND_BY_CITY("
    "$departureLocationCode: String, $departureLocationType: String, "
    "$arrivalLocationCode: String, $arrivalLocationType: String, "
    "$continentIds: [Int!], $countryCodes: [String!], "
    "$departureDate: String, $returnDate: String, "
    "$departureMonths: [String!], $duration: [Int!], "
    "$isDomestic: Boolean, $isMappable: Boolean, $isNonstop: Boolean, "
    "$price: [Int!], $timeCategories: [DepartureTimeCategory!], "
    "$themeIds: [Int!], $tripDays: [Int!], $tripType: String"
    ") {\n"
    "  minPricesByDate(\n"
    "    departureLocationCode: $departureLocationCode\n"
    "    departureLocationType: $departureLocationType\n"
    "    arrivalLocationCode: $arrivalLocationCode\n"
    "    arrivalLocationType: $arrivalLocationType\n"
    "    continentIds: $continentIds\n"
    "    countryCodes: $countryCodes\n"
    "    departureDate: $departureDate\n"
    "    returnDate: $returnDate\n"
    "    departureMonths: $departureMonths\n"
    "    duration: $duration\n"
    "    isDomestic: $isDomestic\n"
    "    isMappable: $isMappable\n"
    "    isNonstop: $isNonstop\n"
    "    price: $price\n"
    "    themeIds: $themeIds\n"
    "    timeCategories: $timeCategories\n"
    "    tripDays: $tripDays\n"
    "    tripType: $tripType\n"
    "  ) {\n"
    "    departureLocation { iataCode cityName popularity __typename }\n"
    "    arrivalLocation { iataCode cityName popularity __typename }\n"
    "    departureDate\n"
    "    airlineCodes\n"
    "    duration\n"
    "    isDomestic\n"
    "    minPrice\n"
    "    returnDate\n"
    "    stops\n"
    "    timeCategory\n"
    "    tripDays\n"
    "    tripType\n"
    "    __typename\n"
    "  }\n"
    "}"
)


def _build_naver_headers() -> dict:
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ko-KR,ko;q=0.9",
        "content-type": "application/json",
        "origin": "https://flight.naver.com",
        "referer": "https://flight.naver.com/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    }
    cookie = os.getenv("NAVER_FLIGHT_COOKIE")
    if cookie:
        headers["cookie"] = cookie
    return headers


def _to_iso(date_str: str) -> str:
    """'20260525' → '2026-05-25'"""
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"


def _naver_cheapest_dates(
    origin: str,
    destination: str,
    months: list[str],
    trip_days: list[int],
    is_nonstop: bool = False,
    top_n: int = 50,
    origin_type: str = "airport",
    destination_type: str = "airport",
) -> list[FlightPrice]:
    """네이버 GraphQL minPricesByDate로 전체 월 날짜별 최저가를 단건 호출로 조회한다."""
    payload = {
        "operationName": "GET_RECOMMEND_BY_CITY",
        "variables": {
            "departureLocationCode": origin,
            "departureLocationType": origin_type,
            "arrivalLocationCode": destination,
            "arrivalLocationType": destination_type,
            "departureMonths": months,
            "isDomestic": False,
            "isNonstop": is_nonstop,
            "tripType": "RT",
        },
        "query": _QUERY,
    }
    try:
        res = requests.post(_NAVER_URL, headers=_build_naver_headers(), json=payload, timeout=10)
        res.raise_for_status()
    except requests.RequestException as e:
        print(f"  [flight] 네이버 요청 실패: {e}")
        return []

    raw = res.json().get("data", {}).get("minPricesByDate") or []
    results = [
        FlightPrice(
            date=_to_iso(item["departureDate"]),
            return_date=_to_iso(item["returnDate"]),
            price=item["minPrice"],
            stops=item.get("stops", 0),
            duration=item.get("duration", 0),
            airline_codes=item.get("airlineCodes", []),
            trip_days=item.get("tripDays", 0),
        )
        for item in raw
        if item.get("minPrice") and item.get("tripDays") in trip_days
    ]
    results.sort(key=lambda f: f.price)
    return results[:top_n]


def _serpapi_cheapest_dates(
    origin: str,
    destination: str,
    months: list[str],
    trip_nights: int,
    top_n: int = 10,
    api_key: str | None = None,
) -> list[FlightPrice]:
    """SerpAPI google_flights로 months에서 생성한 후보 날짜별 왕복 최저가를 조회한다. (fallback)"""
    key = api_key or os.getenv("SERPAPI_KEY")
    if not key:
        return []

    today = date_cls.today()
    candidate_dates: list[str] = []
    for month_str in months:
        year, month = int(month_str[:4]), int(month_str[4:])
        d = date_cls(year, month, 1)
        while d.month == month and len(candidate_dates) < 8:
            if (d - today).days > 7:
                candidate_dates.append(d.isoformat())
            d += timedelta(days=4)

    if not candidate_dates:
        return []

    results = []
    for outbound in candidate_dates:
        return_date = (
            datetime.strptime(outbound, "%Y-%m-%d") + timedelta(days=trip_nights)
        ).strftime("%Y-%m-%d")
        price = _serpapi_fetch_price(origin, destination, outbound, return_date, key)
        if price:
            results.append(FlightPrice(
                date=outbound,
                return_date=return_date,
                price=price,
                trip_days=trip_nights + 1,
            ))

    results.sort(key=lambda f: f.price)
    return results[:top_n]


def _serpapi_fetch_price(
    origin: str,
    destination: str,
    outbound_date: str,
    return_date: str,
    api_key: str,
) -> int | None:
    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": outbound_date,
        "return_date": return_date,
        "currency": "KRW",
        "hl": "en",
        "api_key": api_key,
    }
    try:
        resp = requests.get(_SERPAPI_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        lowest = data.get("price_insights", {}).get("lowest_price")
        if lowest:
            return int(lowest)
        for key_name in ("best_flights", "other_flights"):
            flights = data.get(key_name, [])
            if flights and flights[0].get("price"):
                return int(flights[0]["price"])
    except Exception as e:
        print(f"    ✗ {outbound_date}: {e}")
    return None


def get_cheapest_dates(
    origin: str,
    destination: str,
    months: list[str],
    trip_days: list[int],
    is_nonstop: bool = False,
    top_n: int = 50,
    origin_type: str = "airport",
    destination_type: str = "airport",
) -> list[FlightPrice]:
    """네이버 항공권 API (primary) → SerpAPI (fallback)로 날짜별 최저가를 조회한다.

    Args:
        origin:      출발 공항 IATA 코드 (예: 'ICN')
        destination: 도착 공항 IATA 코드 (예: 'LHR')
        months:      조회 월 목록 (예: ['202607'])
        trip_days:   여행 일수 목록 (예: [5] → 4박5일)
        is_nonstop:  직항만 조회 여부
        top_n:       최대 반환 수

    Returns:
        가격 오름차순 FlightPrice 리스트.
    """
    print(f"  → 네이버 항공권 API 조회 중 (월: {months}, {trip_days}일)...")
    results = _naver_cheapest_dates(
        origin, destination, months, trip_days, is_nonstop, top_n, origin_type, destination_type
    )

    if results:
        print(f"  ✓ 네이버 API: {len(results)}개 날짜, 최저 {results[0].price:,}원 ({results[0].date})")
        return results

    print("  ✗ 네이버 API 빈 응답 → SerpAPI fallback 시도...")
    trip_nights = max(trip_days) - 1 if trip_days else 4
    results = _serpapi_cheapest_dates(origin, destination, months, trip_nights, min(top_n, 10))

    if results:
        print(f"  ✓ SerpAPI fallback: {len(results)}개 날짜 조회 완료")
    else:
        print("  ✗ SerpAPI fallback도 실패")

    return results
