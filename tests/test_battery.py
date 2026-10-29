"""The battery option: a chosen battery sensor mirrored onto the speaker's device."""

import pytest
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_UNIT_OF_MEASUREMENT, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.soundboks.const import CONF_BATTERY_ENTITY

from .conftest import FakeSpeaker, make_entry, setup_entry

pytestmark = pytest.mark.usefixtures("enable_bluetooth")

BATTERY = "sensor.soundboks_202047_battery"
SOURCE = "sensor.pack_battery"
SOURCE_ATTRS = {ATTR_DEVICE_CLASS: "battery", ATTR_UNIT_OF_MEASUREMENT: "%"}


def battery_entry() -> MockConfigEntry:
    return make_entry(**{CONF_BATTERY_ENTITY: SOURCE})


async def test_not_created_without_option(
    hass: HomeAssistant, mock_entry: MockConfigEntry, fake_speaker: FakeSpeaker
):
    await setup_entry(hass, mock_entry)
    assert hass.states.get(BATTERY) is None


async def test_mirrors_source_while_speaker_off(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    hass.states.async_set(SOURCE, "73", SOURCE_ATTRS)
    await setup_entry(hass, battery_entry())  # the speaker never advertises
    state = hass.states.get(BATTERY)
    assert float(state.state) == 73
    assert state.attributes[ATTR_DEVICE_CLASS] == "battery"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "%"


async def test_follows_changes(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    hass.states.async_set(SOURCE, "73", SOURCE_ATTRS)
    await setup_entry(hass, battery_entry())
    hass.states.async_set(SOURCE, "60", SOURCE_ATTRS)
    await hass.async_block_till_done()
    assert float(hass.states.get(BATTERY).state) == 60


@pytest.mark.parametrize("source", ["unavailable", "unknown", "abc", None])
async def test_unavailable_when_source_unusable(
    hass: HomeAssistant, fake_speaker: FakeSpeaker, source: str | None
):
    if source is not None:
        hass.states.async_set(SOURCE, source, SOURCE_ATTRS)
    await setup_entry(hass, battery_entry())
    assert hass.states.get(BATTERY).state == STATE_UNAVAILABLE


async def test_unavailable_when_source_removed(hass: HomeAssistant, fake_speaker: FakeSpeaker):
    hass.states.async_set(SOURCE, "73", SOURCE_ATTRS)
    await setup_entry(hass, battery_entry())
    hass.states.async_remove(SOURCE)
    await hass.async_block_till_done()
    assert hass.states.get(BATTERY).state == STATE_UNAVAILABLE
