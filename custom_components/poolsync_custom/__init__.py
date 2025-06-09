"""The PoolSync Custom integration."""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed

# Assuming other v2 files are in place
from .api import (
    PoolSyncApiClient,
    PoolSyncApiAuthError, # Used in coordinator, but good to be aware of
    PoolSyncApiCommunicationError, # Used in coordinator
)
from .const import (
    API_RESPONSE_MAC_ADDRESS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    OPTION_SCAN_INTERVAL, # For options listener
    PLATFORMS, # Defined in const.py
)
from .coordinator import PoolSyncDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
        
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PoolSync Custom from a config entry."""
    _LOGGER.info(
        "Setting up PoolSync integration for entry %s (IP: %s, Title: %s)",
        entry.entry_id,
        entry.data.get(CONF_IP_ADDRESS),
        entry.title
    )

    hass.data.setdefault(DOMAIN, {})

    ip_address = entry.data[CONF_IP_ADDRESS]
    password = entry.data[CONF_PASSWORD]
    # MAC address is stored during config flow, used for unique ID and device info
    mac_address = entry.data.get(API_RESPONSE_MAC_ADDRESS)
    if not mac_address: # Should always be there from config flow
        _LOGGER.error("MAC address not found in config entry data for %s. This is unexpected.", ip_address)
        # Fallback, though this indicates an issue in config flow saving
        mac_address = f"ip_{ip_address.replace('.', '_')}"


    session = async_get_clientsession(hass)
    api_client = PoolSyncApiClient(ip_address=ip_address, session=session)

    # Get scan interval from options, or default if not set
    scan_interval = entry.options.get(OPTION_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    _LOGGER.debug("Using scan interval of %d seconds for %s", scan_interval, ip_address)

    coordinator = PoolSyncDataUpdateCoordinator(
        hass=hass,
        api_client=api_client,
        password=password,
        update_interval_seconds=scan_interval,
        config_entry_id=entry.entry_id, # For context
        mac_address=mac_address # For device info and unique IDs
    )

    try:
        _LOGGER.debug("Attempting initial data refresh for %s", ip_address)
        await coordinator.async_config_entry_first_refresh()
        _LOGGER.debug("Initial data refresh successful for %s.", ip_address)
        if not coordinator.data:
             _LOGGER.warning("Initial data refresh for %s succeeded but coordinator.data is empty. Check API response.", ip_address)
             # Depending on strictness, could raise ConfigEntryNotReady if data is essential for setup.
             # For now, proceed, entities will handle missing data.
    except ConfigEntryAuthFailed as err:
        _LOGGER.error("Authentication failed for %s during initial refresh: %s", ip_address, err)
        raise # Re-raise to trigger reauth flow or mark entry as failed
    except UpdateFailed as err: # Covers communication and other API errors from coordinator
        _LOGGER.error("Initial data update failed for %s: %s", ip_address, err)
        raise ConfigEntryNotReady(f"Could not connect or fetch data from {ip_address}: {err}") from err
    except Exception as err: # Catch any other unexpected errors
        _LOGGER.exception("Unexpected error during initial refresh for %s: %s", ip_address, err)
        raise ConfigEntryNotReady(f"Unexpected error setting up PoolSync for {ip_address}: {err}") from err

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Listen for option updates. This will reload the entry when options change.
    entry.async_on_unload(entry.add_update_listener(async_update_options_listener))

    # Forward the setup to the platforms (sensor, binary_sensor, etc.)
    # This will call async_setup_entry in sensor.py, binary_sensor.py
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("PoolSync integration setup complete for %s", entry.title)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info(
        "Unloading PoolSync integration for entry %s (IP: %s, Title: %s)",
        entry.entry_id,
        entry.data.get(CONF_IP_ADDRESS),
        entry.title
    )

    # Unload platforms (sensor, binary_sensor, etc.)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        if entry.entry_id in hass.data[DOMAIN]:
            # Optional: If coordinator has specific cleanup (e.g. cancelling tasks), call it here
            # coordinator: PoolSyncDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
            # coordinator.async_shutdown() # Example if such a method existed
            del hass.data[DOMAIN][entry.entry_id]
            _LOGGER.debug("Removed coordinator from hass.data for %s", entry.title)

        if not hass.data[DOMAIN]: # If no more entries for this domain, clear the domain data
            hass.data.pop(DOMAIN)
            _LOGGER.debug("Domain %s data removed from hass.data as no entries remain.", DOMAIN)
        _LOGGER.info("PoolSync integration successfully unloaded for %s", entry.title)
    else:
        _LOGGER.error("Failed to unload PoolSync platforms for %s", entry.title)

    return unload_ok

async def async_update_options_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    _LOGGER.info("Options updated for %s (new interval: %s s), reloading integration.",
                 entry.title,
                 entry.options.get(OPTION_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    # This will call async_unload_entry and then async_setup_entry for this config entry
    await hass.config_entries.async_reload(entry.entry_id)

# Optional: If you plan to change config entry versions and need migration
# async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
#     """Migrate old entry."""
#     _LOGGER.debug("Migrating config entry from version %s for %s", config_entry.version, config_entry.title)
#     # ... migration logic ...
#     # config_entry.version = NEW_VERSION
#     # hass.config_entries.async_update_entry(config_entry, data=new_data)
#     _LOGGER.info("Migration to version %s successful for %s", NEW_VERSION, config_entry.title)
#     return True
