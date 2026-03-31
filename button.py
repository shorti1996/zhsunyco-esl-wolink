"""Button entity for Wolink ESL display refresh."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from .coordinator import WolinkEslCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wolink ESL button entity."""
    coordinator: WolinkEslCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([WolinkRefreshButton(coordinator)])


class WolinkRefreshButton(ButtonEntity):
    """Re-sends the last image to the e-paper display."""

    _attr_has_entity_name = True
    _attr_name = "Refresh Display"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: WolinkEslCoordinator) -> None:
        """Initialize the button entity."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.address}_refresh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
        )

    async def async_press(self) -> None:
        """Re-send the last cached image to the device."""
        if self._coordinator._last_image_bytes is None:
            _LOGGER.warning(
                "No image to refresh for %s — send an image first",
                self._coordinator.address,
            )
            return

        from PIL import Image

        buf = io.BytesIO(self._coordinator._last_image_bytes)
        pil_image = await self.hass.async_add_executor_job(Image.open, buf)
        await self._coordinator.async_send_image(pil_image)
