"""Tests for the Docker disk I/O monitor."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from typer.testing import CliRunner

SCRIPT_PATH = Path(__file__).parents[2] / "docker" / "python" / "docker_io.py"
SPEC = importlib.util.spec_from_file_location("docker_io", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
docker_io = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = docker_io
SPEC.loader.exec_module(docker_io)
RUNNER = CliRunner()


def test_value_classes_are_frozen_pydantic_models() -> None:
    """Use immutable Pydantic models for monitored values."""
    sample = docker_io.Sample(timestamp=0.0, read_bytes=100, write_bytes=200)

    assert isinstance(sample, BaseModel)
    with pytest.raises(ValidationError, match="frozen_instance"):
        sample.read_bytes = 300


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0B", 0),
        ("1.5 kB", 1_500),
        ("2MB", 2_000_000),
        ("1 KiB", 1_024),
        ("1.5MiB", 1_572_864),
        ("2 GB", 2_000_000_000),
    ],
)
def test_parse_byte_value(text: str, expected: int) -> None:
    """Parse Docker's decimal and binary byte units."""
    assert docker_io.parse_byte_value(text) == expected


def test_parse_block_io() -> None:
    """Split valid Docker block I/O counters."""
    assert docker_io.parse_block_io("1.2MB / 350kB") == (1_200_000, 350_000)


@pytest.mark.parametrize("text", ["-- / --", "unknown", "1 MB"])
def test_parse_block_io_rejects_invalid_values(text: str) -> None:
    """Reject unavailable or incomplete block I/O values."""
    with pytest.raises(ValueError, match="invalid"):
        docker_io.parse_block_io(text)


def test_render_sparkline_has_fixed_width() -> None:
    """Keep graph width stable while history fills and after it overflows."""
    short = docker_io.render_sparkline([0.0, 5.0, 10.0], 10)
    long = docker_io.render_sparkline([float(value) for value in range(20)], 10)

    assert len(short) == 10
    assert short.endswith("▁▅█")
    assert len(long) == 10


def test_table_columns_have_fixed_widths() -> None:
    """Keep table rows stable regardless of container names and rate values."""
    monitor = docker_io.IoMonitor(window=1.0, interval=1.0)
    monitor.update(
        [
            docker_io.ContainerIoStats(
                container_id="abcdef1234567890",
                name="a-container-name-that-is-longer-than-the-column",
                read_bytes=0,
                write_bytes=0,
            )
        ],
        0.0,
    )
    monitor.update(
        [
            docker_io.ContainerIoStats(
                container_id="abcdef1234567890",
                name="a-container-name-that-is-longer-than-the-column",
                read_bytes=10**15,
                write_bytes=10**15,
            )
        ],
        1.0,
    )

    table_lines = monitor.render().splitlines()[1:4]
    expected_width = sum(column[1] for column in docker_io.TABLE_COLUMNS) + 2 * (
        len(docker_io.TABLE_COLUMNS) - 1
    )

    assert all(len(line) == expected_width for line in table_lines)
    assert "a-container-name-that..." in table_lines[-1]


def test_calculate_rate_uses_narrowest_span_at_least_window() -> None:
    """Use the shortest available span that covers the minimum window."""
    samples = [
        docker_io.Sample(timestamp=0.0, read_bytes=100, write_bytes=200),
        docker_io.Sample(timestamp=4.0, read_bytes=500, write_bytes=1_000),
        docker_io.Sample(timestamp=6.0, read_bytes=1_100, write_bytes=2_000),
        docker_io.Sample(timestamp=10.0, read_bytes=2_100, write_bytes=4_000),
    ]

    rate = docker_io.calculate_rate(samples, 5.0)

    assert rate is not None
    assert rate.span == 6.0
    assert rate.read_bytes_per_second == pytest.approx(1_600 / 6)
    assert rate.write_bytes_per_second == pytest.approx(3_000 / 6)


def test_calculate_rate_needs_full_window() -> None:
    """Return no rate before the requested window has elapsed."""
    samples = [
        docker_io.Sample(timestamp=0.0, read_bytes=100, write_bytes=200),
        docker_io.Sample(timestamp=4.9, read_bytes=500, write_bytes=1_000),
    ]
    assert docker_io.calculate_rate(samples, 5.0) is None


