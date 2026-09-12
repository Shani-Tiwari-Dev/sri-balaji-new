"""
Shared area / rate / currency calculation utilities.
Ported 1:1 from the original frontend's src/utils/calc.ts so the API always
agrees with the UI, even if the browser-side JS in frontend/js/calc.js is
used for instant client-side previews.
"""

INCHES_PER_UNIT = {
    "meters": 39.3701,
    "centimeters": 1 / 2.54,
    "feet": 12,
    "inches": 1,
}

SQFT_TO_SQM = 0.092903
SQFT_TO_SQCM = 929.03
SQFT_RATE_TO_SQM_RATE = 10.76391
SQFT_RATE_TO_SQCM_RATE = 929.0304


def calculate_slab_area(length, width, unit, pieces=1):
    factor = INCHES_PER_UNIT.get(unit, 12)
    length_in = float(length) * factor
    width_in = float(width) * factor
    per_piece_sqft = (length_in * width_in) / 144
    total_sqft = round(per_piece_sqft * pieces, 2)
    total_sqm = round(total_sqft * SQFT_TO_SQM, 2)
    total_sqcm = round(total_sqft * SQFT_TO_SQCM)
    return {
        "totalSqFt": total_sqft,
        "totalSqMeters": total_sqm,
        "totalSqCm": total_sqcm,
    }


def get_rates_in_all_units(price_per_sqft):
    price_per_sqft = float(price_per_sqft)
    return {
        "perSqFt": round(price_per_sqft, 2),
        "perSqMeter": round(price_per_sqft * SQFT_RATE_TO_SQM_RATE, 2),
        "perSqCm": round(price_per_sqft / SQFT_RATE_TO_SQCM_RATE, 3),
    }


def get_dimensions_in_all_units(length, width, unit):
    factor = INCHES_PER_UNIT.get(unit, 12)
    length_in = float(length) * factor
    width_in = float(width) * factor
    length_m = length_in / 39.3701
    width_m = width_in / 39.3701
    return {
        "feet": {"length": round(length_in / 12, 2), "width": round(width_in / 12, 2)},
        "meters": {"length": round(length_m, 3), "width": round(width_m, 3)},
        "centimeters": {"length": round(length_in * 2.54, 1), "width": round(width_in * 2.54, 1)},
        "inches": {"length": round(length_in, 2), "width": round(width_in, 2)},
    }


def format_currency_inr(amount):
    """Whole-rupee, comma-grouped Indian currency string, e.g. ₹4,66,200."""
    amount = int(round(amount or 0))
    negative = amount < 0
    amount = abs(amount)
    s = str(amount)
    if len(s) <= 3:
        grouped = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + "," + last3
    return ("-" if negative else "") + "\u20b9" + grouped
