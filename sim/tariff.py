"""Minimal electricity-cost model (Section 4.4's pi_jt tariff term):
flat-rate and time-of-use pricing, in USD/Wh. Not per-station (pi_jt in the
full model could vary by station too); this is a single shared grid tariff,
the simplest version that lets 'flat' vs 'time-of-use' be compared."""

FLAT_RATE_USD_PER_WH = 0.00015  # ~$0.15/kWh, typical US retail flat rate


def flat_rate_usd_per_wh(t_min: float) -> float:
    return FLAT_RATE_USD_PER_WH


def tou_rate_usd_per_wh(t_min: float) -> float:
    """Peak 17:00-21:00 ($0.30/kWh), shoulder 07:00-17:00 & 21:00-23:00
    ($0.15/kWh), off-peak else ($0.08/kWh). t_min wraps modulo 1440
    (minutes/day)."""
    hour = (t_min % 1440.0) / 60.0
    if 17.0 <= hour < 21.0:
        return 0.00030
    if 7.0 <= hour < 17.0 or 21.0 <= hour < 23.0:
        return 0.00015
    return 0.00008


TARIFFS = {"flat": flat_rate_usd_per_wh, "tou": tou_rate_usd_per_wh}
