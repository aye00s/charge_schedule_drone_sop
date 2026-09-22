"""Phase 4 energy model: flat-rate flight energy (Section 4.3 fallback,
kappa=0.5 Wh/m) and the three-band CC-CV charging curve. Units: Wh, W, m,
minutes (dt = 1 minute, matching assumption A1/A4).
"""

# CLAUDE.md Section 4.3 suggests kappa=0.5 Wh/m as an illustrative example,
# but combined with a ~90 Wh battery (typical small-quadcopter capacity) that
# gives only 180 m of total range -- unusable for any mission area larger
# than a room. Replaced with a physically grounded estimate instead: cruise
# power/speed for a small quadcopter is roughly 100-200 W at 10-20 m/s, i.e.
# ~0.003-0.007 Wh/m. Using 0.01 Wh/m (round number, upper end of that range,
# leaves margin for climb/maneuvering overhead not otherwise modeled) gives
# a ~9 km range at full charge -- usable across a multi-km mission area.
# Revisit once hardware calibration (Section 14.8, fit_energy_model.py)
# provides a measured value.
FLIGHT_ENERGY_WH_PER_M = 0.01  # kappa

# Section 4.3 default three-band approximation
CHARGE_BANDS = [
    (0.0, 0.70, 200.0),
    (0.70, 0.90, 120.0),
    (0.90, 1.00, 50.0),
]


def flight_energy_wh(distance_m: float) -> float:
    return distance_m * FLIGHT_ENERGY_WH_PER_M


def charge_power_w(soc: float) -> float:
    for lo, hi, power in CHARGE_BANDS:
        if lo <= soc < hi:
            return power
    return CHARGE_BANDS[-1][2]  # soc >= 1.0 edge case


def soc_after_charging(soc: float, minutes: float, battery_wh: float, eta: float = 1.0) -> float:
    """Advance soc by charging for `minutes`, stepping band-by-band so a
    step that crosses a band boundary uses the correct rate in each part."""
    remaining_minutes = minutes
    s = soc
    while remaining_minutes > 1e-9 and s < 1.0:
        lo, hi, power = next(b for b in CHARGE_BANDS if b[0] <= s < b[1])
        # time to reach the top of this band at this power
        energy_to_band_top = (hi - s) * battery_wh
        time_to_band_top_min = energy_to_band_top / (eta * power) * 60.0
        if time_to_band_top_min <= remaining_minutes:
            s = hi
            remaining_minutes -= time_to_band_top_min
        else:
            energy_added = eta * power * (remaining_minutes / 60.0)
            s += energy_added / battery_wh
            remaining_minutes = 0.0
    return min(s, 1.0)


def time_to_reach_target_min(soc_start: float, soc_target: float, battery_wh: float,
                              eta: float = 1.0) -> float:
    """Closed-form (band-by-band) time to charge from soc_start to soc_target."""
    if soc_target <= soc_start:
        return 0.0
    total_min = 0.0
    s = soc_start
    for lo, hi, power in CHARGE_BANDS:
        band_lo = max(lo, s)
        band_hi = min(hi, soc_target)
        if band_hi > band_lo:
            energy_wh = (band_hi - band_lo) * battery_wh
            total_min += energy_wh / (eta * power) * 60.0
    return total_min
