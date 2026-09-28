"""Regression tests for repeated ComfoConnect alarm updates."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

from custom_components.comfoconnect import ComfoConnectBridge


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
