from decimal import Decimal, InvalidOperation
import re

from .specs import SHEET

FREQUENCY_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(Hz|kHz|MHz|GHz)\s*$", re.I)
FACTORS = {"hz": Decimal(1), "khz": Decimal(1000), "mhz": Decimal(1000000), "ghz": Decimal(1000000000)}


def frequency_hz(value):
    if value is None or str(value).strip() == "":
        return None
    match = FREQUENCY_PATTERN.fullmatch(str(value))
    if not match:
        raise ValueError(f"Frequency requires an explicit Hz/kHz/MHz/GHz unit: {value!r}")
    result = Decimal(match[1]) * FACTORS[match[2].lower()]
    if not result.is_finite() or result <= 0 or result != result.to_integral_value():
        raise ValueError(f"Frequency must be positive, with whole-Hz precision: {value!r}")
    return int(result)


def number(value):
    if value is None or str(value).strip() == "":
        return None
    result = Decimal(str(value).strip())
    if not result.is_finite():
        raise ValueError("Non-finite number")
    return float(result)


def normalize_station(raw, source_row, dataset_id):
    flags = []
    record = {"dataset_id": dataset_id, "source_table": SHEET, "source_row": source_row,
              "station_number": str(raw["station_number"]), "is_synthetic": True, "raw": raw}
    for name in ("tx_frequency", "rx_frequency", "channel_bandwidth"):
        target = name + "_hz"
        try:
            record[target] = frequency_hz(raw[name])
            if record[target] is None:
                flags.append("missing_" + name)
        except (ValueError, InvalidOperation):
            record[target] = None
            flags.append("invalid_" + name)
    for name in ("longitude", "latitude", "ground_height_m", "mast_height_m",
                 "antenna_height_agl_m", "antenna_height_asl_m", "antenna_gain_db",
                 "radiation_direction_deg", "line_loss_db"):
        try:
            record[name] = number(raw[name])
        except (ValueError, InvalidOperation):
            record[name] = None
            flags.append("invalid_" + name)
    lon, lat = record["longitude"], record["latitude"]
    if lon is None or lat is None:
        flags.append("missing_coordinates")
    elif not (-180 <= lon <= 180 and -90 <= lat <= 90):
        flags.append("invalid_coordinates")
    elif not (19 <= lon <= 32 and 59 <= lat <= 71):
        flags.append("outside_broad_finland_bbox")
    agl = record["antenna_height_agl_m"]
    if agl is not None and agl < 1:
        flags.append("antenna_below_1m_agl")
    ground, asl = record["ground_height_m"], record["antenna_height_asl_m"]
    if ground is not None and asl is not None and asl < ground:
        flags.append("antenna_asl_below_ground")
    if agl is not None and ground is not None and asl is not None and abs(asl - ground - agl) > 1:
        flags.append("inconsistent_antenna_heights")
    direction = record["radiation_direction_deg"]
    if direction is not None and not 0 <= direction <= 360:
        flags.append("invalid_radiation_direction")
    if raw["directivity"] == "D" and direction is None:
        flags.append("directional_antenna_missing_direction")
    record["reported_power_w"] = None
    try:
        power = number(raw["reported_power"])
        unit = str(raw["power_unit"] or "").strip().lower()
        if power is not None and unit in {"w", "kw"} and power >= 0:
            record["reported_power_w"] = power * (1000 if unit == "kw" else 1)
        else:
            flags.append("missing_or_unsupported_power")
    except (ValueError, InvalidOperation):
        flags.append("invalid_power")
    record["quality_flags"] = flags
    return record
