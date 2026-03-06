import functools
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import ServiceCall, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from pychromecast import Chromecast
from pychromecast.controllers.dashcast import DashCastController

_LOGGER = logging.getLogger(__name__)

DOMAIN = "dash_cast"

LOAD_URL_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required("url"): cv.string,
        vol.Optional("force", default=False): cv.boolean,
        vol.Optional("reload_seconds", default=0): cv.positive_int,
    }
)


def _get_media_player_entities(hass: HomeAssistant):
    """Return all media_player entities using the modern entity component approach."""
    entity_component = hass.data.get("entity_components", {}).get("media_player")
    if entity_component is None:
        entity_component = hass.data.get("media_player")
    if entity_component is not None:
        return list(entity_component.entities)
    return []


def _register_service(hass: HomeAssistant) -> None:
    """Register the load_url service if not already registered."""
    if hass.services.has_service(DOMAIN, "load_url"):
        return

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    dashs: dict = hass.data[DOMAIN].setdefault("dashs", {})

    async def play_media(call: ServiceCall) -> None:
        kwargs = dict(call.data)
        entity_ids = kwargs.pop(ATTR_ENTITY_ID)

        entities = _get_media_player_entities(hass)
        if not entities:
            _LOGGER.warning("No media_player entities found; cannot cast URL")
            return

        for entity in entities:
            if entity.entity_id not in entity_ids:
                continue

            try:
                dash: DashCastController = dashs.get(entity.entity_id)
                if not dash:
                    chromecast: Chromecast = getattr(entity, "_chromecast", None)
                    if chromecast is None:
                        _LOGGER.warning(
                            "Entity %s has no _chromecast attribute; skipping",
                            entity.entity_id,
                        )
                        continue
                    dash = DashCastController()
                    chromecast.register_handler(dash)
                    dashs[entity.entity_id] = dash

                await hass.async_add_executor_job(
                    functools.partial(dash.load_url, **kwargs)
                )
            except Exception:
                _LOGGER.exception(
                    "Error casting URL to %s", entity.entity_id
                )

    hass.services.async_register(DOMAIN, "load_url", play_media, LOAD_URL_SCHEMA)
    _LOGGER.debug("Registered service %s.load_url", DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    _register_service(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    _register_service(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    remaining = hass.config_entries.async_entries(DOMAIN)
    if len(remaining) == 1:
        if hass.services.has_service(DOMAIN, "load_url"):
            hass.services.async_remove(DOMAIN, "load_url")
            _LOGGER.debug("Unregistered service %s.load_url", DOMAIN)
        hass.data.pop(DOMAIN, None)
    return True
