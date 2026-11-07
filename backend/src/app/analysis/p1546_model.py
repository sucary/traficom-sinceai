"""Narrow, auditable adapter around the published P.1546-6 implementation."""

from __future__ import annotations

import math


MODEL_VERSION = "ITU-R P.1546-6 / Py1546 commit e235629"


def erp_kw_from_radiated_power(power_dbw: float, power_type: str) -> tuple[float, float]:
    """Convert an IFIC radiated power to ERP kW and report the applied dB delta."""
    kind = (power_type or "").strip().upper()
    if kind == "E":
        delta_db = 0.0
    elif kind == "I":
        # EIRP uses an isotropic reference; ERP uses a half-wave dipole.
        delta_db = -2.15
    else:
        raise ValueError("radiated power type must be E (ERP) or I (EIRP)")
    erp_dbw = float(power_dbw) + delta_db
    return 10.0 ** (erp_dbw / 10.0) / 1000.0, delta_db


def field_strength_dbuv_m(
    *,
    frequency_mhz: float,
    distance_km: float,
    effective_tx_height_m: float,
    erp_kw: float,
    path_zone: str = "Land",
    receiver_height_m: float = 10.0,
    receiver_clutter_height_m: float = 10.0,
    time_percentage: float = 10.0,
    location_percentage: float = 50.0,
) -> tuple[float, float]:
    """Calculate field strength and basic transmission loss with P.1546-6."""
    values = (frequency_mhz, distance_km, effective_tx_height_m, erp_kw)
    if not all(math.isfinite(float(value)) and float(value) > 0 for value in values):
        raise ValueError("frequency, distance, height and ERP must be finite and positive")
    if not 30 <= frequency_mhz <= 4000:
        raise ValueError("P.1546-6 frequency scope is 30-4000 MHz")
    if not 1 <= distance_km <= 1000:
        raise ValueError("P.1546-6 path distance must be 1-1000 km")
    if path_zone not in {"Land", "Sea", "Warm", "Cold"}:
        raise ValueError("unsupported P.1546 path zone")

    # Py1546 6.1 uses the removed NumPy 1.x alias ``np.mat``.  Mapping it to
    # the documented equivalent keeps the published algorithm usable on
    # NumPy 2 without changing the matrix values or operations.
    import numpy as np
    if not hasattr(np, "mat"):
        np.mat = np.asmatrix
    from Py1546 import P1546

    field, loss = P1546.bt_loss(
        float(frequency_mhz),
        float(time_percentage),
        float(effective_tx_height_m),
        float(receiver_height_m),
        float(receiver_clutter_height_m),
        "Rural",
        [float(distance_km)],
        [path_zone],
        0,
        float(location_percentage),
        0,
        float(erp_kw),
    )
    return float(field), float(loss)
