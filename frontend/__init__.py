"""JavaScript module registration for the frontend card."""

import logging
from pathlib import Path
from typing import Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later

from ..const import JSMODULES, URL_BASE

_LOGGER = logging.getLogger(__name__)

# Compiled JS lives in the www/ sibling directory.
_WWW_DIR = Path(__file__).parent.parent / "www"
_FONTS_DIR = Path(__file__).parent.parent / "fonts"

_FONT_FILES = (
    "rbm.ttf",
    "ppb.ttf",
    "DejaVuSans.ttf",
    "materialdesignicons-webfont.ttf",
    "materialdesignicons-webfont_meta.json",
)


class JSModuleRegistration:
    """Registers JavaScript modules as Lovelace resources."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize."""
        self.hass = hass
        self.lovelace = hass.data.get(LOVELACE_DATA)

    async def async_register(self) -> None:
        """Register static paths and Lovelace resources."""
        await self._async_register_static_paths()
        if self.lovelace and self.lovelace.resource_mode == "storage":
            await self._async_wait_for_lovelace_resources()

    async def _async_register_static_paths(self) -> None:
        """Serve www/ and fonts/ at URL_BASE."""
        paths = [StaticPathConfig(URL_BASE, str(_WWW_DIR), False)]
        for font_file in _FONT_FILES:
            font_path = _FONTS_DIR / font_file
            if font_path.is_file():
                paths.append(
                    StaticPathConfig(
                        f"{URL_BASE}/fonts/{font_file}",
                        str(font_path),
                        True,
                    )
                )
        try:
            await self.hass.http.async_register_static_paths(paths)
            _LOGGER.debug("Registered static path: %s", URL_BASE)
        except RuntimeError:
            _LOGGER.debug("Static path already registered: %s", URL_BASE)

    async def _async_wait_for_lovelace_resources(self) -> None:
        """Wait for Lovelace resources to be loaded, then register modules."""

        async def _check_loaded(_now: Any) -> None:
            if self.lovelace.resources.loaded:
                await self._async_register_modules()
            else:
                _LOGGER.debug("Lovelace resources not loaded yet, retrying in 5s")
                async_call_later(self.hass, 5, _check_loaded)

        await _check_loaded(0)

    async def _async_register_modules(self) -> None:
        """Add or update JS modules in Lovelace resources."""
        existing = list(self.lovelace.resources.async_items())

        for module in JSMODULES:
            url = f"{URL_BASE}/{module['filename']}"
            versioned_url = f"{url}?v={module['version']}"
            registered = False

            for resource in existing:
                if self._strip_query(resource["url"]) == url:
                    registered = True
                    if self._extract_version(resource["url"]) != module["version"]:
                        _LOGGER.info(
                            "Updating %s to version %s",
                            module["name"],
                            module["version"],
                        )
                        await self.lovelace.resources.async_update_item(
                            resource["id"],
                            {"res_type": "module", "url": versioned_url},
                        )
                    break

            if not registered:
                _LOGGER.info(
                    "Registering new Lovelace resource: %s v%s",
                    module["name"],
                    module["version"],
                )
                await self.lovelace.resources.async_create_item(
                    {"res_type": "module", "url": versioned_url}
                )

    async def async_unregister(self) -> None:
        """Remove this integration's Lovelace resources (for uninstall cleanup)."""
        if not self.lovelace or self.lovelace.resource_mode != "storage":
            return
        for module in JSMODULES:
            url_prefix = f"{URL_BASE}/{module['filename']}"
            for resource in self.lovelace.resources.async_items():
                if resource["url"].startswith(url_prefix):
                    await self.lovelace.resources.async_delete_item(resource["id"])

    @staticmethod
    def _strip_query(url: str) -> str:
        return url.split("?")[0]

    @staticmethod
    def _extract_version(url: str) -> str:
        parts = url.split("?v=")
        return parts[1] if len(parts) > 1 else "0"
