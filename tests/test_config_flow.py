"""Config flow: discovery, picking a speaker, PIN, reauth and reconfigure."""

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.soundboks.const import CONF_PIN, DOMAIN
from custom_components.soundboks.protocol import PROFILE_UUID

from .conftest import ADDRESS, FakeSpeaker, make_ble_device, make_service_info

pytestmark = pytest.mark.usefixtures("enable_bluetooth", "no_setup")


@pytest.fixture
async def no_setup(hass: HomeAssistant) -> AsyncIterator[None]:
    """Skip the integration's setup: only the flow is under test."""
    with (
        patch("custom_components.soundboks.async_setup_entry", return_value=True),
        patch("custom_components.soundboks.async_unload_entry", return_value=True),
        patch(
            "custom_components.soundboks.config_flow.async_ble_device_from_address",
            return_value=make_ble_device(),
        ),
    ):
        yield
        # Unload while setup is still stubbed: there is no runtime data to tear down
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_unload(entry.entry_id)


def discovered(*infos):
    return patch(
        "custom_components.soundboks.config_flow.async_discovered_service_info",
        return_value=list(infos),
    )


async def start_bluetooth(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_service_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    return await hass.config_entries.flow.async_configure(result["flow_id"], {})


async def test_bluetooth_discovery_no_pin(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    result = await start_bluetooth(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SOUNDBOKS #202047"
    assert result["data"] == {CONF_ADDRESS: ADDRESS}
    assert result["result"].unique_id == ADDRESS


async def test_bluetooth_discovery_with_pin(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    fake_speaker.set_pin("1234")
    result = await start_bluetooth(hass)
    assert result["step_id"] == "pin"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "12"})
    assert result["errors"] == {CONF_PIN: "invalid_pin_format"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "9999"})
    assert result["errors"] == {CONF_PIN: "invalid_pin"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "1234"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ADDRESS: ADDRESS, CONF_PIN: "1234"}


async def test_user_step_lists_discovered(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    with discovered(make_service_info()):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: ADDRESS}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SOUNDBOKS #202047"


async def test_user_step_no_devices(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    with discovered():
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_step_skips_configured(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}).add_to_hass(
        hass
    )
    with discovered(make_service_info()):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["reason"] == "no_devices_found"


async def test_unreachable_shows_error(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    fake_speaker.unreachable = True
    result = await start_bluetooth(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    fake_speaker.unreachable = False
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_unsupported_aborts(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    del fake_speaker.values[PROFILE_UUID]
    result = await start_bluetooth(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_already_configured_aborts(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}).add_to_hass(
        hass
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=make_service_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_name_without_prefix_falls_back(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    info = make_service_info()
    info.name = "Speaker"
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["title"] == f"SOUNDBOKS {ADDRESS}"


def pin_entry(hass: HomeAssistant, pin: str | None = "1234") -> MockConfigEntry:
    data = {CONF_ADDRESS: ADDRESS} | ({CONF_PIN: pin} if pin else {})
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, title="SOUNDBOKS #202047", data=data)
    entry.add_to_hass(hass)
    return entry


async def test_reauth_updates_pin(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    fake_speaker.set_pin("4321")
    entry = pin_entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "1234"})
    assert result["errors"] == {CONF_PIN: "invalid_pin"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "4321"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PIN] == "4321"


async def test_reconfigure_updates_pin(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    fake_speaker.set_pin("4321")
    entry = pin_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_PIN: "4321"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PIN] == "4321"


async def test_reconfigure_removes_pin_when_speaker_has_none(
    hass: HomeAssistant, fake_speaker: FakeSpeaker
):
    entry = pin_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {CONF_ADDRESS: ADDRESS}
