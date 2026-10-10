"""Airflow settings use the device's speed-specific write API and native units."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from custom_components.comfoconnect import ComfoConnectBridge
from custom_components.comfoconnect.number import NUMBER_TYPES, ComfoConnectNumber
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


@pytest.mark.parametrize("speed", ["away", "low", "medium", "high"])
def test_airflow_writes_select_the_correct_speed(tmp_path, speed):
    """Each setting reaches its own commissioned speed target without temperature scaling."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = ComfoConnectBridge(hass, "127.0.0.1", "test")
        bridge.get_single_property = AsyncMock(return_value=85)
        bridge.cmd_rmi_request = AsyncMock(side_effect=[SimpleNamespace(message=b"\x32\x00\xf4\x01"), SimpleNamespace(message=b"\x05\x00")])
        bridge.set_flow_for_speed = AsyncMock()
        description = next(item for item in NUMBER_TYPES if item.key == f"airflow_{speed}")
        entity = ComfoConnectNumber(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = f"number.airflow_{speed}"
        await entity.async_update()
        assert (entity.native_min_value, entity.native_max_value, entity.native_step) == (50, 500, 5)
        assert not entity.entity_registry_enabled_default
        await entity.async_set_native_value(90)
        bridge.set_flow_for_speed.assert_awaited_once_with(speed, 90)
        assert hass.states.get(entity.entity_id).state == "90.0"

    asyncio.run(scenario())
