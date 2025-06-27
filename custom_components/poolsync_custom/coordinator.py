"""DataUpdateCoordinator for the PoolSync Custom integration."""
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.device_registry import DeviceInfo # For providing device info

from .api import (
    PoolSyncApiClient,
    PoolSyncApiAuthError,
    PoolSyncApiCommunicationError,
    PoolSyncApiError,
)
from .const import DOMAIN, MANUFACTURER, MODEL, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)


class PoolSyncDataUpdateCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Class to manage fetching PoolSync data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: PoolSyncApiClient,
        password: str, # Password needed for API calls
        update_interval_seconds: int,
        config_entry_id: str, # For logging/context
        mac_address: str,     # For unique device identification
    ) -> None:
        """Initialize the data update coordinator."""
        self.api_client = api_client
        self._password = password # Store password for use by entities/services via coordinator
        self.config_entry_id = config_entry_id
        self.mac_address = mac_address
        # Store IP from client for device_info configuration_url
        self._ip_address = api_client._ip_address # Accessing protected member

        # Create a more specific logger name for this coordinator instance
        logger_name = f"{DOMAIN}({self.mac_address or self._ip_address})"
        
        super().__init__(
            hass,
            _LOGGER, # Use the module logger
            name=logger_name, # Name of the coordinator instance (for logging)
            update_interval=timedelta(seconds=update_interval_seconds),
            update_method=self._async_update_data, # Set the update method
        )
        _LOGGER.info(
            "PoolSync coordinator initialized for %s (MAC: %s, IP: %s) with update interval %d seconds",
            self.name, self.mac_address, self._ip_address, update_interval_seconds
        )
            
    async def _async_update_data(self) -> Dict[str, Any]:
        """
        Fetch data from the PoolSync device API.
        This method is called by the DataUpdateCoordinator base class.
        """
        _LOGGER.debug("Coordinator %s: Attempting to fetch data.", self.name)
        try:
            # Use the stored password to fetch all data
            data = await self.api_client.get_all_data(self._password)
            _LOGGER.debug("Coordinator %s: Successfully fetched data. Keys: %s", self.name, data.keys() if isinstance(data, dict) else "N/A")
            if not isinstance(data, dict) or not all(k in data for k in ["poolSync", "devices"]):
                _LOGGER.error("Coordinator %s: Fetched data is not a dict or essential keys ('poolSync', 'devices') are missing. Data: %s", self.name, data)
                raise UpdateFailed(f"Malformed data received from {self.name}: essential keys missing or data not a dict.")
            return data # Return the full data structure

        except PoolSyncApiAuthError as err:
            _LOGGER.error("Coordinator %s: Authentication error fetching data: %s (Status: %s)", self.name, err, getattr(err, 'status_code', 'N/A'))
            raise ConfigEntryAuthFailed(f"Authentication failed for {self.name}. Password may be invalid.") from err
        
        except PoolSyncApiCommunicationError as err:
            _LOGGER.warning("Coordinator %s: Communication error fetching data: %s. Will retry.", self.name, err)
            raise UpdateFailed(f"Error communicating with PoolSync device {self.name}: {err}") from err

        except PoolSyncApiError as err: # Other API-level errors
            _LOGGER.error("Coordinator %s: API error fetching data: %s (Status: %s, Body: %s)", self.name, err, getattr(err, 'status_code', 'N/A'), getattr(err, 'body', 'N/A'))
            raise UpdateFailed(f"API error for {self.name}: {err}") from err

        except Exception as err: # Catch any other unexpected exceptions
            _LOGGER.exception("Coordinator %s: Unexpected error fetching data: %s", self.name, err)
            raise UpdateFailed(f"Unexpected error updating {self.name}: {err}") from err

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for entities to use."""
        device_name = DEFAULT_NAME
        model_name = MODEL
        sw_version = None
        hw_version = None
        config_name_from_api: Optional[str] = None

        if self.data and isinstance(self.data.get("poolSync"), dict):
            poolsync_main_data = self.data["poolSync"]
            if isinstance(poolsync_main_data.get("config"), dict):
                config_name_from_api = poolsync_main_data["config"].get("name")
            if isinstance(poolsync_main_data.get("system"), dict):
                system_info = poolsync_main_data["system"]
                sw_version = system_info.get("fwVersion")
                hw_version = system_info.get("hwVersion")

        if self.data and isinstance(self.data.get("devices"), dict) and \
           isinstance(self.data["devices"].get("0"), dict):
            device0_data = self.data["devices"]["0"]
            if isinstance(device0_data.get("nodeAttr"), dict):
                api_model_name = device0_data["nodeAttr"].get("name")
                if api_model_name: # Use ChlorSync® as model if available
                    model_name = api_model_name

        if config_name_from_api and config_name_from_api != "PoolSync®":
            device_name = config_name_from_api
        else:
            device_name = f"{DEFAULT_NAME} {self.mac_address[-6:]}" if self.mac_address and len(self.mac_address) >= 6 else DEFAULT_NAME

        return DeviceInfo(
            identifiers={(DOMAIN, self.mac_address)},
            name=device_name,
            manufacturer=MANUFACTURER,
            model=str(model_name) if model_name else MODEL,
            sw_version=str(sw_version) if sw_version is not None else None,
            hw_version=str(hw_version) if hw_version is not None else None,
            configuration_url=f"http://{self._ip_address}",
        )
