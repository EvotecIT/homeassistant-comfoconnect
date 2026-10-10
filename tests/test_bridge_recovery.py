"""Bridge availability and reauthentication follow acknowledged responses."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiocomfoconnect.exceptions import AioComfoConnectNotConnected, AioComfoConnectTimeout, ComfoConnectNotAllowed, ComfoConnectOtherSession
from custom_components.comfoconnect import SIGNAL_COMFOCONNECT_AVAILABILITY, ComfoConnectBridge, async_setup_entry
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect


def test_background_reconnect_waits_for_a_reply_before_becoming_available(tmp_path):
    """An early connect return must leave unavailable entities unavailable."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        bridge = ComfoConnectBridge(hass, "127.0.0.1", "test-bridge")
        changes = []

        @callback
        def received(value):
            changes.append(value)

        remove = async_dispatcher_connect(hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format(bridge.uuid), received)
        bridge._reconnect_task = hass.loop.create_future()
        bridge.cmd_time_request = AsyncMock(side_effect=[AioComfoConnectNotConnected("Offline"), AioComfoConnectNotConnected("Retrying"), None])
        try:
            await bridge.async_keepalive("local")
            assert not bridge.is_available
            assert changes == [False]
            await bridge.async_keepalive("local")
            assert bridge.is_available
            assert changes == [False, True]
        finally:
            bridge._reconnect_task.cancel()
            remove()

    asyncio.run(scenario())


@pytest.mark.parametrize("initial_error", [ComfoConnectNotAllowed("Lost session"), ComfoConnectOtherSession("Other client")])
@pytest.mark.parametrize(
    "recovery_error", [None, AioComfoConnectTimeout("Timed out"), ComfoConnectNotAllowed("Refused"), ComfoConnectOtherSession("Other client")]
)
def test_refused_session_is_closed_and_recovery_controls_availability(tmp_path, initial_error, recovery_error):
    """A refused open TCP session is replaced; persistent refusal reaches reauth."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        bridge = ComfoConnectBridge(hass, "127.0.0.1", "test-bridge")
        bridge.disconnect = AsyncMock()
        bridge.connect = AsyncMock()
        bridge.cmd_time_request = AsyncMock(side_effect=[initial_error, recovery_error])
        if isinstance(recovery_error, ComfoConnectNotAllowed):
            with pytest.raises(ComfoConnectNotAllowed):
                await bridge.async_keepalive("local")
            assert bridge.disconnect.await_count == 2
        else:
            await bridge.async_keepalive("local")
            assert bridge.disconnect.await_count == (2 if isinstance(recovery_error, ComfoConnectOtherSession) else 1)
        bridge.connect.assert_awaited_once_with("local")
        assert bridge.is_available is (recovery_error is None)

    asyncio.run(scenario())


def test_keepalive_callback_starts_reauth_for_persistent_refusal():
    """A rejected replacement session asks HA to reauthenticate the existing entry."""

    async def scenario():
        callbacks = []
        hass = SimpleNamespace(
            loop=asyncio.get_running_loop(), data={}, config_entries=SimpleNamespace(async_forward_entry_setups=AsyncMock()), bus=Mock()
        )
        entry = SimpleNamespace(
            entry_id="entry",
            data={"host": "127.0.0.1", CONF_UUID: "bridge", CONF_LOCAL_UUID: "local"},
            async_on_unload=Mock(),
            async_start_reauth=Mock(),
        )
        bridge = SimpleNamespace(
            uuid="bridge",
            connect=AsyncMock(),
            cmd_version_request=AsyncMock(return_value=SimpleNamespace(serialNumber="test", gatewayVersion=1)),
            get_property=AsyncMock(side_effect=["Q450", 1, "Unit"]),
            async_keepalive=AsyncMock(side_effect=ComfoConnectNotAllowed("Refused")),
        )

        def register_interval(_hass, handler, _interval):
            callbacks.append(handler)
            return Mock()

        with (
            patch("custom_components.comfoconnect.ComfoConnectBridge", return_value=bridge),
            patch("custom_components.comfoconnect.dr.async_get", return_value=Mock()),
            patch("custom_components.comfoconnect.async_track_time_interval", side_effect=register_interval),
        ):
            assert await async_setup_entry(hass, entry)
            await callbacks[0](None)
        entry.async_start_reauth.assert_called_once_with(hass)

    asyncio.run(scenario())
