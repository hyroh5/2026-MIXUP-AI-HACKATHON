# -*- coding: utf-8 -*-
"""날씨 데이터 콘솔 출력 포맷 (핵심 정보만 한 줄 요약)"""

from .config import WMO_CODES
from .models import DailyWeather


def _fmt(value, unit: str = "", fmt: str = ".1f") -> str:
    return f"{value:{fmt}}{unit}" if value is not None else "N/A"


def print_daily(weather: DailyWeather, source_label: str) -> None:
    """DailyWeather 핵심 정보를 한 줄로 출력한다."""
    import datetime

    if weather.temp_max is None and weather.weather_code is None:
        print(f"  {weather.date} 데이터 없음")
        return

    try:
        d = datetime.date.fromisoformat(weather.date)
        date_str = d.strftime("%Y-%m-%d")
    except ValueError:
        date_str = weather.date

    desc = ""
    if weather.weather_code is not None:
        desc = WMO_CODES.get(int(weather.weather_code), f"WMO {weather.weather_code}")

    parts = [
        f"[{date_str}]",
        f"최고 {_fmt(weather.temp_max, '°C')} / 최저 {_fmt(weather.temp_min, '°C')}",
        f"강수확률 {_fmt(weather.precipitation_probability_max, '%', '.0f')}",
        f"강우 {_fmt(weather.precipitation_sum, 'mm')}",
    ]
    if desc:
        parts.append(desc)
    parts.append(f"[{source_label}]")

    print("  " + " | ".join(parts))
