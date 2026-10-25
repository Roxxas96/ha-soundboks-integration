"""Polls the speaker, tracks whether it is around, and runs commands."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace

from homeassistant.components.bluetooth import BluetoothChange, BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import SoundboksClient
from .const import DOMAIN, POLL_INTERVAL, PRESENCE_GRACE
from .protocol import (
    InvalidPinError,
    PinRequiredError,
    ProtocolError,
    SoundProfile,
    SpeakerState,
    SpeakerUnreachableError,
    StereoRole,
)

_LOGGER = logging.getLogger(__name__)

type SoundboksConfigEntry = ConfigEntry[SoundboksCoordinator]


class SoundboksCoordinator(DataUpdateCoordinator[SpeakerState | None]):
    """State is None until the speaker has been read once."""

    config_entry: SoundboksConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: SoundboksConfigEntry, client: SoundboksClient
    ) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=entry.title, update_interval=POLL_INTERVAL
        )
        self.client = client
        self.address: str = entry.data[CONF_ADDRESS]
        self.present = False
        self.firmware: str | None = None
        self._cancel_grace: CALLBACK_TYPE | None = None

    async def _async_update_data(self) -> SpeakerState | None:
        if not self.present:
            return self.data
        try:
            state = await self.client.read_state()
            if self.firmware is None:
                self.firmware = await self.client.read_firmware()
                self._update_device_firmware()
        except (InvalidPinError, PinRequiredError) as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SpeakerUnreachableError:
            # Most likely another app holds the speaker: keep what we know
            _LOGGER.debug("Speaker %s unreachable, keeping last state", self.address)
            return self.data
        except ProtocolError as err:
            raise UpdateFailed(str(err)) from err
        return state

    def _update_device_firmware(self) -> None:
        registry = dr.async_get(self.hass)
        if device := registry.async_get_device(identifiers={(DOMAIN, self.address)}):
            registry.async_update_device(device.id, sw_version=self.firmware)

    @callback
    def async_handle_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        self.client.set_ble_device(service_info.device)
        self._cancel_grace_timer()
        if not self.present:
            self.present = True
            self.async_update_listeners()
            self.config_entry.async_create_background_task(
                self.hass, self.async_request_refresh(), "soundboks refresh on advertisement"
            )

    @callback
    def async_handle_unavailable(self, service_info: BluetoothServiceInfoBleak) -> None:
        if not self.present or self._cancel_grace is not None:
            return
        if not PRESENCE_GRACE:
            self._mark_absent()
            return
        self._cancel_grace = async_call_later(
            self.hass, PRESENCE_GRACE, lambda _now: self._mark_absent()
        )

    @callback
    def async_handle_volume(self, raw: int) -> None:
        """The speaker notified a volume change, e.g. from its knob."""
        if self.data is not None and self.data.volume != raw:
            self.async_set_updated_data(replace(self.data, volume=raw))

    async def async_set_volume(self, raw: int) -> None:
        await self._command(lambda: self.client.set_volume(raw))
        self._update_state(volume=raw)

    async def async_set_profile(self, profile: SoundProfile) -> None:
        await self._command(lambda: self.client.set_profile(profile))
        self._update_state(profile=profile)

    async def async_set_stereo(self, role: StereoRole) -> None:
        await self._command(lambda: self.client.set_stereo(role))
        self._update_state(stereo=role)

    async def async_power_off(self) -> None:
        await self._command(self.client.power_off)
        self._mark_absent()

    async def async_reboot(self) -> None:
        await self._command(self.client.reboot)
        self._mark_absent()

    async def async_shutdown(self) -> None:
        self._cancel_grace_timer()
        await super().async_shutdown()

    async def _command(self, action: Callable[[], Awaitable[None]]) -> None:
        if not self.present:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="unreachable")
        try:
            await action()
        except SpeakerUnreachableError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="unreachable"
            ) from err
        except (InvalidPinError, PinRequiredError) as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="invalid_pin"
            ) from err

    def _update_state(self, **changes: object) -> None:
        if self.data is not None:
            self.async_set_updated_data(replace(self.data, **changes))

    @callback
    def _mark_absent(self) -> None:
        self._cancel_grace_timer()
        if self.present:
            self.present = False
            self.async_update_listeners()

    def _cancel_grace_timer(self) -> None:
        if self._cancel_grace is not None:
            self._cancel_grace()
            self._cancel_grace = None
