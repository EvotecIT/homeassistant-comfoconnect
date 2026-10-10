"""Bridge availability follows acknowledged device responses."""

import asyncio
from unittest.mock import AsyncMock, patch

from aiocomfoconnect.exceptions import AioComfoConnectNotConnected
from custom_components.comfoconnect import SIGNAL_COMFOCONNECT_AVAILABILITY, ComfoConnectBridge
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect


def test_background_reconnect_does_not_restore_availability_until_a_reply(tmp_path):
    """The library's early connect return cannot make a disconnected bridge available."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        bridge = ComfoConnectBridge(hass, "127.0.0.1", "test-bridge")
        availability = []

        @callback
        def record_available(available):
            availability.append(available)

        remove = async_dispatcher_connect(hass, SIGNAL_COMFOCONNECT_AVAILABILITY.format(bridge.uuid), record_available)
        bridge._reconnect_task = hass.loop.create_future()
        bridge.cmd_time_request = AsyncMock(side_effect=[AioComfoConnectNotConnected("Offline"), AioComfoConnectNotConnected("Retrying")])
        try:
            await bridge.async_keepalive("local-uuid")
            assert not bridge.is_available
            assert availability == [False]

            bridge.cmd_time_request.side_effect = None
            await bridge.async_keepalive("local-uuid")
            assert bridge.is_available
            assert availability == [False, True]
        finally:
            bridge._reconnect_task.cancel()
            remove()

    asyncio.run(scenario())


def test_only_acknowledged_sessions_advance_connection_generation(tmp_path):
    """Session tracking follows the public library command, rather than a keepalive timer."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        bridge = ComfoConnectBridge(hass, "127.0.0.1", "test-bridge")
        with patch("aiocomfoconnect.bridge.Bridge._send", new=AsyncMock()) as send:
            await bridge.cmd_start_session(True)
            assert bridge.connection_generation == 1
            send.side_effect = AioComfoConnectNotConnected("Offline")
            try:
                await bridge.cmd_start_session(True)
            except AioComfoConnectNotConnected:
                pass
            assert bridge.connection_generation == 1

    asyncio.run(scenario())
