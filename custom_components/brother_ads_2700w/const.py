"""Constants for the Brother ADS-2700W integration."""

from datetime import timedelta

DOMAIN = "brother_ads_2700w"

CONF_AUTO_TIME_SYNC = "auto_time_sync"
CONF_MODEL = "model"
CONF_FIRMWARE = "firmware"

DEFAULT_AUTO_TIME_SYNC = True

SCAN_INTERVAL = timedelta(seconds=30)

# Wear limits as shown in the device web interface ("1060 / 100000pages").
ROLLER_LIFE = 100_000
MAINTENANCE_INTERVAL = 5_000

# Device clock deviation (seconds) above which an automatic sync is triggered.
CLOCK_TOLERANCE = 120
# Minimum time between two automatic sync attempts.
TIME_SYNC_RETRY = timedelta(minutes=5)
