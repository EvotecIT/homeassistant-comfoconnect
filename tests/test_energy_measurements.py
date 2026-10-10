"""Library-decoded power and energy retain their values and native units in HA."""

import asyncio
from types import SimpleNamespace

import pytest
from aiocomfoconnect.sensors import SENSOR_AVOIDED_COOLING, SENSOR_AVOIDED_HEATING, SENSOR_POWER_USAGE_TOTAL_YEAR
from custom_components.comfoconnect.sensor import SENSOR_TYPES, ComfoConnectSensor
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


@pytest.mark.parametrize(
    "sensor_id,value,unit", [(SENSOR_AVOIDED_HEATING, 77, "W"), (SENSOR_AVOIDED_COOLING, 84, "W"), (SENSOR_POWER_USAGE_TOTAL_YEAR, 125, "kWh")]
)
def test_energy_measurements_preserve_library_units(tmp_path, sensor_id, value, unit):
    """In particular, already decoded watts must not be divided by 100 again."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True)
        description = next(item for item in SENSOR_TYPES if item.key == sensor_id)
        entity = ComfoConnectSensor(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = f"sensor.energy_{sensor_id}"
        entity._handle_update(value)
        state = hass.states.get(entity.entity_id)
        assert state.state == str(value)
        assert state.attributes["unit_of_measurement"] == unit
        assert not entity.entity_registry_enabled_default

    asyncio.run(scenario())
