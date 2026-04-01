"""Wolink BLE E-Paper Labels integration for Home Assistant."""

from __future__ import annotations

# Bootstrap bundled library if not installed (e.g. HACS deployment)
import importlib, sys, pathlib  # noqa: E401
if not importlib.util.find_spec("zhsunyco_esl"):
    _whl = next(pathlib.Path(__file__).parent.glob("zhsunyco_esl-*.whl"), None)
    if _whl:
        sys.path.append(str(_whl))

import io
import logging
from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothScanningMode,
)
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import CoreState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .const import CONF_MIRROR, DEFAULT_MIRROR, DOMAIN
from .coordinator import WolinkEslCoordinator
from .frontend import JSModuleRegistration

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.IMAGE, Platform.BUTTON, Platform.SENSOR]

SERVICE_SEND_IMAGE = "send_image"
SERVICE_DRAWCUSTOM = "drawcustom"

SEND_IMAGE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("image"): cv.string,
        vol.Optional("dither", default=True): cv.boolean,
        vol.Optional("compress"): cv.boolean,
        vol.Optional("mirror"): cv.string,
    }
)

DRAWCUSTOM_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("payload"): list,
        vol.Optional("background", default="white"): cv.string,
        vol.Optional("rotate", default=0): vol.Coerce(int),
        vol.Optional("dither", default="floyd-steinberg"): cv.string,
        vol.Optional("dry_run", default=False): cv.boolean,
        vol.Optional("ttl"): vol.Any(int, None),
        vol.Optional("compress"): cv.boolean,
        vol.Optional("mirror"): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up integration — register frontend and services once."""
    hass.data.setdefault(DOMAIN, {})

    _register_services(hass)

    async def _register_frontend(_event=None) -> None:
        registrar = JSModuleRegistration(hass)
        await registrar.async_register()
        hass.data[DOMAIN]["frontend_registrar"] = registrar

    if hass.state is CoreState.running:
        await _register_frontend()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register_frontend)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wolink ESL from a config entry."""
    coordinator = WolinkEslCoordinator(hass, entry)

    # Get initial BLE device reference
    ble_device = bluetooth.async_ble_device_from_address(
        hass, entry.data[CONF_ADDRESS], connectable=True
    )
    if ble_device:
        coordinator.set_ble_device(ble_device)

    # Register BLE advertisement callback to keep device reference fresh
    # and parse manufacturer data for battery voltage / firmware versions
    def _handle_advertisement(service_info, change):
        coordinator.set_ble_device(service_info.device)
        if service_info.manufacturer_data:
            coordinator.update_from_advertisement(service_info.manufacturer_data)

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _handle_advertisement,
            BluetoothCallbackMatcher(address=entry.data[CONF_ADDRESS]),
            BluetoothScanningMode.PASSIVE,
        )
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def async_handle_send_image(call: ServiceCall) -> None:
        """Handle the send_image service call."""
        entity_id = call.data["entity_id"]
        image_path = call.data["image"]
        dither = call.data.get("dither", True)

        coordinator = _get_coordinator_for_entity(hass, entity_id)
        if coordinator is None:
            raise HomeAssistantError(
                f"Could not find Wolink ESL device for entity {entity_id}"
            )

        from PIL import Image

        try:
            pil_image = await hass.async_add_executor_job(Image.open, image_path)
        except Exception as err:
            raise HomeAssistantError(f"Failed to open image: {err}") from err

        await coordinator.async_send_image(
            pil_image, dither=dither, compress=call.data.get("compress"),
            mirror=call.data.get("mirror"),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_IMAGE,
        async_handle_send_image,
        schema=SEND_IMAGE_SCHEMA,
    )

    async def async_handle_drawcustom(call: ServiceCall) -> None:
        """Handle the drawcustom service call."""
        from .imagegen import render_drawcustom

        entity_id = call.data["entity_id"]
        coordinator = _get_coordinator_for_entity(hass, entity_id)
        if coordinator is None:
            raise HomeAssistantError(
                f"Could not find Wolink ESL device for entity {entity_id}"
            )

        dither_method = call.data.get("dither", "floyd-steinberg")
        pil_image, dither_mask = await render_drawcustom(
            hass,
            call.data["payload"],
            coordinator.label_config.width,
            coordinator.label_config.height,
            background=call.data.get("background", "white"),
            rotate=int(call.data.get("rotate", 0)),
            dither=dither_method,
        )

        if call.data.get("dry_run", False):
            # Quantize + render preview so it matches what the display will show
            from .wolink import process_pil_image, render_preview

            from PIL.Image import Transpose

            mirror = call.data.get("mirror")
            if mirror is None:
                mirror = coordinator.entry.options.get(CONF_MIRROR, DEFAULT_MIRROR)
            if mirror and mirror != "none":
                _LOGGER.debug("dry_run: applying %s mirror", mirror)
                if mirror == "horizontal":
                    pil_image = pil_image.transpose(Transpose.FLIP_LEFT_RIGHT)
                elif mirror == "vertical":
                    pil_image = pil_image.transpose(Transpose.FLIP_TOP_BOTTOM)
            else:
                _LOGGER.debug("dry_run: no mirror (mirror=%s)", mirror)

            planes = await hass.async_add_executor_job(
                process_pil_image,
                pil_image,
                coordinator.label_config,
                coordinator.device_profile["color"],
                dither_method,
                1.0, 1.0, True, True,
                dither_mask,
            )
            preview_img = await hass.async_add_executor_job(
                render_preview,
                planes[0], planes[1], planes[2],
                coordinator.label_config.width, coordinator.label_config.height,
            )
            buf = io.BytesIO()
            await hass.async_add_executor_job(preview_img.save, buf, "PNG")
            coordinator.update_preview(buf.getvalue())
            return

        await coordinator.async_send_image(
            pil_image,
            dither=dither_method,
            dither_mask=dither_mask,
            compress=call.data.get("compress"),
            mirror=call.data.get("mirror"),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_DRAWCUSTOM,
        async_handle_drawcustom,
        schema=DRAWCUSTOM_SCHEMA,
    )


def _get_coordinator_for_entity(
    hass: HomeAssistant, entity_id: str
) -> WolinkEslCoordinator | None:
    """Resolve an entity_id to its coordinator."""
    entity_reg = er.async_get(hass)
    entry = entity_reg.async_get(entity_id) if entity_reg else None

    if entry and entry.config_entry_id:
        return hass.data.get(DOMAIN, {}).get(entry.config_entry_id)

    # Fallback: if only one device configured, use it
    coordinators = [
        v for v in hass.data.get(DOMAIN, {}).values()
        if isinstance(v, WolinkEslCoordinator)
    ]
    if len(coordinators) == 1:
        return coordinators[0]

    return None
