"""Number platform for the PoolSync Custom integration."""
import logging
from typing import Any, Callable, Dict, List, Optional, Union

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.exceptions import HomeAssistantError # For service call errors

from .const import (
    DOMAIN,
    DEFAULT_CHLOR_OUTPUT_MIN,
    DEFAULT_CHLOR_OUTPUT_MAX,
    DEFAULT_CHLOR_OUTPUT_STEP,
    NUMBER_KEY_CHLOR_OUTPUT,
)
from .coordinator import PoolSyncDataUpdateCoordinator
from .sensor import _get_value_from_path # Reuse helper from sensor.py

_LOGGER = logging.getLogger(__name__)

NUMBER_DESCRIPTIONS: tuple[NumberEntityDescription, List[str], Optional[Callable[[Any], Any]]] = (
    (NumberEntityDescription(
        key=NUMBER_KEY_CHLOR_OUTPUT, # "chlor_output_control"
        name="Chlorinator Output", # This will be the entity name
        icon="mdi:knob", # Using a knob icon for control
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=DEFAULT_CHLOR_OUTPUT_MIN, # e.g., 0
        native_max_value=DEFAULT_CHLOR_OUTPUT_MAX, # e.g., 100
        native_step=DEFAULT_CHLOR_OUTPUT_STEP,     # e.g., 1 or 5
        mode=NumberMode.SLIDER, # Or NumberMode.BOX
    ), ["devices", "0", "config", "chlorOutput"], None), # Path to get current value
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PoolSync number entities based on a config entry."""
    coordinator: PoolSyncDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug("Setting up number entities for %s", coordinator.name)

    number_entities: list[PoolSyncChlorOutputNumberEntity] = []

    if not coordinator.data or not isinstance(coordinator.data.get("devices"), dict) or \
       not isinstance(coordinator.data["devices"].get("0"), dict):
        _LOGGER.warning(
            "Coordinator %s: 'devices.0' key missing or not a dict in initial data. "
            "Chlorinator Output number entity cannot be set up.",
            coordinator.name
        )
        return # Cannot set up the number entity without its data path

    for description, data_path, value_fn in NUMBER_DESCRIPTIONS:
        # Ensure the specific path for chlorOutput exists
        current_value = _get_value_from_path(coordinator.data, data_path)
        if current_value is None:
            _LOGGER.warning(
                "Coordinator %s: Value for number entity %s at path %s is None. "
                "Entity may be unavailable or show an unexpected state.",
                coordinator.name, description.key, data_path
            )
        # Always add the entity; its availability will handle missing data.
        number_entities.append(
            PoolSyncChlorOutputNumberEntity(coordinator, description, data_path, value_fn)
        )

    if number_entities:
        async_add_entities(number_entities)
        _LOGGER.info("Added %d PoolSync number entities for %s", len(number_entities), coordinator.name)


class PoolSyncChlorOutputNumberEntity(CoordinatorEntity[PoolSyncDataUpdateCoordinator], NumberEntity):
    """Representation of a PoolSync Chlorinator Output Number entity."""

    _attr_has_entity_name = True # Use the entity_description.name as the entity's name

    def __init__(
        self,
        coordinator: PoolSyncDataUpdateCoordinator,
        description: NumberEntityDescription,
        data_path: List[str],
        value_fn: Optional[Callable[[Any], Any]] = None, # Though not typically used for number value
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.entity_description = description # This sets name, icon, uom, min/max, step, mode
        self._data_path = data_path
        self._value_fn = value_fn # Not used for native_value here, but kept for pattern consistency

        self._attr_unique_id = f"{coordinator.mac_address}_{description.key}"
        self._attr_device_info = coordinator.device_info

        _LOGGER.debug(
            "Initializing number entity: Name: %s, Unique ID: %s, Data Path: %s",
            self.entity_description.name, self._attr_unique_id, self._data_path
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the current value of the number entity."""
        value = _get_value_from_path(self.coordinator.data, self._data_path)
        if value is None:
            _LOGGER.debug("Number entity %s: native_value is None from path %s", self.entity_description.key, self._data_path)
            return None
        try:
            num_value = float(value)
            _LOGGER.debug("Number entity %s: native_value is %s from path %s", self.entity_description.key, num_value, self._data_path)
            return num_value
        except (ValueError, TypeError):
            _LOGGER.error(
                "Number entity %s: could not convert value '%s' (type: %s) to float from path %s",
                self.entity_description.key, value, type(value).__name__, self._data_path
            )
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        new_value = int(value) # API expects an integer for percentage
        _LOGGER.info(
            "Number entity %s: Attempting to set native_value to %d (float value: %f)",
            self.entity_description.key, new_value, value
        )

        # Get password from coordinator's config entry data (or API client if stored there)
        # Assuming password is on the coordinator instance, passed during __init__
        if not hasattr(self.coordinator, '_password') or not self.coordinator._password:
             _LOGGER.error("Number entity %s: Password not available on coordinator. Cannot set value.", self.entity_description.key)
             raise HomeAssistantError("API password not available to set value.")

        try:
            await self.coordinator.api_client.async_set_chlor_output(
                password=self.coordinator._password, # Access password stored on coordinator
                output_percentage=new_value
            )
            # After setting, request a refresh of the coordinator data to get the latest state
            # This ensures the UI updates promptly with the (potentially) new value from the device.
            await self.coordinator.async_request_refresh()
            _LOGGER.info("Number entity %s: Successfully set value to %d and requested refresh.", self.entity_description.key, new_value)

        except Exception as e:
            _LOGGER.error(
                "Number entity %s: Failed to set new value %d: %s",
                self.entity_description.key, new_value, e
            )
            # Optionally, re-raise a more specific Home Assistant error if desired
            raise HomeAssistantError(f"Failed to set chlorine output to {new_value}%: {e}") from e

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Available if coordinator is available and the data point for current value exists
        coordinator_available = super().available
        value_exists = _get_value_from_path(self.coordinator.data, self._data_path) is not None
        is_available = coordinator_available and value_exists
        # _LOGGER.debug(
        #     "Number entity %s: Availability check: coordinator_available=%s, value_exists=%s, final_available=%s",
        #     self.entity_description.key, coordinator_available, value_exists, is_available
        # )
        return is_available

