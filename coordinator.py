"""BLE write orchestration for Wolink ESL devices."""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from homeassistant.components.bluetooth import (
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_process_advertisements,
)
from homeassistant.exceptions import HomeAssistantError

from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .const import (
    CONF_AD_TIMEOUT,
    CONF_CONNECT_TIMEOUT,
    CONF_DEVICE_MODEL,
    CONF_MAX_RETRY_COUNT,
    DEFAULT_AD_TIMEOUT,
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_RETRY_COUNT,
    DOMAIN,
)
from .wolink import (
    DEVICES,
    LabelConfig,
    ZhsunycoClient,
    process_pil_image,
    render_preview,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from bleak.backends.device import BLEDevice
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from PIL import Image as PILImage

_LOGGER = logging.getLogger(__name__)


class WolinkEslCoordinator:
    """Manages BLE communication for a single Wolink ESL device.

    Not a DataUpdateCoordinator — these are write-only devices with nothing to poll.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.address: str = entry.data["address"]
        self.device_model: str = entry.data[CONF_DEVICE_MODEL]
        self.label_config: LabelConfig = LabelConfig.from_device(self.device_model)
        self.device_profile: dict = DEVICES[self.device_model]
        self._lock = asyncio.Lock()
        self._ble_device: BLEDevice | None = None
        self._last_image_bytes: bytes | None = None  # PNG for preview
        self._image_entity: object | None = None  # WolinkDisplayPreview, set by entity

        # Display status tracking
        self.display_status: str = "idle"
        self.last_refresh: datetime | None = None
        self.last_error: str | None = None
        self._status_listeners: list[Callable[[], None]] = []

    def register_status_listener(self, callback: Callable[[], None]) -> None:
        """Register a callback to be invoked when display status changes."""
        self._status_listeners.append(callback)

    def _notify_status_listeners(self) -> None:
        """Notify all registered listeners of a status change."""
        for cb in self._status_listeners:
            cb()

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Update cached BLE device reference from advertisement callback."""
        self._ble_device = ble_device

    def set_image_entity(self, entity: object) -> None:
        """Register the ImageEntity for preview updates."""
        self._image_entity = entity

    def update_preview(self, png_bytes: bytes) -> None:
        """Update preview image and notify the ImageEntity."""
        self._last_image_bytes = png_bytes
        if self._image_entity is not None:
            self._image_entity.update_image(png_bytes)

    def _get_cached_ble_device(self) -> BLEDevice | None:
        """Return cached BLE device if available (may be stale)."""
        ble_device = async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is not None:
            return ble_device
        return self._ble_device

    async def _wait_for_advertisement(self, timeout: float) -> BLEDevice | None:
        """Wait for a fresh BLE advertisement from this device.

        Uses HA's bluetooth stack to detect the device advertising,
        guaranteeing a fresh reference within the device's current wake window.
        """
        _LOGGER.debug("Device %s: waiting for advertisement (up to %.0fs)...", self.address, timeout)

        def _match(_service_info: BluetoothServiceInfoBleak) -> bool:
            return True  # Any advertisement from our address is a match

        try:
            service_info = await async_process_advertisements(
                self.hass,
                _match,
                {"address": self.address, "connectable": True},
                BluetoothScanningMode.ACTIVE,
                timeout,
            )
            return service_info.device
        except TimeoutError:
            return None

    async def async_send_image(
        self,
        pil_image: PILImage.Image,
        *,
        dither: bool | str = True,
        color_mode: str | None = None,
        dither_mask: PILImage.Image | None = None,
    ) -> None:
        """Full pipeline: quantize PIL image, send via BLE, update preview."""
        async with self._lock:
            self.display_status = "sending"
            self.last_error = None
            self._notify_status_listeners()

            if color_mode is None:
                color_mode = self.device_profile["color"]

            # Prepare image data BEFORE scanning — minimize time between
            # finding the device and writing to it (ESL tags sleep aggressively)
            planes = await self.hass.async_add_executor_job(
                process_pil_image,
                pil_image,
                self.label_config,
                color_mode,
                dither,
                1.0, 1.0, True, True,
                dither_mask,
            )

            preview_img = await self.hass.async_add_executor_job(
                render_preview,
                planes[0], planes[1], planes[2],
                self.label_config.width, self.label_config.height,
            )

            buf = io.BytesIO()
            await self.hass.async_add_executor_job(preview_img.save, buf, "PNG")
            png_bytes = buf.getvalue()

            # Try connecting and sending. Strategy:
            # 1. First try cached device reference (instant, works if device is awake)
            # 2. If connect fails, wait for a fresh advertisement and connect
            #    immediately within the same wake window
            # 3. Repeat up to max_attempts times
            max_attempts = self.entry.options.get(CONF_MAX_RETRY_COUNT, DEFAULT_RETRY_COUNT)
            ad_timeout = self.entry.options.get(CONF_AD_TIMEOUT, DEFAULT_AD_TIMEOUT)
            connect_timeout = self.entry.options.get(CONF_CONNECT_TIMEOUT, DEFAULT_CONNECT_TIMEOUT)
            last_err: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                # Try cached device first (fast path)
                ble_device = self._get_cached_ble_device()

                if ble_device is not None:
                    try:
                        ble_client = await establish_connection(
                            BleakClientWithServiceCache,
                            ble_device,
                            self.address,
                            max_attempts=1,
                            timeout=connect_timeout,
                        )
                    except Exception as err:
                        _LOGGER.debug(
                            "Attempt %d/%d: cached device %s connect failed: %s, waiting for fresh advertisement",
                            attempt, max_attempts, self.address, err,
                        )
                        self._ble_device = None
                        ble_device = None  # Fall through to advertisement wait

                # If cache miss or cache connect failed, wait for fresh advertisement
                if ble_device is None:
                    ble_device = await self._wait_for_advertisement(timeout=ad_timeout)
                    if ble_device is None:
                        _LOGGER.warning(
                            "Attempt %d/%d: device %s not found (no advertisement within timeout)",
                            attempt, max_attempts, self.address,
                        )
                        last_err = HomeAssistantError(
                            f"Wolink ESL device {self.address} is not available. "
                            "Make sure the device is powered on and within Bluetooth range."
                        )
                        continue

                    try:
                        ble_client = await establish_connection(
                            BleakClientWithServiceCache,
                            ble_device,
                            self.address,
                            max_attempts=1,
                            timeout=connect_timeout,
                        )
                    except Exception as err:
                        _LOGGER.warning(
                            "Attempt %d/%d: connect to %s failed after fresh advertisement: %s",
                            attempt, max_attempts, self.address, err,
                        )
                        last_err = err
                        self._ble_device = None
                        continue

                try:
                    client = ZhsunycoClient(ble_device, config=self.label_config)
                    client.set_client(ble_client)
                    await client.initialize()
                    await client.send_image_planes(*planes)
                except Exception as err:
                    _LOGGER.warning(
                        "Attempt %d/%d: send to %s failed: %s",
                        attempt, max_attempts, self.address, err,
                    )
                    last_err = err
                    self._ble_device = None
                    continue
                finally:
                    await ble_client.disconnect()

                # Success — update preview and status, then return
                self.update_preview(png_bytes)
                self.display_status = "success"
                self.last_refresh = datetime.now(UTC)
                self.last_error = None
                self._notify_status_listeners()
                _LOGGER.info(
                    "Image sent to %s (%s) on attempt %d",
                    self.address, self.device_profile["name"], attempt,
                )
                return

            # All attempts exhausted
            self.display_status = "error"
            self.last_error = str(last_err)
            self._notify_status_listeners()
            raise HomeAssistantError(
                f"Failed to send image to {self.address} after {max_attempts} attempts: {last_err}"
            ) from last_err
