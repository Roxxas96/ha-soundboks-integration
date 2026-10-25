"""Diagnostics download, with the PIN redacted."""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_PIN
from .coordinator import SoundboksConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SoundboksConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), {CONF_PIN}),
        "present": coordinator.present,
        "firmware": coordinator.firmware,
        "state": asdict(coordinator.data) if coordinator.data is not None else None,
    }
