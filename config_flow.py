"""Config flow for Wolink BLE E-Paper Labels."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.selector import selector

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
from .wolink import DEVICES, WOLINK_SERVICE_UUID, KNOWN_NAME_PREFIX

MODEL_CHOICES = {
    key: f"{profile['name']} ({profile['width']}x{profile['height']})"
    for key, profile in DEVICES.items()
}


class WolinkEslConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wolink ESL."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return WolinkEslOptionsFlowHandler(config_entry)

    def __init__(self) -> None:
        """Initialize."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle Bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm Bluetooth discovery and select device model."""
        if user_input is not None:
            assert self._discovery_info is not None
            return self.async_create_entry(
                title=self._discovery_info.name or f"Wolink ESL {self._discovery_info.address}",
                data={
                    CONF_ADDRESS: self._discovery_info.address,
                    CONF_DEVICE_MODEL: user_input[CONF_DEVICE_MODEL],
                },
            )

        assert self._discovery_info is not None
        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_MODEL, default="290"): vol.In(MODEL_CHOICES),
                }
            ),
            description_placeholders={"name": self._discovery_info.name or "Unknown"},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Wolink ESL {address}",
                data={
                    CONF_ADDRESS: address,
                    CONF_DEVICE_MODEL: user_input[CONF_DEVICE_MODEL],
                },
            )

        # Discover available Wolink devices
        self._discovered_devices = {}
        for info in async_discovered_service_info(self.hass):
            if self._is_wolink_device(info):
                # Skip already configured devices
                if self._address_already_configured(info.address):
                    continue
                self._discovered_devices[info.address] = info

        if self._discovered_devices:
            # Show picker for discovered devices
            address_choices = {
                addr: f"{info.name or 'Unknown'} ({addr})"
                for addr, info in self._discovered_devices.items()
            }
            schema = vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(address_choices),
                    vol.Required(CONF_DEVICE_MODEL, default="290"): vol.In(MODEL_CHOICES),
                }
            )
        else:
            # No devices found — fall back to manual MAC entry
            schema = vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): str,
                    vol.Required(CONF_DEVICE_MODEL, default="290"): vol.In(MODEL_CHOICES),
                }
            )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    def _is_wolink_device(self, info: BluetoothServiceInfoBleak) -> bool:
        """Check if a discovered device is a Wolink ESL."""
        # Match by service UUID
        for uuid in info.service_uuids:
            if uuid.lower() == WOLINK_SERVICE_UUID.lower():
                return True
        # Match by name prefix
        if info.name and info.name.startswith(KNOWN_NAME_PREFIX):
            return True
        return False

    def _address_already_configured(self, address: str) -> bool:
        """Check if an address is already configured."""
        for entry in self._async_current_entries():
            if entry.data.get(CONF_ADDRESS) == address:
                return True
        return False


class WolinkEslOptionsFlowHandler(OptionsFlow):
    """Handle options flow for Wolink ESL."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    @property
    def config_entry(self):
        """Return config entry (compat shim for older HA)."""
        # Newer HA provides self.config_entry natively via OptionsFlow;
        # older HA does not, so we store it ourselves.
        return self._config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage connection retry options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MAX_RETRY_COUNT,
                        default=self.config_entry.options.get(
                            CONF_MAX_RETRY_COUNT, DEFAULT_RETRY_COUNT
                        ),
                    ): selector({"number": {"min": 1, "max": 10, "mode": "box"}}),
                    vol.Required(
                        CONF_AD_TIMEOUT,
                        default=self.config_entry.options.get(
                            CONF_AD_TIMEOUT, DEFAULT_AD_TIMEOUT
                        ),
                    ): selector({"number": {"min": 10, "max": 300, "mode": "box", "unit_of_measurement": "s"}}),
                    vol.Required(
                        CONF_CONNECT_TIMEOUT,
                        default=self.config_entry.options.get(
                            CONF_CONNECT_TIMEOUT, DEFAULT_CONNECT_TIMEOUT
                        ),
                    ): selector({"number": {"min": 5, "max": 60, "mode": "box", "unit_of_measurement": "s"}}),
                }
            ),
        )
