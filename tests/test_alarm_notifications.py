"""Native notifications follow the chosen policy without changing raw alarms."""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiocomfoconnect.const import ERRORS, ERRORS_140
from custom_components.comfoconnect import EVENT_COMFOCONNECT_ALARM, ComfoConnectBridge
from custom_components.comfoconnect.const import CONF_LOCAL_UUID, CONF_UUID, DOMAIN
from custom_components.comfoconnect.notifications import CONF_ALARM_NOTIFICATIONS, AlarmNotificationMode
from homeassistant.components import persistent_notification as pn
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from pytest_homeassistant_custom_component.common import MockConfigEntry

BRIDGE = "custom_components.comfoconnect.ComfoConnectBridge"


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Use the actual integration and Home Assistant config/notification APIs."""


@pytest.fixture
def notices(hass):
    """Observe HA's delivered notifications, including user dismissal."""
    current = {}

    @callback
    def received(update_type, notifications):
        if update_type == pn.UpdateType.REMOVED:
            for notification_id in notifications:
                current.pop(notification_id, None)
        else:
            current.update(notifications)

    unsubscribe = pn.async_register_callback(hass, received)
    yield current
    unsubscribe()


@pytest.fixture
async def setup_bridge(hass):
    """Mock the network boundary and platform setup, retaining real entry lifecycle."""
    with ExitStack() as stack:
        for method in ("connect", "disconnect"):
            stack.enter_context(patch(f"{BRIDGE}.{method}", new_callable=AsyncMock))
        stack.enter_context(
            patch(f"{BRIDGE}.cmd_version_request", new_callable=AsyncMock, return_value=SimpleNamespace(serialNumber="DEMO", gatewayVersion=0))
        )
        stack.enter_context(patch(f"{BRIDGE}.get_property", new_callable=AsyncMock, return_value="ComfoAir Q350"))
        stack.enter_context(patch("custom_components.comfoconnect.version_decode", return_value="1.0.0"))
        stack.enter_context(patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups", new_callable=AsyncMock))
        stack.enter_context(patch("homeassistant.config_entries.ConfigEntries.async_unload_platforms", new_callable=AsyncMock, return_value=True))

        async def setup(options=None, minor_version=1, uuid="test-bridge"):
            entry = MockConfigEntry(
                domain=DOMAIN,
                title=uuid,
                version=1,
                minor_version=minor_version,
                data={CONF_HOST: "192.0.2.1", CONF_UUID: uuid, CONF_LOCAL_UUID: "11" * 16},
                options=options or {},
            )
            entry.add_to_hass(hass)
            assert await hass.config_entries.async_setup(entry.entry_id)
            return entry, hass.data[DOMAIN][entry.entry_id]

        yield setup


async def test_existing_entries_keep_native_faults_and_maintenance(hass, setup_bridge, notices):
    """Migration keeps notification delivery on and does not lose other settings."""
    entry, bridge = await setup_bridge(options={"other_setting": "kept"})
    assert entry.minor_version == 2
    assert entry.options == {CONF_ALARM_NOTIFICATIONS: AlarmNotificationMode.ALL, "other_setting": "kept"}
    bridge.alarm_callback(1, {79: ERRORS[79]})
    await hass.async_block_till_done()
    notice = notices[bridge.notifications.notification_id]
    assert notice["title"] == "ComfoConnect filter maintenance"
    assert ERRORS[79] in notice["message"]
    bridge.alarm_callback(2, {21: ERRORS[21]})
    await hass.async_block_till_done()
    notice = notices[bridge.notifications.notification_id]
    assert notice["title"] == "ComfoConnect needs attention"
    assert "### Filter maintenance" in notice["message"]
    assert ERRORS[21] in notice["message"]


@pytest.mark.parametrize("mode", list(AlarmNotificationMode))
async def test_migration_preserves_an_explicit_choice(hass, setup_bridge, mode):
    """An existing option is never reset by migration or another setup."""
    entry, _ = await setup_bridge(options={CONF_ALARM_NOTIFICATIONS: mode})
    assert entry.options[CONF_ALARM_NOTIFICATIONS] == mode
    assert entry.minor_version == 2


@pytest.mark.parametrize("mode", list(AlarmNotificationMode))
async def test_options_apply_without_reconnecting(hass, setup_bridge, notices, mode):
    """Saving a real options flow updates current alarms immediately, preserving other options."""
    entry, bridge = await setup_bridge(options={"other_setting": "kept"})
    bridge.alarm_callback(1, {79: ERRORS[79]})
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    assert result["data_schema"]({}) == {CONF_ALARM_NOTIFICATIONS: AlarmNotificationMode.ALL}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {CONF_ALARM_NOTIFICATIONS: mode})
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert entry.options == {CONF_ALARM_NOTIFICATIONS: mode, "other_setting": "kept"}
    assert bool(notices) == (mode == AlarmNotificationMode.ALL)
    assert hass.data[DOMAIN][entry.entry_id] is bridge
    bridge.connect.assert_awaited_once()


