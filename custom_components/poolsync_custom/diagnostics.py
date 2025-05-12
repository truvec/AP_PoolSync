"""Diagnostics support for the PoolSync Custom integration."""
import traceback # For logging detailed error in diagnostics itself
from typing import Any, Dict, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, API_RESPONSE_MAC_ADDRESS
from .coordinator import PoolSyncDataUpdateCoordinator

import logging
_LOGGER = logging.getLogger(__name__)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""
    _LOGGER.debug("Attempting to gather diagnostics for entry ID: %s", entry.entry_id)
    diagnostics_data: Dict[str, Any] = {
        "config_entry_info": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "domain": entry.domain,
            "data": dict(entry.data), # HA core redacts common sensitive keys
            "options": dict(entry.options),
            "source": str(entry.source),
            "disabled_by": str(entry.disabled_by) if entry.disabled_by else None,
            "version": entry.version,
        },
        "coordinator_status": "Coordinator not found or not initialized.",
        "coordinator_data_payload": "Coordinator data not available.",
        "device_registry_info": "Device registry information not available.",
        "error_in_diagnostics": None, # To capture any error during diagnostics gathering
    }

    try:
        coordinator: Optional[PoolSyncDataUpdateCoordinator] = hass.data.get(DOMAIN, {}).get(entry.entry_id)

        if coordinator:
            diagnostics_data["coordinator_status"] = {
                "last_update_success": coordinator.last_update_success,
                "last_update_success_time": coordinator.last_update_success_time.isoformat() if coordinator.last_update_success_time else None,
                "update_interval_seconds": coordinator.update_interval.total_seconds() if coordinator.update_interval else None,
                "coordinator_name": coordinator.name,
                "mac_address_from_coordinator": getattr(coordinator, 'mac_address', 'N/A'),
                "ip_address_from_coordinator": getattr(coordinator.api_client, '_ip_address', 'N/A') if hasattr(coordinator, 'api_client') else 'N/A',
            }
            diagnostics_data["coordinator_data_payload"] = coordinator.data if coordinator.data is not None else "Data is None"

            try:
                device_registry = dr.async_get(hass)
                mac_address = getattr(coordinator, 'mac_address', None)
                if mac_address:
                    device = device_registry.async_get_device(identifiers={(DOMAIN, mac_address)})
                    if device:
                        diagnostics_data["device_registry_info"] = {
                            "id": device.id,
                            "identifiers": list(list(identifier) for identifier in device.identifiers),
                            "connections": list(list(connection) for connection in device.connections),
                            "manufacturer": device.manufacturer,
                            "model": device.model,
                            "name": device.name,
                            "name_by_user": device.name_by_user,
                            "sw_version": device.sw_version,
                            "hw_version": device.hw_version,
                            "via_device_id": device.via_device_id,
                            "area_id": device.area_id,
                            "entry_type": str(device.entry_type) if device.entry_type else None,
                            "configuration_url": device.configuration_url,
                            "is_new": device.is_new,
                            "disabled_by_device_reg": str(device.disabled_by) if device.disabled_by else None,
                        }
                    else:
                        diagnostics_data["device_registry_info"] = f"Device with MAC {mac_address} not found in registry."
                else:
                    diagnostics_data["device_registry_info"] = "MAC address not available from coordinator to look up device."
            except Exception as e_dev_reg:
                _LOGGER.error("Error gathering device registry info for diagnostics: %s", e_dev_reg)
                diagnostics_data["device_registry_info"] = f"Error: {str(e_dev_reg)}"
                diagnostics_data["error_in_diagnostics"] = (diagnostics_data["error_in_diagnostics"] or "") + f"DeviceReg Error: {traceback.format_exc()}; "

        else:
            _LOGGER.warning("Diagnostics: Coordinator not found in hass.data for entry ID %s.", entry.entry_id)

    except Exception as e_diag:
        _LOGGER.exception("Unexpected error while gathering diagnostics for entry ID %s: %s", entry.entry_id, e_diag)
        diagnostics_data["error_in_diagnostics"] = (diagnostics_data["error_in_diagnostics"] or "") + f"Overall Diagnostics Error: {traceback.format_exc()}"

    _LOGGER.debug("Finished gathering diagnostics for entry ID %s. Error in diagnostics: %s", entry.entry_id, diagnostics_data["error_in_diagnostics"])
    return diagnostics_data

