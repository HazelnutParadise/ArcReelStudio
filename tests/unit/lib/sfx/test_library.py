"""音效库的形态：解析、增益折算与峰值汇总解析。"""

from __future__ import annotations

import pytest

from lib.sfx.library import MAX_GAIN_DB, peak_gain_db, read_sfx_library
from lib.sfx.peak import PeakMeasurementError, parse_peak


def _entry(**overrides: object) -> dict[str, object]:
    return {
        "name": "关门",
        "file": "sfx/sfx-0000abcd.wav",
        "duration_us": 500_000,
        "peak_dbfs": -6.0,
        "gain_db": 5.0,
        "content_digest": "sha256:x",
        "added_at": "2026-11-10T00:00:00Z",
        **overrides,
    }


def test_malformed_entries_are_left_out() -> None:
    project = {
        "sfx": {
            "sfx-0000abcd": _entry(),
            "sfx-bad": _entry(),
            "sfx-0000ffff": _entry(file="other/sfx-0000ffff.wav"),
            "sfx-00001111": "not a mapping",
        }
    }

    assert list(read_sfx_library(project)) == ["sfx-0000abcd"]


def test_gain_brings_the_peak_to_target_but_is_capped() -> None:
    assert peak_gain_db(-6.0) == 5.0
    assert peak_gain_db(-50.0) == MAX_GAIN_DB


@pytest.mark.parametrize(("line", "peak"), [("max_volume: -3.2 dB", -3.2), ("max_volume: -inf dB", float("-inf"))])
def test_peak_is_read_from_volumedetect(line: str, peak: float) -> None:
    assert (
        parse_peak(f"[Parsed_volumedetect_0 @ 0x1] mean_volume: -20.0 dB\n[Parsed_volumedetect_0 @ 0x1] {line}\n")
        == peak
    )


def test_missing_summary_is_an_error() -> None:
    with pytest.raises(PeakMeasurementError):
        parse_peak("no summary here")
