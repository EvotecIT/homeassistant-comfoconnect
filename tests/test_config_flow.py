"""Registration names fit the bridge's UTF-8 buffer."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.comfoconnect.config_flow import ComfoConnectConfigFlow
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN
from custom_components.comfoconnect.notifications import CONF_ALARM_NOTIFICATIONS, AlarmNotificationMode
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant


@pytest.mark.parametrize("location_name", ["Home", "Chalet Bergblick", "ą" * 8, "A" * 14 + "🏠"])
def test_registration_name_fits_bridge_buffer(tmp_path, location_name):
    """Long or multibyte location names cannot produce an oversized registration."""

    async def scenario():
        hass = HomeAssistant(str(tmp_path))
        hass.config.location_name = location_name
        flow = ComfoConnectConfigFlow()
        flow.hass = hass
        flow.local_uuid = "mock-local"
        flow.bridge = SimpleNamespace(host="127.0.0.1", uuid="mock-bridge", register=AsyncMock(), disconnect=AsyncMock())
        flow.async_create_entry = Mock(return_value={"type": "create_entry"})

        await flow._register()

        device_name = flow.bridge.register.await_args.args[1]
        assert len(device_name.encode("utf-8")) <= 31
        assert device_name.startswith("Home Assistant (")
        if location_name == "Home":
            assert device_name == "Home Assistant (Home)"
        flow.bridge.disconnect.assert_awaited_once()
        flow.async_create_entry.assert_called_once()

    asyncio.run(scenario())


async def test_new_installations_default_to_notifications_off(hass, enable_custom_integrations):
    """The actual manual registration flow stores Off, distinct from migrated entries."""
    bridge = SimpleNamespace(host="192.0.2.1", uuid="test-bridge", register=AsyncMock(), disconnect=AsyncMock())
    with (
        patch("custom_components.comfoconnect.config_flow.aiocomfoconnect.discover_bridges", return_value=[bridge]),
        patch("homeassistant.config_entries.ConfigEntries.async_setup", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_UUID: "manual"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: bridge.host})
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    entry = result["result"]
    assert entry.options == {CONF_ALARM_NOTIFICATIONS: AlarmNotificationMode.OFF}
    assert entry.minor_version == 2
    assert entry.data[CONF_LOCAL_UUID]
    bridge.register.assert_awaited_once()
