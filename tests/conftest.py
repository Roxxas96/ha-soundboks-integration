"""Shared fixtures: a fake speaker standing in for the BLE stack."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from unittest.mock import patch

import pytest
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from custom_components.soundboks.protocol import (
    FIRMWARE_UUID,
    INPUTS_UUID,
    POWER_UUID,
    PROFILE_UUID,
    SECURITY_UUID,
    SERIAL_RX_UUID,
    SERIAL_TX_UUID,
    STEREO_UUID,
    VOLUME_UUID,
)

ADDRESS = "AA:BB:CC:DD:EE:FF"
NAME = "#202047"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/ in every test."""
    return


def make_ble_device() -> BLEDevice:
    return BLEDevice(ADDRESS, NAME, None)


@dataclass
class FakeSpeaker:
    """The speaker's state, which outlives each connection to it."""

    values: dict[str, bytes] = field(
        default_factory=lambda: {
            VOLUME_UUID: b"\x2d",
            POWER_UUID: b"\x01",
            PROFILE_UUID: bytes([0, 51, 51, 51, 51, 51, 51]),
            STEREO_UUID: b"\x00",
            INPUTS_UUID: bytes([0, 8]),
            SECURITY_UUID: b"\x00",
            FIRMWARE_UUID: b"2.4.2",
        }
    )
    pin: str | None = None
    unreachable: bool = False
    drop_on_power_write: bool = True
    writes: list[tuple[str, bytes]] = field(default_factory=list)
    connect_count: int = 0
    client: FakeBleakClient | None = None

    def set_pin(self, pin: str) -> None:
        self.pin = pin
        self.values[SECURITY_UUID] = b"\x01"

    def notify(self, uuid: str, data: bytes) -> None:
        assert self.client is not None and self.client.is_connected
        self.client.callbacks[uuid](None, bytearray(data))


class FakeServices:
    def __init__(self, values: dict[str, bytes]) -> None:
        self._values = values

    def get_characteristic(self, uuid: str) -> object | None:
        return object() if uuid in self._values else None


class FakeBleakClient:
    """Enough of BleakClient for the integration's client."""

    def __init__(self, speaker: FakeSpeaker, disconnected_callback: Callable | None) -> None:
        self.speaker = speaker
        self.is_connected = True
        self.authenticated = speaker.pin is None
        self.callbacks: dict[str, Callable] = {}
        self.services = FakeServices(speaker.values)
        self._disconnected_callback = disconnected_callback

    def _check(self) -> None:
        if not self.is_connected:
            raise BleakError("not connected")

    async def read_gatt_char(self, uuid: str) -> bytearray:
        self._check()
        return bytearray(self.speaker.values[uuid])

    async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
        self._check()
        data = bytes(data)
        self.speaker.writes.append((uuid, data))
        if uuid == SERIAL_TX_UUID:
            if data.startswith(b"aup"):
                accepted = data[3:].decode() == self.speaker.pin
                self.authenticated = self.authenticated or accepted
                answer = b"\x01\x00\x00\x00\x00" if accepted else b"\x02\x00"
                self.callbacks[SERIAL_RX_UUID](None, bytearray(answer))
            return
        if not self.authenticated:
            raise BleakError("ATT error 0x81")
        if uuid == POWER_UUID and self.speaker.drop_on_power_write:
            await self._drop()
            raise BleakError("disconnected")
        self.speaker.values[uuid] = data

    async def start_notify(self, uuid: str, callback: Callable) -> None:
        self._check()
        self.callbacks[uuid] = callback

    async def disconnect(self) -> None:
        await self._drop()

    async def _drop(self) -> None:
        if self.is_connected:
            self.is_connected = False
            if self._disconnected_callback:
                self._disconnected_callback(self)


@pytest.fixture
def fake_speaker() -> Iterator[FakeSpeaker]:
    speaker = FakeSpeaker()

    async def establish_connection(client_class, device, name, disconnected_callback=None, **_):
        if speaker.unreachable:
            raise BleakError("device not found")
        speaker.connect_count += 1
        speaker.client = FakeBleakClient(speaker, disconnected_callback)
        return speaker.client

    with patch("custom_components.soundboks.client.establish_connection", establish_connection):
        yield speaker
