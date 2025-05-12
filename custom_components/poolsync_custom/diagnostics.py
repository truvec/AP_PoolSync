"""Diagnostics support for the PoolSync Custom integration."""
import traceback # For logging detailed error in diagnostics itself
from typing import Any, Dict, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator # For type hinting

from .const import DOMAIN, API_RESPONSE_MAC_ADDRESS
# Ensure PoolSyncDataUpdateCoordinator is imported if type hinting is strict
# from .coordinator import PoolSyncDataUpdateCoordinator # Already imported below

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
        # Import here to avoid circular dependency if coordinator imports something from diagnostics
        from .coordinator import PoolSyncDataUpdateCoordinator
        coordinator: Optional[PoolSyncDataUpdateCoordinator] = hass.data.get(DOMAIN, {}).get(entry.entry_id)

        if coordinator:
            # The DataUpdateCoordinator base class has 'last_update_success' (bool)
            # and 'data' (the payload).
            # For a timestamp, we can check if the coordinator has a 'last_successful_update_timestamp'
            # or similar if we added it, or use a general last_updated if available.
            # Standard DataUpdateCoordinator has `last_updated` but it's not a public attribute.
            # Let's try to access `coordinator.last_update_success` and `coordinator.data`.
            # If `last_updated_time` was intended, it's typically part of the entity, not coordinator directly.
            # However, the base coordinator *does* have `last_update_success` and `data`.
            # For a timestamp of the last update attempt (not necessarily success),
            # there isn't a direct public attribute.
            # Let's use what's reliably available.
            # The error log mentioned `last_update_success_time`.
            # The `DataUpdateCoordinator` itself doesn't expose this directly.
            # However, entities often have `self.coordinator.last_update_success`
            # and can get `self.coordinator.data`.
            # For diagnostics, let's focus on `last_update_success` and the `data` payload.
            # If a specific timestamp of success is needed, it should be stored in the custom coordinator.
            # The base class has `last_updated` (protected) and `event_time` (protected).
            # Let's assume for now we want to show if the last poll was successful and the data.
            # The error was `AttributeError: 'PoolSyncDataUpdateCoordinator' object has no attribute 'last_update_success_time'`
            # The base `DataUpdateCoordinator` *does* have `last_update_success`.
            # And if we want a timestamp, `async_track_point_in_time_listener` in `async_refresh` sets `self.last_update_success_time`
            # No, that's not standard. `_schedule_refresh` is internal.
            # Let's use `last_update_success` and the `data` itself.
            # The actual error was in the previous version of this file.
            # The `DataUpdateCoordinator` has `last_update_success` (bool) and `data`.
            # If we want a timestamp of the last *successful* update, we might need to store it ourselves.
            # However, `DataUpdateCoordinator` does have a `last_updated` protected attribute.
            # And `async_refresh` sets `self.last_update_success_time` in some older HA versions or custom ones.
            # Let's check the current HA source for DataUpdateCoordinator.
            # It has `self.last_update_success: bool` and `self.data: DataT | None`.
            # It does not have `last_update_success_time` or `last_updated_time` as public attributes.
            # The `_async_refresh` method does: `self._last_update_success = True`
            # `self.async_update_listeners()` is called.
            # The error message was specific: `AttributeError: 'PoolSyncDataUpdateCoordinator' object has no attribute 'last_update_success_time'. Did you mean: 'last_update_success'?`
            # This implies the object *is* a PoolSyncDataUpdateCoordinator.
            # Let's simplify and provide what's guaranteed.

            coordinator_status_info = {
                "last_update_success": getattr(coordinator, 'last_update_success', 'N/A'),
                "coordinator_name": getattr(coordinator, 'name', 'N/A'),
                "mac_address_from_coordinator": getattr(coordinator, 'mac_address', 'N/A'),
                "ip_address_from_coordinator": 'N/A',
                "update_interval_seconds": None,
            }
            if hasattr(coordinator, 'api_client') and hasattr(coordinator.api_client, '_ip_address'):
                coordinator_status_info["ip_address_from_coordinator"] = coordinator.api_client._ip_address
            if hasattr(coordinator, 'update_interval') and coordinator.update_interval:
                coordinator_status_info["update_interval_seconds"] = coordinator.update_interval.total_seconds()

            # To get a timestamp of the last update attempt, we might need to access protected members
            # or rely on entities. For diagnostics, let's just show success status and data.
            # If `last_update_success` is True, then `coordinator.data` is from that successful update.
            # The error was specific, so let's assume it was a typo in my previous `diagnostics.py`.
            # The base DataUpdateCoordinator does NOT have `last_update_success_time`.
            # It has `last_update_success` (bool) and `data`.
            # Let's remove the problematic timestamp for now to ensure diagnostics run.

            diagnostics_data["coordinator_status"] = coordinator_status_info
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
                current_error = diagnostics_data.get("error_in_diagnostics", "") or ""
                diagnostics_data["error_in_diagnostics"] = current_error + f"DeviceReg Error: {traceback.format_exc()}; "

        else:
            _LOGGER.warning("Diagnostics: Coordinator not found in hass.data for entry ID %s.", entry.entry_id)

    except Exception as e_diag:
        _LOGGER.exception("Unexpected error while gathering diagnostics for entry ID %s: %s", entry.entry_id, e_diag)
        current_error = diagnostics_data.get("error_in_diagnostics", "") or ""
        diagnostics_data["error_in_diagnostics"] = current_error + f"Overall Diagnostics Error: {traceback.format_exc()}"

    _LOGGER.debug("Finished gathering diagnostics for entry ID %s. Error in diagnostics: %s", entry.entry_id, diagnostics_data["error_in_diagnostics"])
    return diagnostics_data

