"""Config flow for SOUNDBOKS speakers: Bluetooth discovery, then the PIN if there is one."""

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .client import SoundboksClient
from .const import CONF_PIN, DOMAIN
from .protocol import (
    ADVERTISED_SERVICE_UUID,
    InvalidPinError,
    SpeakerUnreachableError,
    UnsupportedSpeakerError,
    validate_pin,
)

PIN_SCHEMA = vol.Schema({vol.Required(CONF_PIN): str})


def speaker_name(info: BluetoothServiceInfoBleak) -> str:
    """The "#<serial>" part of the advertised name ("AppControl #202047"), else the address."""
    _, hash_sign, serial = (info.name or "").partition("#")
    return f"#{serial}" if hash_sign and serial else info.address


class SoundboksConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._address = ""
        self._name = ""
        self._discovered: dict[str, str] = {}  # address -> name

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self._name = speaker_name(discovery_info)
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._async_probe("bluetooth_confirm")
        return self._confirm_form()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(self._address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._name = self._discovered[self._address]
            return await self._async_probe("user")
        configured = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if ADVERTISED_SERVICE_UUID in info.service_uuids and info.address not in configured:
                self._discovered[info.address] = speaker_name(info)
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        return self._user_form()

    async def async_step_pin(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            pin, errors = await self._async_check_pin(user_input[CONF_PIN])
            if pin is not None:
                return self._create_entry(pin)
        return self.async_show_form(
            step_id="pin",
            data_schema=PIN_SCHEMA,
            errors=errors,
            description_placeholders={"name": self._name},
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        self._address = entry_data[CONF_ADDRESS]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            pin, errors = await self._async_check_pin(user_input[CONF_PIN])
            if pin is not None:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_PIN: pin})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=PIN_SCHEMA,
            errors=errors,
            description_placeholders={"name": entry.title},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        self._address = entry.data[CONF_ADDRESS]
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                needs_pin = await self._client().pin_required()
            except SpeakerUnreachableError:
                errors["base"] = "cannot_connect"
            else:
                if not needs_pin:
                    return self.async_update_reload_and_abort(
                        entry, data={CONF_ADDRESS: self._address}
                    )
                pin, errors = await self._async_check_pin(user_input.get(CONF_PIN, ""))
                if pin is not None:
                    return self.async_update_reload_and_abort(entry, data_updates={CONF_PIN: pin})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Optional(CONF_PIN): str}),
            errors=errors,
            description_placeholders={"name": entry.title},
        )

    def _client(self) -> SoundboksClient:
        device = async_ble_device_from_address(self.hass, self._address, connectable=True)
        return SoundboksClient(device, None)

    async def _async_probe(self, step_id: str) -> ConfigFlowResult:
        """Check the chosen speaker is supported and whether it needs a PIN."""
        client = self._client()
        try:
            await client.check_supported()
            needs_pin = await client.pin_required()
        except UnsupportedSpeakerError:
            return self.async_abort(reason="not_supported")
        except SpeakerUnreachableError:
            errors = {"base": "cannot_connect"}
            if step_id == "user":
                return self._user_form(errors)
            return self._confirm_form(errors)
        if needs_pin:
            return await self.async_step_pin()
        return self._create_entry(None)

    async def _async_check_pin(self, raw: str) -> tuple[str | None, dict[str, str]]:
        """The PIN once the speaker accepted it, else None and the form errors."""
        try:
            pin = validate_pin(raw)
        except ValueError:
            return None, {CONF_PIN: "invalid_pin_format"}
        client = self._client()
        try:
            await client.verify_pin(pin)
        except InvalidPinError:
            return None, {CONF_PIN: "invalid_pin"}
        except SpeakerUnreachableError:
            return None, {"base": "cannot_connect"}
        finally:
            await client.disconnect()
        return pin, {}

    def _create_entry(self, pin: str | None) -> ConfigFlowResult:
        data = {CONF_ADDRESS: self._address}
        if pin is not None:
            data[CONF_PIN] = pin
        return self.async_create_entry(title=f"SOUNDBOKS {self._name}", data=data)

    def _confirm_form(self, errors: dict[str, str] | None = None) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="bluetooth_confirm",
            errors=errors,
            description_placeholders={"name": self._name},
        )

    def _user_form(self, errors: dict[str, str] | None = None) -> ConfigFlowResult:
        choices = {address: f"{name} ({address})" for address, name in self._discovered.items()}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(choices)}),
            errors=errors,
        )
