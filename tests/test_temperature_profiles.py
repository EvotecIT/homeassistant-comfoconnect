"""Fixed profile settings retain their property IDs and tenths-of-a-degree scale."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from custom_components.comfoconnect import ComfoConnectBridge
from custom_components.comfoconnect.number import NUMBER_TYPES, ComfoConnectNumber
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


@pytest.mark.parametrize("profile,property_id", [("warm", 10), ("normal", 11), ("cool", 12)])
def test_profile_write_uses_its_device_property_and_temperature_scale(tmp_path, profile, property_id):
    """Warm/Normal/Cool targets cannot overwrite one another's property."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = ComfoConnectBridge(hass, "127.0.0.1", "test")
        bridge.get_single_property = AsyncMock(return_value=210)
        bridge.cmd_rmi_request = AsyncMock(side_effect=[SimpleNamespace(message=b"\xb4\x00\xfa\x00"), SimpleNamespace(message=b"\x01\x00")])
        bridge.set_property_typed = AsyncMock()
        description = next(item for item in NUMBER_TYPES if item.key == f"temperature_profile_{profile}")
        entity = ComfoConnectNumber(bridge, SimpleNamespace(), description)
        entity.hass = hass
        entity.entity_id = f"number.profile_{profile}"
        await entity.async_update()
        await entity.async_set_native_value(21.5)
        assert bridge.set_property_typed.await_args.args[2:4] == (property_id, 215)
        assert entity.native_value == 21.5
        assert entity.native_step == 0.1
        assert not entity.entity_registry_enabled_default

    asyncio.run(scenario())
