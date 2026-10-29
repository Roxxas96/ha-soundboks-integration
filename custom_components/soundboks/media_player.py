"""The speaker as a media player: on/off, volume and the active inputs."""

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_TURN_ON_ENTITY, DOMAIN
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
    _base_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.TURN_OFF
    )
    _attr_volume_step = 0.05

    def __init__(self, coordinator: SoundboksCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.address

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        # The speaker can't wake itself: turning on needs a configured helper
        if self._turn_on_entity is None:
            return self._base_features
        return self._base_features | MediaPlayerEntityFeature.TURN_ON

    @property
    def _turn_on_entity(self) -> str | None:
        return self.coordinator.config_entry.options.get(CONF_TURN_ON_ENTITY)

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

    async def async_turn_on(self) -> None:
        # Stays off until the speaker actually advertises
        entity_id = self._turn_on_entity
        if entity_id is None:
            return
        if self.hass.states.get(entity_id) is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="turn_on_entity_missing",
                translation_placeholders={"entity_id": entity_id},
            )
        domain = entity_id.partition(".")[0]
        service = "turn_on" if domain == "script" else "press"
        await self.hass.services.async_call(
            domain, service, {ATTR_ENTITY_ID: entity_id}, blocking=True, context=self._context
        )

    async def async_turn_off(self) -> None:
        await self.coordinator.async_power_off()
