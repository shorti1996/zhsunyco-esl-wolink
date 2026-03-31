"""Sensor entities for Wolink ESL devices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory

from .const import DISPLAY_STATUSES, DOMAIN

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import WolinkEslCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wolink ESL sensor entities."""
    coordinator: WolinkEslCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        WolinkResolutionSensor(coordinator),
        WolinkDisplayStatusSensor(coordinator),
        WolinkLastRefreshSensor(coordinator),
    ])


class WolinkResolutionSensor(SensorEntity):
    """Reports the display resolution (e.g., '296x128')."""

    _attr_has_entity_name = True
    _attr_name = "Display Resolution"
    _attr_icon = "mdi:monitor"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: WolinkEslCoordinator) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}_resolution"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
        )
        w = coordinator.label_config.width
        h = coordinator.label_config.height
        self._attr_native_value = f"{w}\u00d7{h}"


class WolinkDisplayStatusSensor(SensorEntity):
    """Current BLE communication status of the display."""

    _attr_has_entity_name = True
    _attr_name = "Display Status"
    _attr_icon = "mdi:information-outline"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = DISPLAY_STATUSES
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: WolinkEslCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}_display_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
        )

    @property
    def native_value(self) -> str:
        return self._coordinator.display_status

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._coordinator.last_error:
            return {"last_error": self._coordinator.last_error}
        return None

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_status_listener(self.async_write_ha_state)


class WolinkLastRefreshSensor(RestoreSensor):
    """Timestamp of last successful display refresh, persisted across restarts."""

    _attr_has_entity_name = True
    _attr_name = "Last Refresh"
    _attr_icon = "mdi:clock-check-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: WolinkEslCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}_last_refresh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
        )

    @property
    def native_value(self) -> datetime | None:
        return self._coordinator.last_refresh

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_data = await self.async_get_last_sensor_data()
        if last_data and last_data.native_value is not None:
            from datetime import datetime

            try:
                self._coordinator.last_refresh = datetime.fromisoformat(
                    str(last_data.native_value)
                )
            except (ValueError, TypeError):
                pass
        self._coordinator.register_status_listener(self.async_write_ha_state)
