# Home Assistant Zehnder ComfoAirQ / ComfoCoolQ integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

This is a custom integration for Home Assistant to integrate with the Zehnder ComfoAirQ ventilation system. It's using the [aiocomfoconnect](https://github.com/michaelarnauts/aiocomfoconnect) library.

This EvotecIT fork combines alarm notifications with advanced controls and diagnostics. The changes are also maintained as focused upstream contributions, including the [active-alarm sensor](https://github.com/michaelarnauts/home-assistant-comfoconnect/pull/151), [ventilation controls](https://github.com/michaelarnauts/home-assistant-comfoconnect/pull/152), and [session recovery](https://github.com/michaelarnauts/home-assistant-comfoconnect/pull/179).

This custom integration is an upgrade over the existing `comfoconnect` integration and is meant for testing purposes. The goal is eventually to replace the existing `comfoconnect`
integration in Home Assistant.

## Features

* Control ventilation speed
* Control ventilation mode (auto / manual)
* Control ComfoCool mode (auto / off)
* Control timed boost and away modes
* Configure advanced airflow and temperature targets
* Show yearly energy totals and avoided heating/cooling measurements
* Show an Active alarms diagnostic binary sensor
* Configure passive-temperature and humidity ventilation controls
* Show various sensors
* Show extended diagnostic and energy sensors

This integration supports the following additional features over the existing integration:

* Configurable through the UI
* Support for multiple bridges
* Allows to modify the balance mode, bypass mode, temperature profile and ventilation mode
* Allows advanced airflow and temperature target tuning through disabled-by-default number entities
* Support to clear alarms
* Ignores invalid sensor values at the beginning of a session (Workaround for bridge firmware bug)
* Throttles high frequency sensor updates (airflow & fan duty) to once every 10 seconds

**Note: Not all sensors are enabled by default. You can enable them on the integration page.**

### Fan speed overrides

With aiocomfoconnect 0.2.1, a temporary fan-speed override can remain active after selecting `auto` until the unit's timer expires.

### Timed boost and away modes

Choose a duration in the Boost Mode or Away Mode select to start a timer. Choose `Off`, or use the corresponding Cancel button, to stop it. `Active` reports a running timer; selecting it does not start or extend a timer.

Away Mode also offers 2, 8, and 24 hours, plus 7 and 14 days for longer absences. Use `Off` or Cancel away when you return early.

### Advanced airflow and temperature targets

Number entities are disabled by default and use the unit's own minimum, maximum, and step values. They become available after the integration has read those constraints successfully.

The Warm, Normal, and Cool profile target temperatures configure the unit's fixed presets. They apply when temperature regulation is set to `FIXED` on the unit's display. In `ADAPTIVE` mode the unit calculates its target from the running mean outdoor temperature (RMOT), so changing a stored fixed preset does not set the current target. The Temperature Profile select chooses Warm, Normal, or Cool independently of that regulation mode.

Changing an airflow target overwrites the installer's commissioned airflow setting for that speed. Record the existing values and consult your installer before changing them, since these settings affect the ventilation balance.

## Installation

### HACS

The easiest way to install this integration is through [HACS](https://hacs.xyz/).

1. Add this repository (`https://github.com/EvotecIT/homeassistant-comfoconnect`) as a custom repository in HACS.
   See [here](https://hacs.xyz/docs/faq/custom_repositories) for more information.
2. Install the `Zehnder ComfoAirQ` integration.
3. Restart Home Assistant.

If you have the existing `comfoconnect` integration installed, the configuration should be picked up, but you might need to change your existing sensors ids.
You should also remove the old configuration from the `configuration.yaml` file.

If not, you can add the integration through the UI by going to the integrations page and adding the `Zehnder ComfoAirQ` integration.
