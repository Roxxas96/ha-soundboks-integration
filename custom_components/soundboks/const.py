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
# An advertisement older than this doesn't count: it's a replay from before a restart, or the
# speaker is busy. Commands and polls only try to connect within it (or on an open link).
FRESH_ADVERTISEMENT = 15.0  # seconds
# After HA powers the speaker off, adverts relayed while it shuts down are ignored this long
POWER_OFF_QUIET = timedelta(seconds=5)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.SELECT,
    Platform.SENSOR,
]
