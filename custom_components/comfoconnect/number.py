"""Number entities for the ComfoConnect integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiocomfoconnect.const import (
    UNIT_TEMPHUMCONTROL,
    UNIT_VENTILATIONCONFIG,
    PdoType,
    VentilationSpeed,
)
from aiocomfoconnect.exceptions import (
    AioComfoConnectNotConnected,
    AioComfoConnectNotReachable,
    AioComfoConnectTimeout,
    ComfoConnectRmiError,
)
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfVolumeFlowRate
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, SIGNAL_COMFOCONNECT_AVAILABILITY, ComfoConnectBridge

_LOGGER = logging.getLogger(__name__)

PROPERTY_RANGE = 0x20
PROPERTY_STEP = 0x40


@dataclass
class ComfoConnectNumberRequiredKeysMixin:
    """Mixin for required number keys."""

    unit: int
    subunit: int
    property_id: int
    property_type: int


@dataclass
class ComfoConnectNumberEntityDescription(NumberEntityDescription, ComfoConnectNumberRequiredKeysMixin):
    """Describes a ComfoConnect number entity."""

    scale: int = 1
    speed: str | None = None


NUMBER_TYPES = (
    ComfoConnectNumberEntityDescription(
        key="airflow_away",
        name="Away airflow target",
        icon="mdi:fan-speed-1",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        mode=NumberMode.BOX,
        unit=UNIT_VENTILATIONCONFIG,
        subunit=1,
        property_id=3,
        property_type=PdoType.TYPE_CN_INT16,
        speed=VentilationSpeed.AWAY,
    ),
    ComfoConnectNumberEntityDescription(
        key="airflow_low",
        name="Low airflow target",
        icon="mdi:fan-speed-1",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        mode=NumberMode.BOX,
        unit=UNIT_VENTILATIONCONFIG,
        subunit=1,
        property_id=4,
        property_type=PdoType.TYPE_CN_INT16,
        speed=VentilationSpeed.LOW,
    ),
    ComfoConnectNumberEntityDescription(
        key="airflow_medium",
        name="Medium airflow target",
        icon="mdi:fan-speed-2",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        mode=NumberMode.BOX,
        unit=UNIT_VENTILATIONCONFIG,
        subunit=1,
        property_id=5,
        property_type=PdoType.TYPE_CN_INT16,
        speed=VentilationSpeed.MEDIUM,
    ),
    ComfoConnectNumberEntityDescription(
        key="airflow_high",
        name="High airflow target",
        icon="mdi:fan-speed-3",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        mode=NumberMode.BOX,
        unit=UNIT_VENTILATIONCONFIG,
        subunit=1,
        property_id=6,
        property_type=PdoType.TYPE_CN_INT16,
        speed=VentilationSpeed.HIGH,
    ),
    ComfoConnectNumberEntityDescription(
        key="rmot_heating",
        name="Heating RMOT threshold",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        unit=UNIT_TEMPHUMCONTROL,
        subunit=1,
        property_id=2,
        property_type=PdoType.TYPE_CN_INT16,
        scale=10,
    ),
    ComfoConnectNumberEntityDescription(
        key="rmot_cooling",
        name="Cooling RMOT threshold",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        unit=UNIT_TEMPHUMCONTROL,
        subunit=1,
        property_id=3,
        property_type=PdoType.TYPE_CN_INT16,
        scale=10,
    ),
    ComfoConnectNumberEntityDescription(
        key="temperature_profile_warm",
        name="Warm profile target temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        unit=UNIT_TEMPHUMCONTROL,
        subunit=1,
        property_id=10,
        property_type=PdoType.TYPE_CN_INT16,
        scale=10,
    ),
    ComfoConnectNumberEntityDescription(
        key="temperature_profile_normal",
        name="Normal profile target temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        unit=UNIT_TEMPHUMCONTROL,
        subunit=1,
        property_id=11,
        property_type=PdoType.TYPE_CN_INT16,
        scale=10,
    ),
    ComfoConnectNumberEntityDescription(
        key="temperature_profile_cool",
        name="Cool profile target temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
        unit=UNIT_TEMPHUMCONTROL,
        subunit=1,
        property_id=12,
        property_type=PdoType.TYPE_CN_INT16,
        scale=10,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the ComfoConnect number entities."""
    ccb = hass.data[DOMAIN][config_entry.entry_id]

    numbers = [ComfoConnectNumber(ccb=ccb, config_entry=config_entry, description=description) for description in NUMBER_TYPES]

    async_add_entities(numbers, True)


