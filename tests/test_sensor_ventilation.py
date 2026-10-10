"""Ventilation selects map their options to the existing sensor-control APIs."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from custom_components.comfoconnect.select import SELECT_TYPES, ComfoConnectSelect
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


@pytest.mark.parametrize("mode", ["temperature_passive", "humidity_comfort", "humidity_protection"])
def test_sensor_ventilation_reads_and_writes_its_own_mode(tmp_path, mode):
    """Each exposed select controls the matching library property."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = SimpleNamespace(uuid="test", is_available=True)
        setter = AsyncMock()
        setattr(bridge, f"set_sensor_ventmode_{mode}", setter)
        setattr(bridge, f"get_sensor_ventmode_{mode}", AsyncMock(return_value="auto"))
        description = next(item for item in SELECT_TYPES if item.key == f"sensor_ventmode_{mode}")
        entity = ComfoConnectSelect(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = f"select.{mode}"
        await entity.async_update()
        assert entity.current_option == "auto"
        assert set(entity.options) == {"auto", "on", "off"}
        await entity.async_select_option("off")
        setter.assert_awaited_once_with("off")
        assert hass.states.get(entity.entity_id).state == "off"

    asyncio.run(scenario())
