"""Climate platform for PoolSync integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.unit_system import METRIC_SYSTEM

from .const import DOMAIN, HEATPUMP_ID
from .coordinator import PoolSyncDataUpdateCoordinator
from .sensor import _get_value_from_path

_LOGGER = logging.getLogger(__name__)

# Heat pump modes from your integration
HEATPUMP_MODE_OFF = 0
HEATPUMP_MODE_HEAT = 1
HEATPUMP_MODE_COOL = 2

# Mapping PoolSync modes to HA HVAC modes
POOLSYNC_TO_HVAC_MODE = {
    HEATPUMP_MODE_OFF: HVACMode.OFF,
    HEATPUMP_MODE_HEAT: HVACMode.HEAT,
    HEATPUMP_MODE_COOL: HVACMode.COOL,
}

HVAC_MODE_TO_POOLSYNC = {v: k for k, v in POOLSYNC_TO_HVAC_MODE.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PoolSync climate entities from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    
    # Check if heat pump data is available - use same logic as your other platforms
    if not coordinator.data or not isinstance(coordinator.data.get("devices"), dict):
        _LOGGER.warning("Coordinator %s has no data or missing 'devices'. Cannot set up climate.", coordinator.name)
        return

    # Get the actual heat pump ID using same logic as your other platforms
    heatpump_id = HEATPUMP_ID
    if coordinator.data and isinstance(coordinator.data.get("deviceType"), dict):
        deviceTypes = coordinator.data.get("deviceType")
        temp = [key for key, value in deviceTypes.items() if value == "heatPump"]
        heatpump_id = temp[0] if temp else "-1"
    
    # Only create climate entity if heat pump is available
    if heatpump_id != "-1":
        entities.append(PoolSyncClimate(coordinator, heatpump_id))
        _LOGGER.info("Added PoolSync climate entity for heat pump ID %s", heatpump_id)
    
    if entities:
        async_add_entities(entities)


class PoolSyncClimate(CoordinatorEntity[PoolSyncDataUpdateCoordinator], ClimateEntity):
    """Representation of a PoolSync heat pump as a climate device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PoolSyncDataUpdateCoordinator,
        heatpump_id: str,
    ) -> None:
        """Initialize the climate device."""
        super().__init__(coordinator)
        self._heatpump_id = heatpump_id
        self._attr_name = "Heat Pump"
        self._attr_unique_id = f"{coordinator.mac_address}_climate"
        self._attr_device_info = coordinator.device_info
        
        # Set supported features
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE |
            ClimateEntityFeature.TURN_ON |
            ClimateEntityFeature.TURN_OFF
        )
        
        # Set HVAC modes
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.HEAT,
            HVACMode.COOL,
        ]
        
        # Temperature settings - match your number entity ranges
        is_metric = coordinator.hass.config.units is METRIC_SYSTEM
        if is_metric:
            self._attr_temperature_unit = UnitOfTemperature.CELSIUS
            self._attr_min_temp = 5
            self._attr_max_temp = 40
            self._attr_target_temperature_step = 0.5
        else:
            self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
            self._attr_min_temp = 40
            self._attr_max_temp = 104
            self._attr_target_temperature_step = 1

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        # Use same path as hp_water_temp sensor
        water_temp_path = ["devices", self._heatpump_id, "status", "waterTemp"]
        value = _get_value_from_path(self.coordinator.data, water_temp_path)
        
        if value is None:
            return None
            
        try:
            return float(value)
        except (ValueError, TypeError):
            _LOGGER.error("Climate: Could not convert water temperature '%s' to float", value)
            return None

    @property
    def target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        # Use same path as hp_setpoint_temp sensor
        setpoint_path = ["devices", self._heatpump_id, "config", "setpoint"]
        value = _get_value_from_path(self.coordinator.data, setpoint_path)
        
        if value is None:
            return None
            
        try:
            return float(value)
        except (ValueError, TypeError):
            _LOGGER.error("Climate: Could not convert setpoint temperature '%s' to float", value)
            return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation mode."""
        # Use same path as hp_mode sensor
        mode_path = ["devices", self._heatpump_id, "config", "mode"]
        value = _get_value_from_path(self.coordinator.data, mode_path)
        
        if value is None:
            return HVACMode.OFF
            
        try:
            mode_value = int(value)
            return POOLSYNC_TO_HVAC_MODE.get(mode_value, HVACMode.OFF)
        except (ValueError, TypeError):
            _LOGGER.error("Climate: Could not convert mode '%s' to int", value)
            return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current running hvac operation."""
        current_mode = self.hvac_mode
        if current_mode == HVACMode.OFF:
            return HVACAction.OFF
            
        # Check if the heat pump is actively running using mode-specific logic
        mode_path = ["devices", self._heatpump_id, "config", "mode"]
        state_flags_path = ["devices", self._heatpump_id, "status", "stateFlags"]
        ctrl_flags_path = ["devices", self._heatpump_id, "status", "ctrlFlags"]
        
        mode_value = _get_value_from_path(self.coordinator.data, mode_path)
        state_flags_value = _get_value_from_path(self.coordinator.data, state_flags_path)
        ctrl_flags_value = _get_value_from_path(self.coordinator.data, ctrl_flags_path)
        
        is_running = False
        if mode_value is not None and state_flags_value is not None and ctrl_flags_value is not None:
            try:
                mode = int(mode_value)
                state_flags = int(state_flags_value)
                ctrl_flags = int(ctrl_flags_value)
                
                if mode == 1:  # Heating mode
                    # Heat pump is running when stateFlags > 257 AND ctrlFlags >= 397
                    is_running = (state_flags > 257 and ctrl_flags >= 397)
                elif mode == 2:  # Cooling mode  
                    # Heat pump is running when in cooling state (272+) and operation flags active (445+)
                    is_running = (state_flags >= 272 and ctrl_flags >= 445)
            except (ValueError, TypeError):
                pass
        
        if is_running:
            if current_mode == HVACMode.HEAT:
                return HVACAction.HEATING
            elif current_mode == HVACMode.COOL:
                return HVACAction.COOLING
        else:
            return HVACAction.IDLE
            
        return HVACAction.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode not in self._attr_hvac_modes:
            _LOGGER.error("Unsupported HVAC mode: %s", hvac_mode)
            return
            
        poolsync_mode = HVAC_MODE_TO_POOLSYNC.get(hvac_mode)
        if poolsync_mode is None:
            _LOGGER.error("Cannot map HVAC mode %s to PoolSync mode", hvac_mode)
            return
            
        try:
            # Use the coordinator methods we added
            await self.coordinator.async_set_heatpump_mode(self._heatpump_id, poolsync_mode)
            await self.coordinator.async_request_refresh()
            _LOGGER.info("Climate: Set HVAC mode to %s (mode %d)", hvac_mode, poolsync_mode)
        except Exception as err:
            _LOGGER.error("Error setting HVAC mode to %s: %s", hvac_mode, err)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        target_temp = kwargs.get(ATTR_TEMPERATURE)
        if target_temp is None:
            return
            
        # Validate temperature range
        if target_temp < self._attr_min_temp or target_temp > self._attr_max_temp:
            _LOGGER.error(
                "Temperature %s is out of range (%s-%s)",
                target_temp,
                self._attr_min_temp,
                self._attr_max_temp,
            )
            return
            
        try:
            # Use the coordinator methods we added
            await self.coordinator.async_set_heatpump_temperature(self._heatpump_id, target_temp)
            await self.coordinator.async_request_refresh()
            _LOGGER.info("Climate: Set target temperature to %s", target_temp)
        except Exception as err:
            _LOGGER.error("Error setting temperature to %s: %s", target_temp, err)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return None
            
        attributes = {}
        
        # Add air temperature from heat pump
        air_temp_path = ["devices", self._heatpump_id, "status", "airTemp"]
        air_temp = _get_value_from_path(self.coordinator.data, air_temp_path)
        if air_temp is not None:
            try:
                attributes["air_temperature"] = float(air_temp)
            except (ValueError, TypeError):
                pass
        
        # Add heat pump flow status
        flow_path = ["devices", self._heatpump_id, "status", "ctrlFlags"]
        flow_value = _get_value_from_path(self.coordinator.data, flow_path)
        if flow_value is not None:
            try:
                attributes["flow_active"] = bool(int(flow_value) >= 1)
            except (ValueError, TypeError):
                pass
        
        # Add heat pump device ID for debugging
        attributes["heat_pump_device_id"] = self._heatpump_id
                
        return attributes if attributes else None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        coordinator_available = super().available
        # Check if the heat pump mode data exists (key data point)
        mode_path = ["devices", self._heatpump_id, "config", "mode"]
        mode_exists = _get_value_from_path(self.coordinator.data, mode_path) is not None
        return coordinator_available and mode_exists
