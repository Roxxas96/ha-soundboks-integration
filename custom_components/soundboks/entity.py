"""Base entity: one device per speaker."""

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SoundboksCoordinator


class SoundboksEntity(CoordinatorEntity[SoundboksCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SoundboksCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer=MANUFACTURER,
            model="SOUNDBOKS (BLE)",
            name=coordinator.config_entry.title,
            sw_version=coordinator.firmware,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.present and self.coordinator.data is not None
