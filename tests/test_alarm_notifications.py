"""Regression tests for repeated ComfoConnect alarm updates."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

from custom_components.comfoconnect import ComfoConnectBridge
from custom_components.comfoconnect.binary_sensor import ComfoConnectAlarmBinarySensor
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_setup as setup_loader


def test_unchanged_alarm_does_not_repeat_events_or_notifications():
    loop = asyncio.new_event_loop()
    hass = SimpleNamespace(loop=loop, bus=Mock())
    bridge = ComfoConnectBridge(hass, "127.0.0.1", "test-bridge")

    try:
        with (
            patch("custom_components.comfoconnect.dispatcher_send") as dispatcher,
            patch("custom_components.comfoconnect.persistent_notification.async_create") as create,
            patch("custom_components.comfoconnect.persistent_notification.async_dismiss") as dismiss,
        ):
            incoming = {79: "Order new filters"}
            bridge.alarm_callback(1, incoming)
            bridge.alarm_callback(1, incoming)

            incoming[79] = "Mutated after delivery"
            bridge.alarm_callback(1, {79: "Order new filters"})

            assert dispatcher.call_count == 1
            assert hass.bus.async_fire.call_count == 1
            assert create.call_count == 1
            dismiss.assert_not_called()

            bridge.alarm_callback(1, {79: "Replace filters now"})
            bridge.alarm_callback(1, {})
            bridge.alarm_callback(1, {})

            assert dispatcher.call_count == 3
            assert hass.bus.async_fire.call_count == 3
            assert create.call_count == 2
            dismiss.assert_called_once()
            assert bridge.active_alarms == {}
    finally:
        loop.close()


def test_initial_clear_dismisses_a_notification_left_from_a_prior_session():
    loop = asyncio.new_event_loop()
    hass = SimpleNamespace(loop=loop, bus=Mock())
    bridge = ComfoConnectBridge(hass, "127.0.0.1", "test-bridge")

    try:
        with patch("custom_components.comfoconnect.persistent_notification.async_dismiss") as dismiss:
            bridge.alarm_callback(1, {})
            dismiss.assert_called_once()
    finally:
        loop.close()


def test_dispatched_alarms_and_clears_update_the_ha_binary_sensor(tmp_path):
    """Real dispatcher callbacks publish alarm state from HA's event-loop thread."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        setup_loader(hass)
        bridge = ComfoConnectBridge(hass, "127.0.0.1", "test-bridge")
        entity = ComfoConnectAlarmBinarySensor(bridge)
        entity.hass = hass
        entity.entity_id = "binary_sensor.active_alarms"
        await entity.async_added_to_hass()
        entity.async_write_ha_state()
        assert hass.states.get(entity.entity_id).state == "off"

        with (
            patch("custom_components.comfoconnect.persistent_notification.async_create"),
            patch("custom_components.comfoconnect.persistent_notification.async_dismiss"),
        ):
            bridge.alarm_callback(1, {79: "Replace filters"})
            await hass.async_block_till_done()
            state = hass.states.get(entity.entity_id)
            assert state.state == "on"
            assert state.attributes["alarm_count"] == 1
            assert state.attributes["alarms"] == [{"id": 79, "message": "Replace filters"}]

            bridge.alarm_callback(1, {})
            await hass.async_block_till_done()
            state = hass.states.get(entity.entity_id)
            assert state.state == "off"
            assert state.attributes["alarm_count"] == 0

        await entity.async_will_remove_from_hass()

    asyncio.run(scenario())