class ComfoConnectNumber(NumberEntity):
    """Representation of a ComfoConnect writable numeric property."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_should_poll = True
    entity_description: ComfoConnectNumberEntityDescription

    def __init__(
        self,
        ccb: ComfoConnectBridge,
        config_entry: ConfigEntry,
        description: ComfoConnectNumberEntityDescription,
    ) -> None:
        """Initialize the ComfoConnect number."""
        self._ccb = ccb
        self._constraints_generation: int | None = None
        self._attr_available = False
        self.entity_description = description
        self._attr_unique_id = f"{self._ccb.uuid}-{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._ccb.uuid)},
        )

    async def async_added_to_hass(self) -> None:
        """Register for bridge availability changes."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_COMFOCONNECT_AVAILABILITY.format(self._ccb.uuid),
                self._handle_availability_update,
            )
        )

    @property
    def available(self) -> bool:
        """Use constraints only from the bridge's current acknowledged session."""
        return self._attr_available and self._ccb.is_available and self._constraints_generation == self._ccb.connection_generation

    @callback
    def _handle_availability_update(self, available: bool) -> None:
        """Invalidate constraints on disconnect and wait for a successful poll."""
        if not available:
            self._constraints_generation = None
        self._attr_available = available and self._constraints_generation == self._ccb.connection_generation
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Read the value, loading constraints once per bridge connection."""
        if not self._ccb.is_available:
            self._handle_availability_update(False)
            return

        try:
            generation = self._ccb.connection_generation
            value = await self._ccb.get_single_property(
                self.entity_description.unit,
                self.entity_description.subunit,
                self.entity_description.property_id,
                self.entity_description.property_type,
            )
            if self._constraints_generation != generation:
                await self._update_constraints()
            if generation != self._ccb.connection_generation:
                raise ValueError("Bridge session changed while reading the number")
        except (ComfoConnectRmiError, AioComfoConnectTimeout, AioComfoConnectNotConnected, AioComfoConnectNotReachable, ValueError) as err:
            self._attr_available = self._ccb.is_available and self._constraints_generation == self._ccb.connection_generation
            _LOGGER.warning("Could not update %s; keeping the last value: %s", self.entity_description.name, err)
            return

        self._attr_native_value = self._decode_value(value)
        self._attr_available = True

    async def async_set_native_value(self, value: float) -> None:
        """Set the configured property value."""
        if not self.available:
            raise HomeAssistantError("The number is unavailable until its value and constraints have been read")

        encoded_value = round(value * self.entity_description.scale)

        if self.entity_description.speed:
            await self._ccb.set_flow_for_speed(self.entity_description.speed, encoded_value)
        else:
            await self._ccb.set_property_typed(
                self.entity_description.unit,
                self.entity_description.subunit,
                self.entity_description.property_id,
                encoded_value,
                self.entity_description.property_type,
            )

        self._attr_native_value = self._decode_value(encoded_value)
        self.async_write_ha_state()

    async def _update_constraints(self) -> None:
        """Read min, max, and step metadata from the ventilation unit."""
        generation = self._ccb.connection_generation
        range_data = await self._read_property_metadata(PROPERTY_RANGE)
        step_data = await self._read_property_metadata(PROPERTY_STEP)
        if len(range_data) < 2 or not step_data or range_data[0] > range_data[1] or step_data[0] <= 0:
            raise ValueError("Invalid number property constraints")
        if generation != self._ccb.connection_generation:
            raise ValueError("Bridge session changed while reading number constraints")

        self._attr_native_min_value = self._decode_value(range_data[0])
        self._attr_native_max_value = self._decode_value(range_data[1])
        self._attr_native_step = self._decode_value(step_data[0])
        self._constraints_generation = generation

    async def _read_property_metadata(self, kind: int) -> list[int]:
        """Read typed property metadata values from the bridge."""
        result = await self._ccb.cmd_rmi_request(
            bytes(
                [
                    0x01,
                    self.entity_description.unit,
                    self.entity_description.subunit,
                    kind,
                    self.entity_description.property_id,
                ]
            )
        )
        data = bytes(result.message)
        if len(data) % 2:
            return []
        return [int.from_bytes(data[index : index + 2], byteorder="little", signed=True) for index in range(0, len(data), 2)]

    def _decode_value(self, value: int) -> float:
        """Decode raw property values to their native Home Assistant value."""
        return value / self.entity_description.scale