def test_calculate_rate_rejects_counter_reset() -> None:
    """Do not report negative rates after a cumulative counter reset."""
    samples = [
        docker_io.Sample(timestamp=0.0, read_bytes=500, write_bytes=1_000),
        docker_io.Sample(timestamp=5.0, read_bytes=100, write_bytes=2_000),
    ]
    assert docker_io.calculate_rate(samples, 5.0) is None


def test_monitor_update_clears_counter_reset() -> None:
    """Restart history when either cumulative counter decreases."""
    monitor = docker_io.IoMonitor(window=5.0, interval=1.0)
    monitor.histories = {
        "abc": docker_io.deque(
            [docker_io.Sample(timestamp=0.0, read_bytes=500, write_bytes=1_000)]
        )
    }
    containers = [
        docker_io.ContainerIoStats(
            container_id="abc", name="web", read_bytes=100, write_bytes=200
        )
    ]

    monitor.update(containers, 5.0)

    assert list(monitor.histories["abc"]) == [
        docker_io.Sample(timestamp=5.0, read_bytes=100, write_bytes=200)
    ]


def test_monitor_owns_rate_and_render_state() -> None:
    """Calculate and render rates from state owned by the monitor."""
    monitor = docker_io.IoMonitor(window=5.0, interval=1.0)
    containers = [
        docker_io.ContainerIoStats(
            container_id="abc123", name="web", read_bytes=100, write_bytes=200
        )
    ]
    monitor.update(containers, 0.0)
    monitor.update(
        [
            docker_io.ContainerIoStats(
                container_id="abc123", name="web", read_bytes=600, write_bytes=1_200
            )
        ],
        5.0,
    )
    monitor.last_refresh = datetime(2026, 9, 29, 12, 34, 56, tzinfo=timezone.utc)

    assert monitor.is_complete()
    assert monitor.rate_for("abc123") == docker_io.Rate(
        read_bytes_per_second=100.0,
        write_bytes_per_second=200.0,
        span=5.0,
    )
    assert "100.0 B/s" in monitor.render()
    assert "200.0 B/s" in monitor.render()
    assert "Overall: READ 100.0 B/s | WRITE 200.0 B/s" in monitor.render()
    assert "READ total 600.0 B | WRITE total 1.2 KiB" in monitor.render()
    assert "Last refresh: 2026-09-29 12:34:56 UTC" in monitor.render()
    assert "I/O history (0s, 1/60 samples)" in monitor.render()
    assert "now 100.0 B/s  peak 100.0 B/s" in monitor.render()


def test_monitor_bounds_io_history() -> None:
    """Retain no more aggregate graph points than the configured width."""
    monitor = docker_io.IoMonitor(window=1.0, interval=1.0, graph_width=3)

    for timestamp in range(5):
        monitor.update(
            [
                docker_io.ContainerIoStats(
                    container_id="abc",
                    name="web",
                    read_bytes=timestamp * 100,
                    write_bytes=timestamp * 200,
                )
            ],
            float(timestamp),
        )

    assert len(monitor.io_history) == 3
    assert monitor.io_history[0].timestamp == 2.0
    assert monitor.io_history[-1].timestamp == 4.0


def test_typer_help_lists_monitor_options() -> None:
    """Expose all monitor controls through the Typer command."""
    result = RUNNER.invoke(docker_io.app, ["--help"])

    assert result.exit_code == 0
    assert "--window" in result.stdout
    assert "--interval" in result.stdout
    assert "--all" in result.stdout
    assert "--once" in result.stdout
    assert "--no-clear" in result.stdout
    assert "--graph-width" in result.stdout


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--window", "0.5"], "must be at least"),
        (["--window", "nan"], "must be at least"),
        (["--interval", "0.1"], "must be at least"),
        (["--interval", "inf"], "must be at least"),
        (["--graph-width", "9"], "must be between 10 and 200"),
        (["--graph-width", "201"], "must be between 10 and 200"),
    ],
)
def test_typer_rejects_invalid_ranges(arguments: list[str], message: str) -> None:
    """Reject non-finite values and values below the documented limits."""
    result = RUNNER.invoke(docker_io.app, arguments)

    assert result.exit_code == 2
    assert message in result.output
