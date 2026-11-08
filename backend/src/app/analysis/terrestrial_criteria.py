from __future__ import annotations

import math


CRITERION = {
    "title": "ECC Recommendation T/R 25-08, A.1.2.3",
    "edition": "6 June 2025",
    "url": "https://docdb.cept.org/download/4789",
    "conditions": {
        "time_percentage": 10,
        "location_percentage": 50,
        "receiver_height_m": 10,
        "reference_bandwidth_hz": 25_000,
        "location": "border-line",
    },
    "challenge_extension": (
        "Challenge Q&A instructs use of the above-400 MHz value above the "
        "Recommendation's stated 470 MHz upper bound."
    ),
}


def base_threshold_dbuv_m(frequency_mhz: float) -> float:
    if not math.isfinite(frequency_mhz) or frequency_mhz < 29.7:
        raise ValueError("T/R 25-08 challenge criterion starts at 29.7 MHz")
    if frequency_mhz < 47:
        return 0.0
    if frequency_mhz < 108:
        return 6.0
    if frequency_mhz < 380:
        return 12.0
    if frequency_mhz < 400:
        return 18.0
    return 20.0


def threshold_dbuv_m(
    frequency_mhz: float,
    channel_spacing_hz: float | None = None,
    uniform_spectral_power: bool = False,
) -> tuple[float, float]:
    base = base_threshold_dbuv_m(frequency_mhz)
    correction = 0.0
    if uniform_spectral_power and channel_spacing_hz is not None and channel_spacing_hz > 25_000:
        correction = 10.0 * math.log10(channel_spacing_hz / 25_000.0)
    return base + correction, correction
