"""Canonical threshold constants — single source of truth.

All modules MUST import from here, not redefine locally.
"""
ERROR_RATE_THRESHOLD = 0.05   # >5% → scale down / alert
SUCCESS_RATE_MIN = 0.70       # <70% → do not scale up
RESTART_RATE_THRESHOLD = 3    # >3/hr → scale down / alert
SUCCESS_RATE_DROP_THRESHOLD = 0.10  # >10% drop from baseline
MAX_RESTARTS_PER_HOUR = RESTART_RATE_THRESHOLD  # alias
