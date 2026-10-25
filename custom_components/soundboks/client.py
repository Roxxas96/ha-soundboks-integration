"""The BLE connection to one speaker.

The speaker takes a single connection at a time, so the client never holds one for long: a command
keeps the link for an idle window (a burst of volume changes reuses it), anything else that opened
the link closes it straight away. One lock runs every operation in turn.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .protocol import (
    AUTO_BOOT_ONCE,
    FIRMWARE_UUID,
    INPUTS_UUID,
    MAX_RAW_VOLUME,
    POWER_OFF,
    POWER_UUID,
    PROFILE_UUID,
    REQUIRED_UUIDS,
    SECURITY_UUID,
    SERIAL_RX_UUID,
    SERIAL_TX_UUID,
    STEREO_UUID,
    VOLUME_UUID,
    InvalidPinError,
    PinRequiredError,
    ProtocolError,
    SoundProfile,
    SpeakerState,
    SpeakerUnreachableError,
    StereoRole,
    UnsupportedSpeakerError,
    auth_accepted,
    auth_command,
    decode_inputs,
    decode_profile,
    decode_stereo,
    decode_volume,
    encode_profile,
    pin_required,
)

_LOGGER = logging.getLogger(__name__)

UNREACHABLE_MESSAGE = (
    "Could not reach the speaker: it may be off, out of range, or another app may be connected"
)
CONNECT_ATTEMPTS = 2  # fail fast: the next poll retries anyway
RESPONSE_TIMEOUT = 5.0
LINK_ERRORS = (BleakError, TimeoutError)


class SoundboksClient:
    def __init__(
        self,
        ble_device: BLEDevice | None,
        pin: str | None,
        *,
        idle_timeout: float = 30.0,
        on_volume: Callable[[int], None] | None = None,
    ) -> None:
        self._ble_device = ble_device
        self._pin = pin
        self._idle_timeout = idle_timeout
        self._on_volume = on_volume
        self._lock = asyncio.Lock()
        self._client: BleakClient | None = None
        self._authenticated = False
        self._responses: asyncio.Queue[bytes] = asyncio.Queue()
        self._idle_handle: asyncio.TimerHandle | None = None
        self._idle_task: asyncio.Task | None = None

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """The latest device seen advertising, used for the next connection."""
        self._ble_device = ble_device

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def check_supported(self) -> None:
        async def check(client: BleakClient) -> None:
            if any(client.services.get_characteristic(uuid) is None for uuid in REQUIRED_UUIDS):
                raise UnsupportedSpeakerError("this speaker model is not supported")

        await self._run(check, command=False, authenticate=False)

    async def pin_required(self) -> bool:
        async def read(client: BleakClient) -> bool:
            return pin_required(await self._read(client, SECURITY_UUID))

        return await self._run(read, command=False, authenticate=False)

    async def verify_pin(self, pin: str) -> None:
        """Authenticate with pin; on success it becomes the client's PIN."""

        async def verify(client: BleakClient) -> None:
            await self._authenticate(client, pin)
            self._pin = pin

        await self._run(verify, command=True, authenticate=False)

    async def read_firmware(self) -> str:
        async def read(client: BleakClient) -> str:
            return (await self._read(client, FIRMWARE_UUID)).decode(errors="replace").strip()

        return await self._run(read, command=False, authenticate=False)

    async def read_state(self) -> SpeakerState:
        async def read(client: BleakClient) -> SpeakerState:
            return SpeakerState(
                volume=decode_volume(await self._read(client, VOLUME_UUID)),
                profile=decode_profile(await self._read(client, PROFILE_UUID)),
                stereo=decode_stereo(await self._read(client, STEREO_UUID)),
                inputs=decode_inputs(await self._read(client, INPUTS_UUID)),
            )

        return await self._run(read, command=False)

    async def set_volume(self, raw: int) -> None:
        if not 0 <= raw <= MAX_RAW_VOLUME:
            raise ValueError(f"volume {raw} is outside 0-{MAX_RAW_VOLUME}")
        await self._write(VOLUME_UUID, bytes([raw]))

    async def set_profile(self, profile: SoundProfile) -> None:
        async def write(client: BleakClient) -> None:
            current = await self._read(client, PROFILE_UUID)
            await client.write_gatt_char(
                PROFILE_UUID, encode_profile(current, profile), response=True
            )

        await self._run(write, command=True)

    async def set_stereo(self, role: StereoRole) -> None:
        await self._write(STEREO_UUID, bytes([role]))

    async def power_off(self) -> None:
        await self._run(self._power_write(POWER_OFF), command=False)

    async def reboot(self) -> None:
        """Auto-boot once, then power off: the speaker restarts by itself."""
        await self._run(self._power_write(AUTO_BOOT_ONCE), command=False)
        await self.power_off()

    async def disconnect(self) -> None:
        async with self._lock:
            await self._drop()

    def _power_write(self, data: bytes) -> Callable[[BleakClient], Awaitable[None]]:
        async def write(client: BleakClient) -> None:
            # The speaker never answers a power write: it drops the link, which means it worked
            try:
                await client.write_gatt_char(POWER_UUID, data, response=True)
            except LINK_ERRORS:
                _LOGGER.debug("Link dropped after power write %s, as expected", data.hex())
            await self._drop()

        return write

    async def _write(self, uuid: str, data: bytes) -> None:
        async def write(client: BleakClient) -> None:
            await client.write_gatt_char(uuid, data, response=True)

        await self._run(write, command=True)

    async def _run[T](
        self,
        operation: Callable[[BleakClient], Awaitable[T]],
        *,
        command: bool,
        authenticate: bool = True,
    ) -> T:
        """Run operation on the link, connecting first if needed.

        A command (re)starts the idle window. Anything else closes a link it opened, and leaves
        the idle window of an existing one alone, so polls never keep the speaker busy.
        """
        async with self._lock:
            opened = not self.is_connected
            if command:
                self._cancel_idle()
            try:
                client = await self._connect()
                if authenticate:
                    await self._ensure_authenticated(client)
                result = await operation(client)
            except LINK_ERRORS as err:
                await self._drop()
                raise SpeakerUnreachableError(UNREACHABLE_MESSAGE) from err
            except BaseException:
                await self._drop()
                raise
            if command and self.is_connected:
                self._arm_idle()
            elif opened:
                await self._drop()
            return result

    async def _connect(self) -> BleakClient:
        if self._client is not None and self._client.is_connected:
            return self._client
        if self._ble_device is None:
            raise SpeakerUnreachableError(UNREACHABLE_MESSAGE)
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                self._ble_device,
                self._ble_device.name or self._ble_device.address,
                disconnected_callback=self._on_disconnected,
                max_attempts=CONNECT_ATTEMPTS,
            )
        except LINK_ERRORS as err:
            raise SpeakerUnreachableError(UNREACHABLE_MESSAGE) from err
        self._client = client
        self._authenticated = False
        self._responses = asyncio.Queue()
        # Keep this subscription for the link's lifetime: unsubscribing drops the authentication
        await client.start_notify(SERIAL_RX_UUID, self._on_response)
        if self._on_volume is not None:
            await client.start_notify(VOLUME_UUID, self._on_volume_notification)
        return client

    async def _ensure_authenticated(self, client: BleakClient) -> None:
        if self._authenticated:
            return
        if pin_required(await self._read(client, SECURITY_UUID)):
            if not self._pin:
                raise PinRequiredError("the speaker has a PIN")
            await self._authenticate(client, self._pin)
        self._authenticated = True

    async def _authenticate(self, client: BleakClient, pin: str) -> None:
        while not self._responses.empty():
            self._responses.get_nowait()
        await client.write_gatt_char(SERIAL_TX_UUID, auth_command(pin), response=True)
        answer = await asyncio.wait_for(self._responses.get(), RESPONSE_TIMEOUT)
        if not auth_accepted(answer):
            raise InvalidPinError("the speaker refused the PIN")
        self._authenticated = True

    @staticmethod
    async def _read(client: BleakClient, uuid: str) -> bytes:
        return bytes(await client.read_gatt_char(uuid))

    def _on_response(self, _sender: object, data: bytearray) -> None:
        self._responses.put_nowait(bytes(data))

    def _on_volume_notification(self, _sender: object, data: bytearray) -> None:
        try:
            raw = decode_volume(bytes(data))
        except ProtocolError:
            _LOGGER.debug("Ignoring volume notification %s", bytes(data).hex())
            return
        if self._on_volume is not None:
            self._on_volume(raw)

    def _on_disconnected(self, client: BleakClient) -> None:
        if client is self._client:
            self._client = None
            self._cancel_idle()

    def _arm_idle(self) -> None:
        self._cancel_idle()
        loop = asyncio.get_running_loop()
        self._idle_handle = loop.call_later(self._idle_timeout, self._idle_expired)

    def _cancel_idle(self) -> None:
        if self._idle_handle is not None:
            self._idle_handle.cancel()
            self._idle_handle = None

    def _idle_expired(self) -> None:
        self._idle_handle = None
        self._idle_task = asyncio.create_task(self.disconnect())

    async def _drop(self) -> None:
        self._cancel_idle()
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.disconnect()
            except LINK_ERRORS:
                _LOGGER.debug("Error while disconnecting", exc_info=True)
