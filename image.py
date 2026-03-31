"""ImageEntity for Wolink ESL display preview."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.image import ImageEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from .coordinator import WolinkEslCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wolink ESL image entity."""
    coordinator: WolinkEslCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WolinkDisplayPreview(coordinator)])


class WolinkDisplayPreview(ImageEntity):
    """Shows the last rendered/sent display content as a live preview."""

    _attr_content_type = "image/png"
    _attr_has_entity_name = True
    _attr_name = "Display"

    def __init__(self, coordinator: WolinkEslCoordinator) -> None:
        """Initialize the image entity."""
        super().__init__(coordinator.hass)
        self._coordinator = coordinator
        self._current_image: bytes | None = None
        self._attr_unique_id = f"{coordinator.address}_display"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            name=f"Wolink ESL {coordinator.device_profile['name']}",
            manufacturer="Zhsunyco/Wolink",
            model=coordinator.device_profile["name"],
        )
        # Register with coordinator for preview updates
        coordinator.set_image_entity(self)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose display dimensions so other integrations can auto-detect them."""
        return {
            "display_width": self._coordinator.label_config.width,
            "display_height": self._coordinator.label_config.height,
        }

    async def async_image(self) -> bytes | None:
        """Return the current preview image bytes."""
        return self._current_image

    def update_image(self, image_bytes: bytes) -> None:
        """Update preview and trigger HA state change for instant frontend refresh."""
        self._current_image = image_bytes
        self._attr_image_last_updated = dt_util.utcnow()
        self.async_write_ha_state()