@pytest.mark.parametrize(
    "definitions,filter_codes,fault_code",
    [(ERRORS, (77, 78, 79), 83), (ERRORS_140, (73, 74, 75), 79)],
    ids=["current-firmware", "legacy-firmware"],
)
async def test_faults_only_uses_firmware_specific_definitions(hass, setup_bridge, notices, definitions, filter_codes, fault_code):
    """Filter reminders stay silent; an overlapping older fault code still alerts."""
    _, bridge = await setup_bridge(options={CONF_ALARM_NOTIFICATIONS: AlarmNotificationMode.FAULTS})
    filters = {code: definitions[code] for code in filter_codes}
    bridge.alarm_callback(1, filters)
    await hass.async_block_till_done()
    assert not notices
    bridge.alarm_callback(1, {**filters, fault_code: definitions[fault_code]})
    await hass.async_block_till_done()
    notice = notices[bridge.notifications.notification_id]
    assert definitions[fault_code] in notice["message"]
    assert all(message not in notice["message"] for message in filters.values())
    bridge.alarm_callback(1, filters)
    await hass.async_block_till_done()
    assert not notices


async def test_rechecks_wait_for_confirmed_clear_across_nodes(hass, setup_bridge, notices):
    """Recheck is silent, preserves known faults, and never clears another node."""
    _, bridge = await setup_bridge()
    bridge.alarm_callback(1, {100: ERRORS[100]})
    await hass.async_block_till_done()
    assert not notices
    bridge.alarm_callback(1, {21: ERRORS[21]})
    bridge.alarm_callback(2, {22: ERRORS[22]})
    await hass.async_block_till_done()
    notice_id = bridge.notifications.notification_id
    both = notices[notice_id]
    assert ERRORS[21] in both["message"] and ERRORS[22] in both["message"]
    bridge.alarm_callback(1, {100: ERRORS[100]})
    bridge.alarm_callback(3, {})
    await hass.async_block_till_done()
    assert notices[notice_id] == both
    bridge.alarm_callback(1, {100: ERRORS[100], 23: ERRORS[23]})
    await hass.async_block_till_done()
    assert ERRORS[21] in notices[notice_id]["message"] and ERRORS[23] in notices[notice_id]["message"]
    assert ERRORS[100] not in notices[notice_id]["message"]
    bridge.alarm_callback(1, {})
    await hass.async_block_till_done()
    assert ERRORS[21] not in notices[notice_id]["message"]
    assert ERRORS[22] in notices[notice_id]["message"]
    bridge.alarm_callback(2, {})
    await hass.async_block_till_done()
    assert not notices


