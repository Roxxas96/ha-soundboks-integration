"""Diagnostics download."""

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.soundboks.const import CONF_PIN
from custom_components.soundboks.diagnostics import async_get_config_entry_diagnostics

from .conftest import FakeSpeaker, advertise, setup_entry

pytestmark = pytest.mark.usefixtures("enable_bluetooth")


async def test_diagnostics_redacts_pin(
    hass: HomeAssistant, mock_entry: MockConfigEntry, fake_speaker: FakeSpeaker
):
    fake_speaker.set_pin("1234")
    entry = MockConfigEntry(
        domain=mock_entry.domain,
        unique_id=mock_entry.unique_id,
        title=mock_entry.title,
        data={**mock_entry.data, CONF_PIN: "1234"},
    )
    await setup_entry(hass, entry)
    await advertise(hass, entry)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["entry"][CONF_PIN] == "**REDACTED**"
    assert "1234" not in str(diagnostics)
    assert diagnostics["present"] is True
    assert diagnostics["firmware"] == "2.4.2"
    assert diagnostics["state"]["volume"] == 0x2D
