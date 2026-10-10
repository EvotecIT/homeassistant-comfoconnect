"""Device diagnostics present the existing library values without extra writes."""

import asyncio
from types import SimpleNamespace

import pytest
from aiocomfoconnect.sensors import SENSOR_CHANGING_FILTERS, SENSOR_DEVICE_STATE, SENSOR_FAN_SPEED_MODE_MODULATED, SENSOR_RF_PAIRING_MODE
from custom_components.comfoconnect.sensor import SENSOR_TYPES, ComfoConnectSensor
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


@pytest.mark.parametrize(
    "sensor_id,raw,state",
    [
        (SENSOR_DEVICE_STATE, 1, "normal"),
        (SENSOR_CHANGING_FILTERS, 2, "changing_filter"),
        (SENSOR_RF_PAIRING_MODE, 3, "failed"),
        (SENSOR_FAN_SPEED_MODE_MODULATED, 150, "50.0"),
    ],
)
def test_diagnostic_values_reach_ha(tmp_path, sensor_id, raw, state):
    """The public state is readable and the sensor remains disabled by default."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True)
        description = next(item for item in SENSOR_TYPES if item.key == sensor_id)
        entity = ComfoConnectSensor(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = f"sensor.diagnostic_{sensor_id}"
        entity._handle_update(raw)
        assert hass.states.get(entity.entity_id).state == state
        assert not entity.entity_registry_enabled_default

    asyncio.run(scenario())