async def test_dismissal_survives_duplicate_filtered_reports_and_reload(hass, setup_bridge, notices):
    """Only a relevant alarm change reopens a notice the user dismissed."""
    entry, bridge = await setup_bridge(options={CONF_ALARM_NOTIFICATIONS: AlarmNotificationMode.FAULTS})
    bridge.alarm_callback(1, {21: ERRORS[21]})
    await hass.async_block_till_done()
    notice_id = bridge.notifications.notification_id
    assert notice_id in notices
    pn.async_dismiss(hass, notice_id)
    bridge.alarm_callback(1, {21: ERRORS[21]})
    bridge.alarm_callback(2, {79: ERRORS[79]})
    await hass.async_block_till_done()
    assert not notices
    assert await hass.config_entries.async_reload(entry.entry_id)
    reloaded = hass.data[DOMAIN][entry.entry_id]
    assert reloaded is not bridge
    reloaded.alarm_callback(1, {21: ERRORS[21]})
    await hass.async_block_till_done()
    assert not notices
    reloaded.alarm_callback(1, {21: ERRORS[21], 22: ERRORS[22]})
    await hass.async_block_till_done()
    assert ERRORS[22] in notices[notice_id]["message"]


async def test_reload_and_removal_preserve_other_nodes_and_bridges(hass, setup_bridge, notices):
    """A first clear after reload and another entry's removal cannot clear an active unit."""
    entry, bridge = await setup_bridge()
    _, other = await setup_bridge(uuid="other-bridge")
    bridge.alarm_callback(1, {21: ERRORS[21]})
    other.alarm_callback(1, {22: ERRORS[22]})
    await hass.async_block_till_done()
    assert len(notices) == 2
    assert await hass.config_entries.async_reload(entry.entry_id)
    reloaded = hass.data[DOMAIN][entry.entry_id]
    reloaded.alarm_callback(2, {})
    await hass.async_block_till_done()
    assert ERRORS[21] in notices[bridge.notifications.notification_id]["message"]
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert list(notices) == [other.notifications.notification_id]


async def test_off_keeps_alarm_events_and_raw_diagnostics(hass, setup_bridge, notices):
    """Choosing Off suppresses delivery while alarms and automation events remain available."""
    _, bridge = await setup_bridge(options={CONF_ALARM_NOTIFICATIONS: AlarmNotificationMode.OFF})
    events = []
    hass.bus.async_listen(EVENT_COMFOCONNECT_ALARM, callback(lambda event: events.append(event.data)))
    bridge.alarm_callback(1, {79: ERRORS[79]})
    await hass.async_block_till_done()
    assert not notices
    assert bridge.active_alarms == {1: {79: ERRORS[79]}}
    assert events[0]["errors"] == [{"id": 79, "message": ERRORS[79]}]
    bridge.notifications.set_mode(AlarmNotificationMode.ALL)
    await hass.async_block_till_done()
    assert ERRORS[79] in notices[bridge.notifications.notification_id]["message"]


async def test_off_is_applied_before_connecting(hass, setup_bridge, notices):
    """Early alarms during connection cannot bypass a new installation's Off setting."""

    async def connect(bridge, local_uuid):
        bridge.alarm_callback(1, {21: ERRORS[21]})

    with patch(f"{BRIDGE}.connect", new=connect):
        _, bridge = await setup_bridge(options={CONF_ALARM_NOTIFICATIONS: AlarmNotificationMode.OFF}, minor_version=2)
    await hass.async_block_till_done()
    assert bridge.active_alarms == {1: {21: ERRORS[21]}}
    assert not notices


async def test_first_confirmed_clear_removes_an_old_notice(hass, notices):
    """An old notification is removed once the unit confirms an empty snapshot."""
    bridge = ComfoConnectBridge(hass, "192.0.2.1", "test-bridge")
    pn.async_create(hass, "Old alarm", notification_id=bridge.notifications.notification_id)
    bridge.alarm_callback(1, {})
    await hass.async_block_till_done()
    assert not notices
