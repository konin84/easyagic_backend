# Crop database keyed by soil type.
# season: list of months (1=Jan … 12=Dec) when planting is suitable.
# min/max_temp: air temperature range (°C) the crop tolerates.

CROP_DATABASE = {
    "Clay": [
        {"name": "Rice",        "season": [4,5,6,7,8,9],        "min_temp": 20, "max_temp": 35, "water_needs": "High"},
        {"name": "Wheat",       "season": [10,11,12,1,2,3],      "min_temp": 10, "max_temp": 25, "water_needs": "Medium"},
        {"name": "Corn/Maize",  "season": [4,5,6,7,8],           "min_temp": 18, "max_temp": 32, "water_needs": "High"},
        {"name": "Cabbage",     "season": [1,2,3,10,11,12],       "min_temp":  7, "max_temp": 20, "water_needs": "Medium"},
        {"name": "Broccoli",    "season": [1,2,3,10,11,12],       "min_temp": 10, "max_temp": 20, "water_needs": "Medium"},
        {"name": "Soybean",     "season": [5,6,7,8,9],            "min_temp": 15, "max_temp": 30, "water_needs": "Medium"},
        {"name": "Peas",        "season": [10,11,12,1,2,3],       "min_temp":  7, "max_temp": 18, "water_needs": "Medium"},
    ],
    "Sandy": [
        {"name": "Carrots",       "season": [3,4,5,9,10,11],      "min_temp": 10, "max_temp": 24, "water_needs": "Medium"},
        {"name": "Potatoes",      "season": [3,4,5,9,10],          "min_temp": 10, "max_temp": 20, "water_needs": "High"},
        {"name": "Groundnut",     "season": [4,5,6,7,8,9],         "min_temp": 20, "max_temp": 35, "water_needs": "Low"},
        {"name": "Watermelon",    "season": [4,5,6,7,8],           "min_temp": 22, "max_temp": 35, "water_needs": "Medium"},
        {"name": "Sweet Potato",  "season": [4,5,6,7,8,9],         "min_temp": 18, "max_temp": 30, "water_needs": "Low"},
        {"name": "Cassava",       "season": [4,5,6,7,8,9,10,11],   "min_temp": 18, "max_temp": 35, "water_needs": "Low"},
        {"name": "Millet",        "season": [5,6,7,8,9],            "min_temp": 20, "max_temp": 35, "water_needs": "Low"},
    ],
    "Loam": [
        {"name": "Tomatoes",    "season": [4,5,6,7,8,9],           "min_temp": 18, "max_temp": 30, "water_needs": "High"},
        {"name": "Corn/Maize",  "season": [4,5,6,7,8],             "min_temp": 18, "max_temp": 32, "water_needs": "High"},
        {"name": "Beans",       "season": [4,5,6,7,8,9],           "min_temp": 18, "max_temp": 30, "water_needs": "Medium"},
        {"name": "Lettuce",     "season": [3,4,9,10,11],            "min_temp": 10, "max_temp": 22, "water_needs": "High"},
        {"name": "Pepper",      "season": [5,6,7,8,9],              "min_temp": 20, "max_temp": 32, "water_needs": "Medium"},
        {"name": "Cucumber",    "season": [4,5,6,7,8,9],            "min_temp": 18, "max_temp": 30, "water_needs": "High"},
        {"name": "Onion",       "season": [10,11,12,1,2,3],         "min_temp": 13, "max_temp": 24, "water_needs": "Medium"},
        {"name": "Wheat",       "season": [10,11,12,1,2,3],         "min_temp": 10, "max_temp": 25, "water_needs": "Medium"},
        {"name": "Soybean",     "season": [5,6,7,8,9],              "min_temp": 15, "max_temp": 30, "water_needs": "Medium"},
        {"name": "Eggplant",    "season": [4,5,6,7,8,9],            "min_temp": 20, "max_temp": 32, "water_needs": "Medium"},
    ],
    "Silt": [
        {"name": "Wheat",       "season": [10,11,12,1,2,3],         "min_temp": 10, "max_temp": 25, "water_needs": "Medium"},
        {"name": "Soybean",     "season": [5,6,7,8,9],              "min_temp": 15, "max_temp": 30, "water_needs": "Medium"},
        {"name": "Lettuce",     "season": [3,4,9,10,11],            "min_temp": 10, "max_temp": 22, "water_needs": "High"},
        {"name": "Spinach",     "season": [9,10,11,12,1,2,3],       "min_temp":  5, "max_temp": 20, "water_needs": "Medium"},
        {"name": "Strawberry",  "season": [3,4,5,9,10],             "min_temp": 15, "max_temp": 26, "water_needs": "High"},
        {"name": "Corn/Maize",  "season": [4,5,6,7,8],              "min_temp": 18, "max_temp": 32, "water_needs": "High"},
    ],
    "Laterite": [
        {"name": "Cassava",      "season": [4,5,6,7,8,9,10,11],    "min_temp": 18, "max_temp": 35, "water_needs": "Low"},
        {"name": "Sweet Potato", "season": [4,5,6,7,8,9],           "min_temp": 18, "max_temp": 30, "water_needs": "Low"},
        {"name": "Groundnut",    "season": [4,5,6,7,8,9],           "min_temp": 20, "max_temp": 35, "water_needs": "Low"},
        {"name": "Mango",        "season": [1,2,3,4,5,6],           "min_temp": 20, "max_temp": 40, "water_needs": "Low"},
        {"name": "Cashew",       "season": [1,2,3,4,5,6,7,8,9,10,11,12], "min_temp": 18, "max_temp": 40, "water_needs": "Low"},
        {"name": "Pineapple",    "season": [1,2,3,4,5,6,7,8,9,10,11,12], "min_temp": 20, "max_temp": 38, "water_needs": "Low"},
    ],
    "Black Cotton": [
        {"name": "Cotton",      "season": [5,6,7,8,9,10],           "min_temp": 20, "max_temp": 35, "water_needs": "Medium"},
        {"name": "Sorghum",     "season": [5,6,7,8,9],              "min_temp": 18, "max_temp": 35, "water_needs": "Low"},
        {"name": "Chickpea",    "season": [10,11,12,1,2,3],         "min_temp": 10, "max_temp": 25, "water_needs": "Low"},
        {"name": "Sunflower",   "season": [4,5,6,7,8,9],            "min_temp": 18, "max_temp": 32, "water_needs": "Medium"},
        {"name": "Wheat",       "season": [10,11,12,1,2,3],         "min_temp": 10, "max_temp": 25, "water_needs": "Medium"},
        {"name": "Linseed",     "season": [10,11,12,1,2,3],         "min_temp":  8, "max_temp": 22, "water_needs": "Low"},
    ],
    "Alluvial": [
        {"name": "Rice",        "season": [4,5,6,7,8,9],            "min_temp": 20, "max_temp": 35, "water_needs": "High"},
        {"name": "Wheat",       "season": [10,11,12,1,2,3],         "min_temp": 10, "max_temp": 25, "water_needs": "Medium"},
        {"name": "Sugarcane",   "season": [1,2,3,4,5,6,7,8,9,10,11,12], "min_temp": 20, "max_temp": 38, "water_needs": "High"},
        {"name": "Jute",        "season": [3,4,5,6,7,8],            "min_temp": 22, "max_temp": 35, "water_needs": "High"},
        {"name": "Corn/Maize",  "season": [4,5,6,7,8],              "min_temp": 18, "max_temp": 32, "water_needs": "High"},
        {"name": "Tomatoes",    "season": [4,5,6,7,8,9],            "min_temp": 18, "max_temp": 30, "water_needs": "High"},
        {"name": "Banana",      "season": [1,2,3,4,5,6,7,8,9,10,11,12], "min_temp": 18, "max_temp": 38, "water_needs": "High"},
    ],
}

# Unknown soil → use Loam as a safe default
CROP_DATABASE["Unknown"] = CROP_DATABASE["Loam"]
