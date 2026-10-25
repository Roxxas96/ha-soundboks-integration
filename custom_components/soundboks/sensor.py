"""Which inputs are playing."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SoundboksConfigEntry, SoundboksCoordinator
from .entity import SoundboksEntity, describe_inputs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoundboksConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ActiveInputsSensor(entry.runtime_data)])


class ActiveInputsSensor(SoundboksEntity, SensorEntity):
    _attr_translation_key = "active_inputs"

    def __init__(self, coordinator: SoundboksCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_active_inputs"

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return describe_inputs(self.coordinator.data.inputs) or "None"
