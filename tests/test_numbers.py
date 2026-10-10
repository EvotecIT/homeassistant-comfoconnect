"""Numeric settings retain acknowledged values and use current-session constraints."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiocomfoconnect.exceptions import AioComfoConnectNotConnected, AioComfoConnectTimeout, ComfoConnectRmiError
from custom_components.comfoconnect import ComfoConnectBridge
from custom_components.comfoconnect.number import NUMBER_TYPES, ComfoConnectNumber
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.loader import async_setup as setup_loader


def metadata(*values):
    """Build the signed 16-bit metadata returned by the device boundary."""
    return SimpleNamespace(message=b"".join(value.to_bytes(2, "little", signed=True) for value in values))


def number_entity(hass):
    """Create a real cooling-threshold entity with only device I/O mocked."""
    bridge = ComfoConnectBridge(hass, "127.0.0.1", "test-bridge")
    bridge.get_single_property = AsyncMock(return_value=200)
    bridge.cmd_rmi_request = AsyncMock(side_effect=[metadata(150, 400), metadata(10)])
    bridge.set_property_typed = AsyncMock()
    description = next(item for item in NUMBER_TYPES if item.key == "rmot_cooling")
    entity = ComfoConnectNumber(bridge, SimpleNamespace(), description)
    entity.hass = hass
    entity.entity_id = "number.cooling_threshold"
    return bridge, entity


@pytest.mark.parametrize("error", [ComfoConnectRmiError("Busy"), AioComfoConnectTimeout("Timed out")])
def test_acknowledged_write_is_published_and_survives_a_failed_read(tmp_path, error):
    """A follow-up device read cannot hide an acknowledged change from HA."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge, entity = number_entity(hass)
        await entity.async_update()
        assert (entity.native_min_value, entity.native_max_value, entity.native_step) == (15, 40, 1)
        await entity.async_set_native_value(21)
        assert bridge.set_property_typed.await_args.args[3] == 210
        assert hass.states.get(entity.entity_id).state == "21.0"
        bridge.get_single_property.side_effect = error
        await entity.async_update()
        assert entity.native_value == 21
        assert entity.available
        bridge.get_single_property.side_effect = None
        bridge.get_single_property.return_value = 210
        await entity.async_update()
        assert entity.native_value == 21
        assert bridge.cmd_rmi_request.await_count == 2

    asyncio.run(scenario())


def test_old_readback_is_ignored_until_confirmation_or_a_different_value(tmp_path):
    """Briefly stale readback is ignored; a later external value is still accepted."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge, entity = number_entity(hass)
        await entity.async_update()
        await entity.async_set_native_value(21)
        await entity.async_update()
        assert entity.native_value == 21
        bridge.get_single_property.return_value = 210
        await entity.async_update()
        assert entity.native_value == 21
        await entity.async_set_native_value(22)
        bridge.get_single_property.return_value = 230
        await entity.async_update()
        assert entity.native_value == 23

    asyncio.run(scenario())


def test_a_poll_started_before_a_write_cannot_undo_its_acknowledgement(tmp_path):
    """An overlapping in-flight read cannot publish an earlier device value."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge, entity = number_entity(hass)
        await entity.async_update()
        result = hass.loop.create_future()

        async def delayed_read(*_args):
            return await result

        bridge.get_single_property.side_effect = delayed_read
        pending = hass.loop.create_task(entity.async_update())
        await asyncio.sleep(0)
        await entity.async_set_native_value(21)
        result.set_result(200)
        await pending
        assert entity.native_value == 21
        assert hass.states.get(entity.entity_id).state == "21.0"

    asyncio.run(scenario())


