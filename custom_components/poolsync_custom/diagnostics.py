"""Diagnostics support for the PoolSync Custom integration."""
from typing import Any, Dict, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD # Used by HA core to know what to redact
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr # For getting device info

from .const import DOMAIN, API_RESPONSE_MAC_ADDRESS # For identifying device
from .coordinator import PoolSyncDataUpdateCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""
    # Home Assistant's core diagnostics handling automatically redacts fields named 'password',
    # 'username', 'token', 'secret', 'key', 'api_key', 'access_token', etc., from entry.data
    # and entry.options when they are included directly.
    # So, we don't need to manually redact here if we pass entry.data directly.
    # However, it's good practice to be explicit or to structure if we add more.

    diagnostics_data: Dict[str, Any] = {
        "config_entry_id": entry.entry_id,
        "config_entry_title": entry.title,
        "config_entry_domain": entry.domain,
        # entry.data and entry.options are automatically redacted by the core
        # for common sensitive keys like 'password'.
        "config_entry_data": dict(entry.data),
        "options": dict(entry.options),
        "disabled_by": entry.disabled_by,
        "source": str(entry.source), # Convert enum to string
    }

    # Attempt to get the coordinator if the integration is loaded
    coordinator: Optional[PoolSyncDataUpdateCoordinator] = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    if coordinator:
        diagnostics_data["coordinator_status"] = {
            "last_update_success": coordinator.last_update_success,
            "last_update_success_time": coordinator.last_update_success_time.isoformat() if coordinator.last_update_success_time else None,
            "update_interval": coordinator.update_interval.total_seconds() if coordinator.update_interval else None,
            "coordinator_name": coordinator.name,
            "mac_address_from_coordinator": coordinator.mac_address,
            "ip_address_from_coordinator": coordinator._ip_address, # Accessing protected member
        }
        # Include the actual data from the coordinator (this is the raw device data)
        diagnostics_data["coordinator_data_payload"] = coordinator.data
        
        # Get device info from device registry
        device_registry = dr.async_get(hass)
        # The identifier for the device is (DOMAIN, coordinator.mac_address)
        device = device_registry.async_get_device(identifiers={(DOMAIN, coordinator.mac_address)})
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
                "entry_type": device.entry_type.value if device.entry_type else None,
                "configuration_url": device.configuration_url,
                "is_new": device.is_new,
                "disabled_by": device.disabled_by.value if device.disabled_by else None,
            }
        else:
            diagnostics_data["device_registry_info"] = f"Device with MAC {coordinator.mac_address} not found in registry."
            
    else:
        diagnostics_data["coordinator_status"] = "Coordinator not found in hass.data. Integration might not be fully loaded or has failed."
        diagnostics_data["coordinator_data_payload"] = "Coordinator not available to fetch data."
        diagnostics_data["device_registry_info"] = "Coordinator not available to identify device in registry."


    return diagnostics_data

