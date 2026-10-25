"""Byte encoding and decoding, no BLE involved."""

import pytest

from custom_components.soundboks.protocol import (
    Input,
    ProtocolError,
    SoundProfile,
    StereoRole,
    auth_accepted,
    auth_command,
    decode_inputs,
    decode_profile,
    decode_stereo,
    decode_volume,
    encode_profile,
    level_to_raw,
    pin_required,
    raw_to_level,
    validate_pin,
)


def test_level_round_trip_edges():
    assert level_to_raw(0.0) == 0
    assert level_to_raw(1.0) == 255
    assert level_to_raw(0.5) == 128
    assert level_to_raw(-0.2) == 0 and level_to_raw(1.7) == 255
    assert raw_to_level(255) == 1.0 and raw_to_level(0) == 0.0


def test_decode_volume():
    assert decode_volume(b"\x2d") == 0x2D
    with pytest.raises(ProtocolError):
        decode_volume(b"")


def test_profile():
    current = bytes([3, 1, 2, 3, 4, 5, 6])
    assert decode_profile(current) is SoundProfile.CUSTOM
    assert encode_profile(current, SoundProfile.BASS_PLUS) == bytes([1, 1, 2, 3, 4, 5, 6])
    with pytest.raises(ValueError):
        encode_profile(current, SoundProfile.CUSTOM)
    with pytest.raises(ProtocolError):
        decode_profile(bytes([9, 0, 0, 0, 0, 0, 0]))
    with pytest.raises(ProtocolError):
        encode_profile(b"\x00", SoundProfile.POWER)  # not 7 bytes


def test_stereo():
    assert decode_stereo(b"\x02") is StereoRole.RIGHT
    with pytest.raises(ProtocolError):
        decode_stereo(b"\x07")


def test_inputs():
    assert decode_inputs(bytes([0, 8 | 4])) == Input.BLUETOOTH | Input.AUX
    assert decode_inputs(bytes([0, 0])) == Input(0)
    assert decode_inputs(bytes([0, 0x80 | 8])) == Input.BLUETOOTH  # unknown bits dropped
    with pytest.raises(ProtocolError):
        decode_inputs(b"\x00")


def test_security_and_pin():
    assert pin_required(b"\x01") and pin_required(b"\x03")
    assert not pin_required(b"\x00") and not pin_required(b"\x02")
    assert validate_pin(" 0042 ") == "0042"
    for bad in ("123", "12345", "12a4", ""):
        with pytest.raises(ValueError):
            validate_pin(bad)
    assert auth_command("1234") == b"aup1234"


def test_auth_accepted():
    assert auth_accepted(b"\x01\x00\x00\x00\x00") is True
    assert auth_accepted(b"\x02\x00") is False
    with pytest.raises(ProtocolError):
        auth_accepted(b"\x00")
