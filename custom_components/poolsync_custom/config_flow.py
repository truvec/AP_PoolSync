"""Config flow for PoolSync Custom integration."""
import asyncio
import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_IP_ADDRESS, CONF_PASSWORD
from homeassistant.core import callback # For @callback decorator
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# Use the provided API client and constants
from .api import (
    PoolSyncApiClient,
    PoolSyncApiAuthError,
    PoolSyncApiCommunicationError,
    PoolSyncApiError,
)
from .const import (
    API_RESPONSE_MAC_ADDRESS,
    API_RESPONSE_PASSWORD,
    API_RESPONSE_TIME_REMAINING,
    CONF_IP_ADDRESS as POOLSYNC_CONF_IP_ADDRESS, # Alias for clarity if needed
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    OPTION_SCAN_INTERVAL, # For options flow
    PUSHLINK_CHECK_INTERVAL_S,
    PUSHLINK_TIMEOUT_S,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(POOLSYNC_CONF_IP_ADDRESS): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PoolSync Custom."""

    VERSION = 1
    # CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL # Not needed in ConfigFlow

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._ip_address: Optional[str] = None
        self._mac_address: Optional[str] = None
        self._password: Optional[str] = None
        self._api_client: Optional[PoolSyncApiClient] = None
        self._link_task: Optional[asyncio.Task] = None
        self._linking_in_progress: bool = False # Flag to manage link step re-entry

    async def _async_create_client(self, ip_address: str) -> PoolSyncApiClient:
        """Create an API client instance."""
        session = async_get_clientsession(self.hass)
        return PoolSyncApiClient(ip_address, session)

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.FlowResult:
        """Handle the initial step where the user provides the IP address."""
        _LOGGER.debug("ConfigFlow: Starting user step.")
        errors: Dict[str, str] = {}

        if user_input is not None:
            self._ip_address = user_input[POOLSYNC_CONF_IP_ADDRESS].strip()
            # Validate IP format roughly (not a full validation, but catches common mistakes)
            if not self._ip_address or len(self._ip_address.split('.')) != 4:
                errors["base"] = "invalid_ip" # Add this to strings.json if used
                _LOGGER.warning("Invalid IP address format entered: %s", self._ip_address)
            else:
                self._api_client = await self._async_create_client(self._ip_address)
                try:
                    _LOGGER.info("Attempting to start push-link for IP: %s", self._ip_address)
                    await self._api_client.start_pushlink()
                    _LOGGER.info("Push-link successfully initiated for %s.", self._ip_address)
                    self._linking_in_progress = True
                    return await self.async_step_link()

                except PoolSyncApiCommunicationError:
                    _LOGGER.error("Communication error with PoolSync device at %s during push-link start.", self._ip_address)
                    errors["base"] = "cannot_connect"
                except PoolSyncApiError as e:
                    _LOGGER.error("API error during push-link start for %s: %s (Status: %s, Body: %s)", self._ip_address, e, e.status_code, e.body)
                    errors["base"] = "api_error"
                except Exception as e:
                    _LOGGER.exception("Unexpected exception during push-link start for %s: %s", self._ip_address, e)
                    errors["base"] = "unknown"
        else:
            _LOGGER.debug("ConfigFlow: Showing user form for IP address.")

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_link(
        self, user_input: Optional[Dict[str, Any]] = None # user_input from async_configure
    ) -> config_entries.FlowResult:
        """Handle the linking step: waiting for button press and polling for password."""
        _LOGGER.debug("ConfigFlow: Starting link step. Linking in progress: %s. User input: %s", self._linking_in_progress, user_input)

        if not self._ip_address or not self._api_client:
            _LOGGER.error("ConfigFlow: IP address or API client not set in link step.")
            return self.async_abort(reason="internal_error")

        # Check if polling task passed an error
        if user_input and "error" in user_input and user_input["error"]:
            _LOGGER.error("ConfigFlow: Link step received error from polling task: %s", user_input["error"])
            self._linking_in_progress = False # Stop linking on error
            if self._link_task and not self._link_task.done():
                self._link_task.cancel()
            return self.async_show_form(
                step_id="link",
                description_placeholders={"ip_address": self._ip_address, "time_remaining": 0},
                errors={"base": user_input["error"]}
            )

        # If password already obtained (e.g., from a completed task), create entry
        if self._password and self._mac_address:
            _LOGGER.info("ConfigFlow: Password and MAC obtained. Creating entry for MAC %s.", self._mac_address)
            await self.async_set_unique_id(self._mac_address) # Use MAC as unique ID
            self._abort_if_unique_id_configured()
            self._linking_in_progress = False # Ensure flag is cleared
            return self.async_create_entry(
                title=f"{DEFAULT_NAME} ({self._mac_address[-6:]})", # e.g. PoolSync (55D598)
                data={
                    CONF_IP_ADDRESS: self._ip_address,
                    CONF_PASSWORD: self._password,
                    API_RESPONSE_MAC_ADDRESS: self._mac_address,
                },
            )

        # Start polling task only if linking is marked as in progress and task isn't running/done
        if self._linking_in_progress and (not self._link_task or self._link_task.done()):
            _LOGGER.debug("ConfigFlow: Creating new link polling task for %s.", self._ip_address)
            self._link_task = self.hass.async_create_task(
                self._async_poll_for_password()
            )
        elif not self._linking_in_progress and self._link_task and not self._link_task.done():
             _LOGGER.debug("ConfigFlow: Linking not in progress, but task exists. Cancelling task for %s.", self._ip_address)
             self._link_task.cancel() # Ensure task is cancelled if linking is no longer active

        # Determine time_remaining for placeholder
        time_remaining_for_ui = PUSHLINK_TIMEOUT_S
        if user_input and "time_remaining" in user_input:
            time_remaining_for_ui = user_input["time_remaining"]

        return self.async_show_form(
            step_id="link",
            description_placeholders={
                "ip_address": self._ip_address,
                "time_remaining": time_remaining_for_ui
            },
            errors={}, # Errors are handled above if passed from polling task
        )

    async def _async_poll_for_password(self) -> None:
        """Poll the device for pushlink status until password is received or timeout."""
        _LOGGER.debug("ConfigFlow: Starting password polling loop for %s.", self._ip_address)
        if not self._api_client or not self._ip_address:
            _LOGGER.error("ConfigFlow: API client or IP not set for polling task for %s.", self._ip_address)
            self.hass.config_entries.flow.async_configure(
                flow_id=self.flow_id, user_input={"error": "internal_error_polling_setup"}
            )
            return

        time_elapsed = 0
        error_to_show: Optional[str] = None

        while time_elapsed < PUSHLINK_TIMEOUT_S:
            if not self._linking_in_progress:
                _LOGGER.debug("ConfigFlow: Linking no longer in progress (IP: %s), stopping poll task.", self._ip_address)
                return # Exit if linking was cancelled or completed by another path

            try:
                _LOGGER.debug("Polling pushlink status for %s. Elapsed: %ds", self._ip_address, time_elapsed)
                status_response = await self._api_client.get_pushlink_status()

                if API_RESPONSE_PASSWORD in status_response and status_response.get(API_RESPONSE_PASSWORD):
                    self._password = status_response[API_RESPONSE_PASSWORD]
                    self._mac_address = status_response.get(API_RESPONSE_MAC_ADDRESS)
                    if not self._mac_address:
                        _LOGGER.warning("Password received for %s but MAC address is missing. Using IP as fallback unique ID.", self._ip_address)
                        self._mac_address = f"ip_{self._ip_address.replace('.', '_')}"

                    _LOGGER.info("Password successfully obtained for MAC: %s (IP: %s)", self._mac_address, self._ip_address)
                    self._linking_in_progress = False # Mark linking as complete
                    self.hass.config_entries.flow.async_configure(flow_id=self.flow_id) # Re-trigger link step
                    return

                time_remaining = status_response.get(API_RESPONSE_TIME_REMAINING)
                if time_remaining is None: # If key is missing, assume timeout or error
                    _LOGGER.warning("Pushlink status for %s missing 'timeRemaining'. Response: %s", self._ip_address, status_response)
                    time_remaining = PUSHLINK_TIMEOUT_S - time_elapsed # Estimate
                else:
                    time_remaining = int(time_remaining) # Ensure it's an int

                _LOGGER.debug("Pushlink time remaining for %s: %s", self._ip_address, time_remaining)
                self.hass.config_entries.flow.async_configure(
                    flow_id=self.flow_id,
                    user_input={"time_remaining": time_remaining} # Update UI
                )

                if time_remaining <= 0 and not self._password:
                    _LOGGER.warning("Pushlink timed out (timeRemaining <= 0) for %s without password.", self._ip_address)
                    error_to_show = "link_timeout"
                    break

            except PoolSyncApiCommunicationError:
                _LOGGER.warning("Communication error while polling pushlink status for %s. Retrying.", self._ip_address)
                # Continue polling, may be temporary. If persistent, will eventually timeout.
            except PoolSyncApiError as e:
                _LOGGER.error("API error while polling pushlink status for %s: %s (Status: %s, Body: %s). Aborting link.", self._ip_address, e, e.status_code, e.body)
                error_to_show = "link_failed" # More specific than generic api_error
                break
            except Exception as e:
                _LOGGER.exception("Unexpected error while polling pushlink status for %s: %s", self._ip_address, e)
                error_to_show = "unknown"
                break

            if error_to_show: break # Exit while loop if error encountered

            await asyncio.sleep(PUSHLINK_CHECK_INTERVAL_S)
            time_elapsed += PUSHLINK_CHECK_INTERVAL_S

        self._linking_in_progress = False # Ensure flag is cleared after loop
        if not self._password and not error_to_show: # If loop finished by time_elapsed without password
            _LOGGER.warning("Pushlink process timed out after %d seconds for %s.", PUSHLINK_TIMEOUT_S, self._ip_address)
            error_to_show = "link_timeout"

        # Pass error back to the link step UI, or an empty dict if successful
        self.hass.config_entries.flow.async_configure(
            flow_id=self.flow_id,
            user_input={"error": error_to_show} if error_to_show else {}
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return PoolSyncOptionsFlowHandler(config_entry)

    def __del__(self):
        """Clean up when flow is destroyed (e.g., user navigates away)."""
        _LOGGER.debug("ConfigFlow for %s: __del__ called. Cancelling link task if active.", self._ip_address or "Unknown IP")
        self._linking_in_progress = False # Ensure polling stops
        if self._link_task and not self._link_task.done():
            self._link_task.cancel()
            _LOGGER.debug("ConfigFlow for %s: Link task cancelled in __del__.", self._ip_address or "Unknown IP")


class PoolSyncOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow for PoolSync Custom."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        # Make a mutable copy of the options
        self.options = dict(config_entry.options)

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.FlowResult:
        """Manage the options."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            # Validate scan_interval
            new_scan_interval = user_input.get(OPTION_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            if not isinstance(new_scan_interval, int) or new_scan_interval < 10: # Min 10s
                errors["base"] = "invalid_scan_interval"
                _LOGGER.warning("Invalid scan interval entered: %s", new_scan_interval)
            else:
                self.options[OPTION_SCAN_INTERVAL] = new_scan_interval
                _LOGGER.info("OptionsFlow: Creating entry with new options: %s", self.options)
                # title="" means do not change the title of the config entry
                return self.async_create_entry(title="", data=self.options)

        # Get current scan_interval or default for form display
        current_scan_interval = self.options.get(OPTION_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        _LOGGER.debug("OptionsFlow: Showing form with current interval: %s", current_scan_interval)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        OPTION_SCAN_INTERVAL,
                        default=current_scan_interval,
                    ): vol.All(vol.Coerce(int), vol.Range(min=10)), # Min interval 10s
                }
            ),
            errors=errors,
            description_placeholders={"current_interval": str(current_scan_interval)}
        )