def test_successive_writes_keep_the_latest_value_during_stale_readback(tmp_path):
    """Older values from two acknowledged writes cannot replace the latest one."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge, entity = number_entity(hass)
        await entity.async_update()
        await entity.async_set_native_value(21)
        await entity.async_set_native_value(22)
        for stale in (200, 210):
            bridge.get_single_property.return_value = stale
            await entity.async_update()
            assert entity.native_value == 22
        bridge.get_single_property.return_value = 220
        await entity.async_update()
        assert entity.native_value == 22

    asyncio.run(scenario())


def test_readback_grace_expires_instead_of_hiding_the_device_forever(tmp_path):
    """A device that retains its old value becomes authoritative after the grace."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge, entity = number_entity(hass)
        await entity.async_update()
        with patch("custom_components.comfoconnect.number.monotonic", return_value=100):
            await entity.async_set_native_value(21)
        with patch("custom_components.comfoconnect.number.monotonic", return_value=106):
            await entity.async_update()
        assert entity.native_value == 20

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "range_response,step_response", [(metadata(), metadata(10)), (metadata(400, 150), metadata(10)), (metadata(150, 400), metadata(0))]
)
def test_invalid_constraints_leave_the_setting_unavailable(tmp_path, range_response, step_response):
    """HA's default bounds cannot enable writes after incomplete/invalid metadata."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge, entity = number_entity(hass)
        bridge.cmd_rmi_request.side_effect = [range_response, step_response]
        await entity.async_update()
        assert not entity.available
        with pytest.raises(HomeAssistantError):
            await entity.async_set_native_value(21)
        bridge.set_property_typed.assert_not_awaited()

    asyncio.run(scenario())


def test_metadata_failure_retries_and_new_sessions_reload_limits(tmp_path):
    """Constraints are cached only after success and only for the current session."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge, entity = number_entity(hass)
        bridge.cmd_rmi_request.side_effect = ComfoConnectRmiError("Busy")
        await entity.async_update()
        assert not entity.available
        bridge.cmd_rmi_request.side_effect = [metadata(150, 400), metadata(10)]
        await entity.async_update()
        assert entity.available
        with patch("aiocomfoconnect.bridge.Bridge._send", new=AsyncMock()):
            await bridge.cmd_start_session(True)
        assert not entity.available
        with pytest.raises(HomeAssistantError):
            await entity.async_set_native_value(21)
        bridge.cmd_rmi_request.side_effect = [metadata(150, 450), metadata(20)]
        await entity.async_update()
        assert entity.available
        assert (entity.native_min_value, entity.native_max_value, entity.native_step) == (15, 45, 2)

    asyncio.run(scenario())


def test_failed_write_and_failed_session_start_do_not_publish_success(tmp_path):
    """Only a device acknowledgement changes the number or the session identity."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge, entity = number_entity(hass)
        await entity.async_update()
        entity.async_write_ha_state()
        bridge.set_property_typed.side_effect = ComfoConnectRmiError("Busy")
        with pytest.raises(ComfoConnectRmiError):
            await entity.async_set_native_value(21)
        assert hass.states.get(entity.entity_id).state == "20.0"
        with patch("aiocomfoconnect.bridge.Bridge._send", new=AsyncMock(side_effect=AioComfoConnectNotConnected("Offline"))):
            with pytest.raises(AioComfoConnectNotConnected):
                await bridge.cmd_start_session(True)
        assert entity.available

    asyncio.run(scenario())


def test_session_change_during_metadata_does_not_enable_writes(tmp_path):
    """Metadata assembled across different sessions is discarded."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge, entity = number_entity(hass)
        calls = 0

        async def changed_session(_message):
            nonlocal calls
            calls += 1
            if calls == 1:
                with patch("aiocomfoconnect.bridge.Bridge._send", new=AsyncMock()):
                    await bridge.cmd_start_session(True)
                return metadata(150, 400)
            return metadata(10)

        bridge.cmd_rmi_request.side_effect = changed_session
        await entity.async_update()
        assert not entity.available
        with pytest.raises(HomeAssistantError):
            await entity.async_set_native_value(21)

    asyncio.run(scenario())
