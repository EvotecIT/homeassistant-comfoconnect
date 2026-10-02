"""Regressions for writable numbers and diagnostic power sensors."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiocomfoconnect.exceptions import AioComfoConnectTimeout, ComfoConnectRmiError
from aiocomfoconnect.sensors import SENSOR_AVOIDED_COOLING, SENSOR_AVOIDED_HEATING
from custom_components.comfoconnect import SIGNAL_COMFOCONNECT_AVAILABILITY
from custom_components.comfoconnect.number import NUMBER_TYPES, ComfoConnectNumber
from custom_components.comfoconnect.select import SELECT_TYPES, ComfoConnectSelect
from custom_components.comfoconnect.sensor import SENSOR_TYPES, ComfoConnectSensor
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send


def metadata(*values):
    """Return the bridge's signed 16-bit metadata response."""
    return SimpleNamespace(message=b"".join(value.to_bytes(2, "little", signed=True) for value in values))


def number_entity(hass, key="airflow_away"):
    """Create an entity with mocked device I/O and a real HA state machine."""
    bridge = SimpleNamespace(
        uuid="test-bridge",
        is_available=True,
        get_single_property=AsyncMock(return_value=85),
        cmd_rmi_request=AsyncMock(side_effect=[metadata(50, 140), metadata(5)]),
        set_flow_for_speed=AsyncMock(),
        set_property_typed=AsyncMock(),
    )
    description = next(description for description in NUMBER_TYPES if description.key == key)
    entity = ComfoConnectNumber(bridge, SimpleNamespace(), description)
    entity.hass = hass
    entity.entity_id = f"number.{key}"
    return bridge, entity


@pytest.mark.parametrize("read_error", [ComfoConnectRmiError("Busy"), AioComfoConnectTimeout("Timed out")])
def test_acknowledged_write_is_published_even_when_followup_read_fails(tmp_path, read_error):
    """A transient read cannot hide a value already acknowledged by the unit."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        bridge, entity = number_entity(hass)
        await entity.async_update()
        entity.async_write_ha_state()
        assert hass.states.get(entity.entity_id).state == "85.0"

        await entity.async_set_native_value(90)
        assert hass.states.get(entity.entity_id).state == "90.0"

        bridge.get_single_property.side_effect = read_error
        await entity.async_update()
        entity.async_write_ha_state()
        assert hass.states.get(entity.entity_id).state == "90.0"
        assert entity.available

        bridge.get_single_property.side_effect = None
        bridge.get_single_property.return_value = 95
        await entity.async_update()
        entity.async_write_ha_state()
        assert hass.states.get(entity.entity_id).state == "95.0"
        assert bridge.cmd_rmi_request.await_count == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("key,mode", [("boost_timeout", "boost"), ("away_timeout", "away")])
def test_timer_select_reports_active_without_starting_a_timer_for_the_status_option(tmp_path, key, mode):
    """Duration starts a timer, while Active reflects the device's existing state."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setter = AsyncMock()
        getter = AsyncMock(return_value=False)
        bridge = SimpleNamespace(uuid="test-bridge", is_available=True)
        setattr(bridge, f"set_{mode}", setter)
        setattr(bridge, f"get_{mode}", getter)
        description = next(description for description in SELECT_TYPES if description.key == key)
        entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = f"select.{key}"

        await entity.async_select_option("Active")
        setter.assert_not_awaited()
        assert hass.states.get(entity.entity_id).state == "Off"

        await entity.async_select_option("10 Minutes")
        setter.assert_awaited_once_with(True, 600)
        assert hass.states.get(entity.entity_id).state == "Active"

        await entity.async_select_option("Off")
        assert setter.await_args.args == (False,)
        assert hass.states.get(entity.entity_id).state == "Off"

    asyncio.run(scenario())


def test_metadata_failure_is_retried_and_constraints_reload_after_reconnect(tmp_path):
    """Numbers stay unavailable without constraints, then cache them until disconnect."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        bridge, entity = number_entity(hass)
        await entity.async_added_to_hass()
        bridge.cmd_rmi_request.side_effect = [metadata(50, 140), ComfoConnectRmiError("Busy")]
        await entity.async_update()
        assert not entity.available
        with pytest.raises(HomeAssistantError):
            await entity.async_set_native_value(90)
        bridge.set_flow_for_speed.assert_not_awaited()

        bridge.cmd_rmi_request.side_effect = [metadata(50, 140), metadata(5)]
        await entity.async_update()
        assert entity.available
        assert (entity.native_min_value, entity.native_max_value, entity.native_step) == (50, 140, 5)
        await entity.async_update()
        assert bridge.cmd_rmi_request.await_count == 4

        bridge.is_available = False
        async_dispatcher_send(hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format(bridge.uuid), False)
        await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id).state == "unavailable"

        bridge.is_available = True
        async_dispatcher_send(hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format(bridge.uuid), True)
        await hass.async_block_till_done()
        assert not entity.available

        bridge.cmd_rmi_request.side_effect = [metadata(50, 150), metadata(10)]
        await entity.async_update()
        assert entity.available
        assert (entity.native_min_value, entity.native_max_value, entity.native_step) == (50, 150, 10)
        await entity.async_will_remove_from_hass()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "range_response,step_response", [(metadata(50), metadata(5)), (metadata(140, 50), metadata(5)), (metadata(50, 140), metadata(0))]
)
def test_invalid_device_constraints_do_not_enable_writes(tmp_path, range_response, step_response):
    """Incomplete or invalid device metadata cannot expose HA's default write limits."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        bridge, entity = number_entity(hass)
        bridge.cmd_rmi_request.side_effect = [range_response, step_response]
        await entity.async_update()
        assert not entity.available
        with pytest.raises(HomeAssistantError):
            await entity.async_set_native_value(90)
        bridge.set_flow_for_speed.assert_not_awaited()

    asyncio.run(scenario())


def test_failed_write_keeps_previous_state_and_temperature_writes_use_device_scale(tmp_path):
    """Only acknowledged writes change HA state, with the same scale as the device."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        bridge, entity = number_entity(hass, "rmot_heating")
        bridge.get_single_property.return_value = 110
        bridge.cmd_rmi_request.side_effect = [metadata(0, 150), metadata(10)]
        await entity.async_update()
        entity.async_write_ha_state()
        bridge.set_property_typed.side_effect = ComfoConnectRmiError("Busy")
        with pytest.raises(ComfoConnectRmiError):
            await entity.async_set_native_value(12)
        assert hass.states.get(entity.entity_id).state == "11.0"

        bridge.set_property_typed.side_effect = None
        await entity.async_set_native_value(12)
        assert hass.states.get(entity.entity_id).state == "12.0"
        assert bridge.set_property_typed.await_args.args[3] == 120
        assert (entity.native_min_value, entity.native_max_value, entity.native_step) == (0, 15, 1)

    asyncio.run(scenario())


@pytest.mark.parametrize("sensor_id", [SENSOR_AVOIDED_HEATING, SENSOR_AVOIDED_COOLING])
def test_avoided_power_preserves_watts_from_the_library(tmp_path, sensor_id):
    """Already decoded watts reach HA without a second scale conversion."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        bridge = SimpleNamespace(uuid="test-bridge", is_available=True)
        description = next(description for description in SENSOR_TYPES if description.key == sensor_id)
        entity = ComfoConnectSensor(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = "sensor.avoided_power"
        entity._handle_update(77)
        state = hass.states.get(entity.entity_id)
        assert state.state == "77"
        assert state.attributes["unit_of_measurement"] == "W"

    asyncio.run(scenario())
