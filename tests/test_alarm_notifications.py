"""Notifications change with alarms and clear stale notifications after restart."""

import asyncio
from unittest.mock import patch

from custom_components.comfoconnect import ComfoConnectBridge
from homeassistant.core import HomeAssistant


def test_alarm_notification_deduplication_changes_and_clear(tmp_path):
    """An unchanged callback cannot recreate a persistent notification."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        bridge = ComfoConnectBridge(hass, "127.0.0.1", "test-bridge")
        with (
            patch("custom_components.comfoconnect.persistent_notification.async_create") as create,
            patch("custom_components.comfoconnect.persistent_notification.async_dismiss") as dismiss,
        ):
            bridge.alarm_callback(1, {79: "Replace filters"})
            bridge.alarm_callback(1, {79: "Replace filters"})
            assert create.call_count == 1
            assert create.call_args.kwargs["notification_id"] == "comfoconnect_alarm_test-bridge"
            assert create.call_args.kwargs["title"] == "ComfoConnect needs attention"
            bridge.alarm_callback(1, {100: "Recheck"})
            assert create.call_count == 2
            assert create.call_args.kwargs["title"] == "ComfoConnect is checking alarms"
            bridge.alarm_callback(1, {})
            bridge.alarm_callback(1, {})
            dismiss.assert_called_once_with(hass, "comfoconnect_alarm_test-bridge")

    asyncio.run(scenario())


def test_first_clear_dismisses_a_notification_from_before_restart(tmp_path):
    """An initially empty cache cannot suppress the first device clear."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        bridge = ComfoConnectBridge(hass, "127.0.0.1", "test-bridge")
        with patch("custom_components.comfoconnect.persistent_notification.async_dismiss") as dismiss:
            bridge.alarm_callback(1, {})
            dismiss.assert_called_once_with(hass, "comfoconnect_alarm_test-bridge")

    asyncio.run(scenario())
