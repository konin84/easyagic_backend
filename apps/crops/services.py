from datetime import datetime
from .data import CROP_DATABASE

_SUITABILITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def get_crop_recommendations(soil_type: str, current_temp: float = None) -> list:
    current_month = datetime.now().month
    crops = CROP_DATABASE.get(soil_type, CROP_DATABASE["Unknown"])

    recommendations = []
    for crop in crops:
        in_season = current_month in crop["season"]

        temp_ok = True
        temp_note = ""
        if current_temp is not None:
            if current_temp < crop["min_temp"]:
                temp_ok = False
                temp_note = f"Currently too cold — needs above {crop['min_temp']}°C"
            elif current_temp > crop["max_temp"]:
                temp_ok = False
                temp_note = f"Currently too hot — needs below {crop['max_temp']}°C"

        if in_season and temp_ok:
            suitability = "High"
        elif in_season or temp_ok:
            suitability = "Medium"
        else:
            suitability = "Low"

        recommendations.append({
            "name": crop["name"],
            "suitability": suitability,
            "in_season": in_season,
            "temperature_suitable": temp_ok,
            "temperature_note": temp_note,
            "water_needs": crop["water_needs"],
            "optimal_temp_range": f"{crop['min_temp']}°C – {crop['max_temp']}°C",
        })

    recommendations.sort(key=lambda c: _SUITABILITY_ORDER[c["suitability"]])
    return recommendations
