# PoolSync Custom Integration for Home Assistant

[](https://github.com/hacs/integration)

This is a custom integration for Home Assistant to monitor and control AutoPilot PoolSync pool chlorinators and heat pumps over the local network. It does not rely on any cloud services.

## Features

  * Local push-button linking to obtain an access password from the PoolSync device.
  * Retrieves comprehensive status and configuration data.
  * Creates sensors in Home Assistant for key metrics (e.g., water temperature, salt PPM, flow rate, device status).
  * Creates binary sensors for online status and other states like faults or service mode.
  * **Control Chlorinator Output:** Allows setting the chlorine output percentage via a number entity.
  * **Control Heat Pump:** Provides a full **Climate** entity to control your heat pump's mode (Heat/Cool/Off) and target temperature.

## Prerequisites

1.  Your PoolSync device must be connected to your local Wi-Fi network.
2.  You need to know the local IP address of your PoolSync device.
3.  Home Assistant instance (version 2023.1.0 or newer recommended) with HACS (Home Assistant Community Store) installed.

## Installation via HACS

1.  **Ensure HACS is installed.** If not, follow the [HACS installation guide](https://hacs.xyz/docs/setup/download).
2.  **Add Custom Repository:**
      * Open HACS in your Home Assistant.
      * Go to "Integrations".
      * Click the three dots in the top right corner and select "Custom repositories".
      * In the "Repository" field, paste the URL of this GitHub repository.
      * In the "Category" field, select "Integration".
      * Click "Add".
3.  **Install Integration:**
      * Search for "PoolSync Custom" in HACS.
      * Click "Install".
      * Restart Home Assistant when prompted.

## Configuration

1.  **Go to Settings \> Devices & Services.**
2.  Click the **+ ADD INTEGRATION** button in the bottom right.
3.  Search for "PoolSync Custom" and click on it.
4.  **Enter IP Address:**
      * You will be prompted to enter the local IP address of your PoolSync device. Click "Submit".
5.  **Push-Button Linking:**
      * The integration will attempt to initiate the linking process.
      * You will be prompted to **press the "Auth" button on your PoolSync device**.
      * The configuration flow will show the approximate time remaining to press the button.
      * Once the button is pressed, the integration will retrieve an access password and the device's MAC address.
6.  **Setup Complete:**
      * If successful, the integration will be added, and entities for your PoolSync device will be created.

## Entities

This integration will create several entities, depending on your specific PoolSync model and connected devices.

  * **Sensors (ChlorSync):**

      * Water Temperature
      * Salt Level (PPM)
      * Flow Rate
      * Chlorinator Output Setting
      * Boost Time Remaining
      * Various diagnostic sensors (Wi-Fi RSSI, board temperature, cell currents/voltages - some may be disabled by default).

  * **Sensors (HeatPump):**

      * Water Temperature
      * Air Temperature
      * Mode (Off/Heat/Cool)
      * Setpoint Temperature
      * Compressor RPM

  * **Binary Sensors:**

      * PoolSync Online Status
      * System Fault Status
      * Service Mode Active
      * ChlorSync Module Online Status
      * ChlorSync Fault Status
      * HeatPump Module Online Status
      * HeatPump Flow Active
      * HeatPump Fan Active
      * HeatPump Compressor Active

  * **Climate:**

      * **Heat Pump:** A full climate entity to control the operating mode (`Off`, `Heat`, `Cool`) and set the target temperature. It also displays the current water temperature.

  * **Number Controls:**

      * **Chlorinator Output:** Allows setting the output percentage (0-100%).
      * **HeatPump Temperature Set Point:** Allows setting the target temperature.
      * **HeatPump Mode:** Allows changing the mode (0-off, 1-heat, 2-cool).

## Options

After setting up the integration, you can adjust the polling interval:

1.  Go to **Settings \> Devices & Services**.
2.  Find the PoolSync integration card and click **Configure**.
3.  Adjust the "Update interval (seconds)" and click **Submit**.

## Troubleshooting

  * Ensure your PoolSync device is powered on and connected to the same network as your Home Assistant instance.
  * Double-check the IP address of the PoolSync device.
  * If linking fails, try restarting the PoolSync device and then attempt the configuration again.
  * Check Home Assistant logs (Settings \> System \> Logs) for any error messages related to `poolsync_custom`.
  * Use the Diagnostics feature on the device page in HA to download raw data, which can be helpful for debugging.

## Disclaimer

This integration is not affiliated with or endorsed by AutoPilot Pool Systems. Use at your own risk.
