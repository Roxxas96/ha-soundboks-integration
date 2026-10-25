"""SOUNDBOKS speakers over Bluetooth LE."""

from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
    async_ble_device_from_address,
    async_register_callback,
    async_track_unavailable,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .client import SoundboksClient
from .const import CONF_PIN, IDLE_TIMEOUT, PLATFORMS
from .coordinator import SoundboksConfigEntry, SoundboksCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: SoundboksConfigEntry) -> bool:
    address = entry.data[CONF_ADDRESS]
    client = SoundboksClient(
        # None while the speaker is off: the first advertisement provides it
        async_ble_device_from_address(hass, address, connectable=True),
        entry.data.get(CONF_PIN),
        idle_timeout=IDLE_TIMEOUT,
        on_volume=lambda raw: coordinator.async_handle_volume(raw),
    )
    coordinator = SoundboksCoordinator(hass, entry, client)
    entry.runtime_data = coordinator
    entry.async_on_unload(
        async_register_callback(
            hass,
            coordinator.async_handle_advertisement,
            BluetoothCallbackMatcher(address=address, connectable=True),
            BluetoothScanningMode.PASSIVE,
        )
    )
    entry.async_on_unload(
        async_track_unavailable(hass, coordinator.async_handle_unavailable, address)
    )
    # Not async_config_entry_first_refresh: an off speaker must not hold up setup
    await coordinator.async_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SoundboksConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
        await entry.runtime_data.client.disconnect()
    return unloaded
