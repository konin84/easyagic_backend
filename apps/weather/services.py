import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

_HOURLY_VARS = [
    "soil_temperature_0cm",
    "soil_temperature_6cm",
    "soil_temperature_18cm",
    "soil_temperature_54cm",
    "soil_moisture_0_to_1cm",
    "soil_moisture_1_to_3cm",
    "soil_moisture_3_to_9cm",
]

_DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "rain_sum",
    "windspeed_10m_max",
    "et0_fao_evapotranspiration",
]

_CURRENT_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "windspeed_10m",
    "weathercode",
]


def get_agricultural_data(latitude: float, longitude: float) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "timezone": "auto",
        "forecast_days": 7,
        "hourly": ",".join(_HOURLY_VARS),
        "daily": ",".join(_DAILY_VARS),
        "current": ",".join(_CURRENT_VARS),
    }

    response = requests.get(OPEN_METEO_URL, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    hourly = data.get("hourly", {})
    current_soil = {
        "soil_temperature_0cm": _first(hourly, "soil_temperature_0cm"),
        "soil_temperature_6cm": _first(hourly, "soil_temperature_6cm"),
        "soil_temperature_18cm": _first(hourly, "soil_temperature_18cm"),
        "soil_temperature_54cm": _first(hourly, "soil_temperature_54cm"),
        "soil_moisture_0_to_1cm": _first(hourly, "soil_moisture_0_to_1cm"),
        "soil_moisture_1_to_3cm": _first(hourly, "soil_moisture_1_to_3cm"),
    }

    daily = data.get("daily", {})
    return {
        "location": {
            "latitude": data.get("latitude"),
            "longitude": data.get("longitude"),
            "timezone": data.get("timezone"),
            "elevation": data.get("elevation"),
        },
        "current_weather": data.get("current", {}),
        "current_soil": current_soil,
        "daily_forecast": {
            "dates": daily.get("time", []),
            "max_temp": daily.get("temperature_2m_max", []),
            "min_temp": daily.get("temperature_2m_min", []),
            "precipitation_mm": daily.get("precipitation_sum", []),
            "rain_mm": daily.get("rain_sum", []),
            "max_windspeed_kmh": daily.get("windspeed_10m_max", []),
            "evapotranspiration_mm": daily.get("et0_fao_evapotranspiration", []),
        },
    }


def _first(hourly: dict, key: str):
    values = hourly.get(key, [])
    return values[0] if values else None
