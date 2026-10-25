"""Constants for the SOUNDBOKS integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "soundboks"
CONF_PIN = "pin"
MANUFACTURER = "SOUNDBOKS ApS"

POLL_INTERVAL = timedelta(seconds=30)
IDLE_TIMEOUT = 30.0  # seconds a command keeps the link open
# The speaker stops advertising while any app is connected, so "not advertising" may only mean
# busy: keep the last state this long before showing it off (see docs/PROTOCOL.md)
PRESENCE_GRACE = timedelta(minutes=5)

PLATFORMS: list[Platform] = []
