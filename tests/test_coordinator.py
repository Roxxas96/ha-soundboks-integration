"""Setup, polling and presence, against the fake speaker."""

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.soundboks.const import CONF_PIN, PRESENCE_GRACE
from custom_components.soundboks.protocol import POWER_UUID, VOLUME_UUID

from .conftest import FakeSpeaker, advertise, make_service_info, setup_entry

pytestmark = pytest.mark.usefixtures("enable_bluetooth")


async def test_setup_with_speaker_off_succeeds(
    hass: HomeAssistant, mock_entry: MockConfigEntry, fake_speaker: FakeSpeaker
):
    await setup_entry(hass, mock_entry)
    coordinator = mock_entry.runtime_data
    assert mock_entry.state is ConfigEntryState.LOADED
    assert coordinator.data is None
    assert coordinator.present is False
    assert fake_speaker.connect_count == 0


async def test_advertisement_reads_state(
    hass: HomeAssistant, mock_entry: MockConfigEntry, fake_speaker: FakeSpeaker
):
    await setup_entry(hass, mock_entry)
    await advertise(hass, mock_entry)
    coordinator = mock_entry.runtime_data
    assert coordinator.present is True
    assert coordinator.data.volume == 0x2D
    assert coordinator.firmware == "2.4.2"
    assert coordinator.client.is_connected is False


async def test_poll_skipped_when_absent(
    hass: HomeAssistant, mock_entry: MockConfigEntry, fake_speaker: FakeSpeaker
):
    await setup_entry(hass, mock_entry)
    await mock_entry.runtime_data.async_refresh()
    assert fake_speaker.connect_count == 0


async def test_busy_speaker_keeps_last_state(
    hass: HomeAssistant, mock_entry: MockConfigEntry, fake_speaker: FakeSpeaker
):
    await setup_entry(hass, mock_entry)
    await advertise(hass, mock_entry)
    coordinator = mock_entry.runtime_data
    before = coordinator.data
    fake_speaker.unreachable = True
    await coordinator.async_refresh()
    assert coordinator.data == before
    assert coordinator.last_update_success is True


async def test_wrong_pin_fails_auth(
    hass: HomeAssistant, mock_entry: MockConfigEntry, fake_speaker: FakeSpeaker
):
    fake_speaker.set_pin("9999")
    entry = MockConfigEntry(
        domain=mock_entry.domain,
        unique_id=mock_entry.unique_id,
        title=mock_entry.title,
        data={**mock_entry.data, CONF_PIN: "1234"},
    )
    await setup_entry(hass, entry)
    await advertise(hass, entry)
    coordinator = entry.runtime_data
    assert coordinator.last_update_success is False
    assert isinstance(coordinator.last_exception, ConfigEntryAuthFailed)


async def test_power_off_marks_absent_immediately(
    hass: HomeAssistant, mock_entry: MockConfigEntry, fake_speaker: FakeSpeaker
):
    await setup_entry(hass, mock_entry)
    await advertise(hass, mock_entry)
    coordinator = mock_entry.runtime_data
    await coordinator.async_power_off()
    assert (POWER_UUID, b"\x00") in fake_speaker.writes
    assert coordinator.present is False


async def test_set_volume_updates_state_without_poll(
    hass: HomeAssistant, mock_entry: MockConfigEntry, fake_speaker: FakeSpeaker
):
    await setup_entry(hass, mock_entry)
    await advertise(hass, mock_entry)
    coordinator = mock_entry.runtime_data
    await coordinator.async_set_volume(0x80)
    assert (VOLUME_UUID, b"\x80") in fake_speaker.writes
    assert coordinator.data.volume == 0x80
    await coordinator.client.disconnect()


async def test_command_when_absent_raises_without_connecting(
    hass: HomeAssistant, mock_entry: MockConfigEntry, fake_speaker: FakeSpeaker
):
    await setup_entry(hass, mock_entry)
    with pytest.raises(HomeAssistantError):
        await mock_entry.runtime_data.async_set_volume(10)
    assert fake_speaker.connect_count == 0


async def test_command_when_unreachable_raises_ha_error(
    hass: HomeAssistant, mock_entry: MockConfigEntry, fake_speaker: FakeSpeaker
):
    await setup_entry(hass, mock_entry)
    await advertise(hass, mock_entry)
    fake_speaker.unreachable = True
    with pytest.raises(HomeAssistantError) as raised:
        await mock_entry.runtime_data.async_set_volume(10)
    assert raised.value.translation_key == "unreachable"


async def test_knob_notification_updates_state(
    hass: HomeAssistant, mock_entry: MockConfigEntry, fake_speaker: FakeSpeaker
):
    await setup_entry(hass, mock_entry)
    await advertise(hass, mock_entry)
    coordinator = mock_entry.runtime_data
    await coordinator.async_set_volume(0x10)
    fake_speaker.notify(VOLUME_UUID, b"\x50")
    assert coordinator.data.volume == 0x50
    await coordinator.client.disconnect()


async def test_unavailable_respects_grace(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    fake_speaker: FakeSpeaker,
    freezer: FrozenDateTimeFactory,
):
    assert PRESENCE_GRACE == timedelta(minutes=5)
    await setup_entry(hass, mock_entry)
    await advertise(hass, mock_entry)
    coordinator = mock_entry.runtime_data
    coordinator.async_handle_unavailable(make_service_info())
    freezer.tick(timedelta(minutes=4))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.present is True
    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.present is False


async def test_advertisement_cancels_grace(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    fake_speaker: FakeSpeaker,
    freezer: FrozenDateTimeFactory,
):
    await setup_entry(hass, mock_entry)
    await advertise(hass, mock_entry)
    coordinator = mock_entry.runtime_data
    coordinator.async_handle_unavailable(make_service_info())
    await advertise(hass, mock_entry)
    freezer.tick(timedelta(minutes=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.present is True


async def test_unload_disconnects(
    hass: HomeAssistant, mock_entry: MockConfigEntry, fake_speaker: FakeSpeaker
):
    await setup_entry(hass, mock_entry)
    await advertise(hass, mock_entry)
    coordinator = mock_entry.runtime_data
    await coordinator.async_set_volume(10)
    assert coordinator.client.is_connected
    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    assert coordinator.client.is_connected is False
    assert mock_entry.state is ConfigEntryState.NOT_LOADED
