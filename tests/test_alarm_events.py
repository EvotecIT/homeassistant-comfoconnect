"""Alarm automation events retain their payload and change-only delivery contract."""

import asyncio

from custom_components.comfoconnect import EVENT_COMFOCONNECT_ALARM, ComfoConnectBridge
from homeassistant.core import HomeAssistant, callback


def test_changed_and_cleared_alarm_events_keep_the_public_payload(tmp_path):
    """Real HA listeners receive one event per changed node/content snapshot."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        bridge = ComfoConnectBridge(hass, "127.0.0.1", "test-bridge")
        events = []

        @callback
        def received(event):
            events.append(event.data)

        remove = hass.bus.async_listen(EVENT_COMFOCONNECT_ALARM, received)
        try:
            bridge.alarm_callback(1, {79: "Replace filters"})
            bridge.alarm_callback(2, {})
            bridge.alarm_callback(1, {79: "Replace filters"})
            bridge.alarm_callback(2, {})
            bridge.alarm_callback(1, {})
            await hass.async_block_till_done()
            assert events == [
                {"bridge_uuid": "test-bridge", "node_id": 1, "errors": [{"id": 79, "message": "Replace filters"}]},
                {"bridge_uuid": "test-bridge", "node_id": 2, "errors": []},
                {"bridge_uuid": "test-bridge", "node_id": 1, "errors": []},
            ]
        finally:
            remove()

    asyncio.run(scenario())
