"""Config flow for SOUNDBOKS speakers."""

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class SoundboksConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
