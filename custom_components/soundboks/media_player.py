"""The speaker as a media player: on/off, volume and the active inputs."""

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SoundboksConfigEntry, SoundboksCoordinator
from .entity import SoundboksEntity, describe_inputs
from .protocol import level_to_raw, raw_to_level


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoundboksConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SoundboksMediaPlayer(entry.runtime_data)])


class SoundboksMediaPlayer(SoundboksEntity, MediaPlayerEntity):
    _attr_name = None  # the device's name
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.TURN_OFF
    )
    _attr_volume_step = 0.05

    def __init__(self, coordinator: SoundboksCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.address

    @property
    def available(self) -> bool:
        # An absent speaker is off, not unavailable: it can't be reached either way
        return True

    @property
    def state(self) -> MediaPlayerState:
        return MediaPlayerState.ON if self.coordinator.present else MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        data = self.coordinator.data
        return raw_to_level(data.volume) if data is not None else None

    @property
    def source(self) -> str | None:
        data = self.coordinator.data
        return describe_inputs(data.inputs) if data is not None else None

    async def async_set_volume_level(self, volume: float) -> None:
        await self.coordinator.async_set_volume(level_to_raw(volume))

    async def async_turn_off(self) -> None:
        await self.coordinator.async_power_off()
