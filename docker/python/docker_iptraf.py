#!/usr/bin/env python3
#===============================================================================
#
# Script Name: docker_iptraf.py
# Title: Docker container network traffic
# Tags: Docker, Networking, Monitoring
# Purpose: Shows per-container RX and TX rates over a recent sample window.
#
# Description:
#   Polls cumulative network counters from the Docker CLI and displays per-
#   container receive and transmit rates measured across at least the requested
#   number of seconds.
#
# Parameters:
#   --window SECONDS   Minimum elapsed time used to calculate rates (default: 5)
#   --interval SECONDS Polling interval in seconds (default: 1)
#   --all              Include stopped containers reported by Docker
#   --once             Print one complete measurement and exit
#   --no-clear         Do not clear the terminal between updates
#   --graph-width N    Number of throughput samples shown (default: 60)
#
# Required Privileges:
#   - Permission to run the Docker CLI and access the Docker daemon
#
# Required Dependencies:
#   - Pydantic 2.0 or newer
#   - Rich 14.0 or newer
#   - Typer 0.27.2 or newer
#
# Output Format:
#   - Terminal table containing container identity, RX/TX rates, cumulative
#     counters, and the elapsed sample span
#
# Example Usage:
#   python docker_iptraf.py
#   python docker_iptraf.py --window 10 --interval 2
#   python docker_iptraf.py --window 2 --interval 1 --once
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
"""Monitor per-container Docker network traffic from cumulative counters.

Docker exposes cumulative network byte counters rather than instantaneous rates.
This module periodically samples those counters and calculates receive and
transmit rates across the shortest available interval that is at least as long
as the requested measurement window.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from typing import Annotated, Sequence

import typer
from pydantic import BaseModel, ConfigDict
from rich.console import Console
from rich.live import Live
from rich.text import Text

app = typer.Typer(
    add_completion=False,
    help=__doc__,
    no_args_is_help=False,
    pretty_exceptions_show_locals=False,
)

# Docker normally emits decimal SI units, but the parser also accepts binary IEC
# units so recorded output and future Docker formats can use either convention.
BYTE_UNITS = {
    "b": 1,
    "kb": 1_000,
    "mb": 1_000_000,
    "gb": 1_000_000_000,
    "tb": 1_000_000_000_000,
    "kib": 1 << 10,
    "mib": 1 << 20,
    "gib": 1 << 30,
    "tib": 1 << 40,
}
BYTE_VALUE_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*([kmgt]?i?b)$", re.IGNORECASE)
SPARKLINE_LEVELS = "▁▂▃▄▅▆▇█"


class DockerStatsError(RuntimeError):
    """Indicate that Docker statistics could not be collected or interpreted."""


class FrozenModel(BaseModel):
    """Provide an immutable Pydantic base for traffic-monitor value objects.

    Attributes:
        model_config (ConfigDict): Pydantic configuration that prevents model
            fields from being changed after validation.
    """

    model_config = ConfigDict(frozen=True)


class ContainerStats(FrozenModel):
    """Represent cumulative network counters for one Docker container.

    Attributes:
        container_id (str): Stable Docker container identifier.
        name (str): Human-readable Docker container name.
        rx_bytes (int | None): Total received bytes, or ``None`` when Docker
            does not expose a usable counter.
        tx_bytes (int | None): Total transmitted bytes, or ``None`` when Docker
            does not expose a usable counter.
    """

    container_id: str
    name: str
    rx_bytes: int | None
    tx_bytes: int | None


class Sample(FrozenModel):
    """Represent cumulative counters captured at a monotonic timestamp.

    Attributes:
        timestamp (float): Monotonic time in seconds when the counters were read.
        rx_bytes (int): Cumulative received-byte counter.
        tx_bytes (int): Cumulative transmitted-byte counter.
    """

    timestamp: float
    rx_bytes: int
    tx_bytes: int


class Rate(FrozenModel):
    """Represent calculated network rates and their measurement span.

    Attributes:
        rx_bytes_per_second (float): Average receive rate during ``span``.
        tx_bytes_per_second (float): Average transmit rate during ``span``.
        span (float): Elapsed seconds between the samples used for the rate.
    """

    rx_bytes_per_second: float
    tx_bytes_per_second: float
    span: float


class ThroughputPoint(FrozenModel):
    """Represent one aggregate throughput point in the rolling graph.

    Attributes:
        timestamp (float): Monotonic time associated with the aggregate rates.
        rx_bytes_per_second (float): Combined receive rate for all containers.
        tx_bytes_per_second (float): Combined transmit rate for all containers.
    """

    timestamp: float
    rx_bytes_per_second: float
    tx_bytes_per_second: float


def validate_minimum(value: float, minimum: float) -> float:
    """Validate that a CLI floating-point value is finite and large enough.

    Args:
        value (float): Parsed command-line value to validate.
        minimum (float): Smallest accepted value, inclusive.

    Returns:
        float: The unchanged validated value.

    Raises:
        typer.BadParameter: If ``value`` is non-finite or below ``minimum``.
    """
    if not math.isfinite(value) or value < minimum:
        raise typer.BadParameter(f"must be at least {minimum:g}")
    return value


def validate_window(value: float) -> float:
    """Validate the rate-window command-line option.

    Args:
        value (float): Requested measurement window in seconds.

    Returns:
        float: The validated window, which is at least one second.

    Raises:
        typer.BadParameter: If ``value`` is non-finite or less than one.
    """
    return validate_minimum(value, 1.0)


def validate_interval(value: float) -> float:
    """Validate the polling-interval command-line option.

    Args:
        value (float): Requested delay between Docker polls in seconds.

    Returns:
        float: The validated interval, which is at least 0.2 seconds.

    Raises:
        typer.BadParameter: If ``value`` is non-finite or less than 0.2.
    """
    return validate_minimum(value, 0.2)


def validate_graph_width(value: int) -> int:
    """Validate the throughput graph width command-line option.

    Args:
        value (int): Requested number of samples displayed in each sparkline.

    Returns:
        int: The validated width between 10 and 200 characters, inclusive.

    Raises:
        typer.BadParameter: If ``value`` is outside the supported range.
    """
    if not 10 <= value <= 200:
        raise typer.BadParameter("must be between 10 and 200")
    return value


def parse_byte_value(value: str) -> int:
    """Convert a human-readable Docker byte value to an integer byte count.

    Args:
        value (str): Number and unit such as ``1.2MB`` or ``3 MiB``.

    Returns:
        int: Byte count truncated to a whole byte.

    Raises:
        ValueError: If the value has no recognized number and byte unit.
    """
    match = BYTE_VALUE_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"invalid byte value: {value!r}")
    amount, unit = match.groups()
    return int(float(amount) * BYTE_UNITS[unit.lower()])


def parse_net_io(value: str) -> tuple[int, int]:
    """Parse Docker's ``RX / TX`` network counter representation.

    Args:
        value (str): Network counters in Docker's ``received / transmitted`` display format.

    Returns:
        tuple[int, int]: Received bytes followed by transmitted bytes.

    Raises:
        ValueError: If the value is not exactly two valid byte quantities.
    """
    # Splitting on the separator first produces clearer validation for stopped
    # containers, which Docker can represent as "-- / --".
    parts = value.split("/")
    if len(parts) != 2:
        raise ValueError(f"invalid NetIO value: {value!r}")
    return parse_byte_value(parts[0]), parse_byte_value(parts[1])


def calculate_rate(samples: Sequence[Sample], window: float) -> Rate | None:
    """Calculate rates over the narrowest sample span covering a window.

    Args:
        samples (Sequence[Sample]): Chronologically ordered cumulative counters.
        window (float): Minimum elapsed seconds required between samples.

    Returns:
        Rate | None: Calculated RX/TX rates, or ``None`` when the history has not
            reached the window or the counters cannot produce a valid rate.
    """
    if len(samples) < 2:
        return None

    # Start at the newest sample and walk backward. The first qualifying sample
    # gives the narrowest elapsed span that is still at least `window` seconds.
    # This works for both lists and deques because it does not slice the input.
    reverse_samples = reversed(samples)
    newest = next(reverse_samples)
    oldest = next(
        (sample for sample in reverse_samples if newest.timestamp - sample.timestamp >= window),
        None,
    )
    if oldest is None:
        return None

    # Cumulative counter deltas divided by elapsed monotonic time produce an
    # average rate that is unaffected by wall-clock adjustments.
    span = newest.timestamp - oldest.timestamp
    rx_delta = newest.rx_bytes - oldest.rx_bytes
    tx_delta = newest.tx_bytes - oldest.tx_bytes
    # A negative delta means Docker reset a counter, normally after a container
    # restart. Suppress that measurement instead of displaying a negative rate.
    if span <= 0 or rx_delta < 0 or tx_delta < 0:
        return None
    return Rate(
        rx_bytes_per_second=rx_delta / span,
        tx_bytes_per_second=tx_delta / span,
        span=span,
    )


def collect_stats(include_all: bool) -> tuple[list[ContainerStats], int]:
    """Collect and validate one snapshot from ``docker stats``.

    Args:
        include_all (bool): Whether Docker should include stopped containers.

    Returns:
        tuple[list[ContainerStats], int]: Parsed container records and the number
            of malformed output lines that were ignored.

    Raises:
        DockerStatsError: If Docker is missing, exits unsuccessfully, or returns
            no recognizable records despite producing output.
    """
    # JSON-lines output avoids parsing Docker's padded, human-oriented table.
    # Disabling the continuous stream yields a single instantaneous snapshot.
    command = ["docker", "stats", "--no-stream", "--format", "{{json .}}"]
    if include_all:
        command.insert(2, "--all")

    # Run the Docker CLI synchronously and capture raw output streams.
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise DockerStatsError("Docker CLI was not found in PATH.") from exc

    # Handle nonzero exit statuses by extracting detailed daemon or CLI diagnostics.
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Docker error"
        raise DockerStatsError(f"Unable to read Docker statistics: {detail}")

    containers: list[ContainerStats] = []
    malformed = 0
    # Process each emitted JSON object corresponding to a container's current stats.
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            container_id = str(record["ID"])
            name = str(record.get("Name") or container_id)
            # Stopped containers commonly have unavailable network values. Keep
            # those containers visible while marking their counters unavailable.
            try:
                rx_bytes, tx_bytes = parse_net_io(str(record["NetIO"]))
            except (KeyError, ValueError):
                rx_bytes, tx_bytes = None, None
            containers.append(
                ContainerStats(
                    container_id=container_id,
                    name=name,
                    rx_bytes=rx_bytes,
                    tx_bytes=tx_bytes,
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            # Track corrupted or unrecognized output lines without aborting valid entries.
            malformed += 1

    # If parsing completely failed across all records, assume an incompatible output format.
    if malformed and not containers:
        raise DockerStatsError("Docker returned statistics in an unrecognized format.")
    return containers, malformed


def format_bytes(value: float) -> str:
    """Format a byte count or byte rate using a compact binary unit.

    Args:
        value (float): Number of bytes to format.

    Returns:
        str: Value rounded to one decimal place with a B-through-TiB suffix.
    """
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    # Iteratively scale down by powers of 1024 until the value fits within the unit threshold.
    for unit in units[:-1]:
        if abs(amount) < 1024:
            return f"{amount:.1f} {unit}"
        amount /= 1024
    # Fall back to the largest unit if the value exceeds all intermediate thresholds.
    return f"{amount:.1f} {units[-1]}"


def render_sparkline(values: Sequence[float], width: int) -> str:
    """Render numeric values as a right-aligned, fixed-width sparkline.

    Args:
        values (Sequence[float]): Chronological non-negative throughput values.
        width (int): Exact number of terminal columns to return.

    Returns:
        str: A fixed-width graph padded on the left while history fills.
    """
    visible = list(values[-width:])
    if not visible:
        return " " * width

    peak = max(visible)
    if peak <= 0:
        graph = SPARKLINE_LEVELS[0] * len(visible)
    else:
        highest_level = len(SPARKLINE_LEVELS) - 1
        graph = "".join(
            SPARKLINE_LEVELS[round((value / peak) * highest_level)] for value in visible
        )
    return graph.rjust(width)


class TrafficMonitor:
    """Own Docker traffic samples, display state, and the polling lifecycle.

    Attributes:
        window (float): Minimum seconds spanned by each calculated rate.
        interval (float): Seconds to wait between Docker polls.
        include_all (bool): Whether to request stopped containers from Docker.
        once (bool): Whether to exit after the first complete measurement.
        clear_screen (bool): Whether to clear an interactive terminal on refresh.
        graph_width (int): Maximum samples displayed in each throughput graph.
        histories (dict[str, deque[Sample]]): Samples keyed by container ID.
        throughput_history (deque[ThroughputPoint]): Bounded aggregate rates.
        containers (list[ContainerStats]): Container records from the latest poll.
        malformed_lines (int): Invalid Docker output lines in the latest poll.
        last_refresh (datetime | None): Local time of the latest completed poll.
        first_render (bool): Whether the monitor has yet to render output.
    """

    def __init__(
        self,
        window: float,
        interval: float,
        include_all: bool = False,
        once: bool = False,
        clear_screen: bool = True,
        graph_width: int = 60,
    ) -> None:
        """Initialize monitor configuration and empty runtime state.

        Args:
            window (float): Minimum seconds required for rate calculation.
            interval (float): Seconds to wait between Docker polls.
            include_all (bool): Include stopped containers when ``True``.
            once (bool): Stop after one complete measurement when ``True``.
            clear_screen (bool): Clear interactive output before refreshes when
                ``True``.
            graph_width (int): Number of aggregate samples retained and graphed.
        """
        self.window = window
        self.interval = interval
        self.include_all = include_all
        self.once = once
        self.clear_screen = clear_screen
        self.graph_width = graph_width
        self.histories: dict[str, deque[Sample]] = {}
        self.throughput_history: deque[ThroughputPoint] = deque(maxlen=graph_width)
        self.containers: list[ContainerStats] = []
        self.malformed_lines = 0
        self.last_refresh: datetime | None = None
        self.first_render = True

    def poll(self, timestamp: float | None = None) -> None:
        """Collect current counters and update each container's sample history.

        Args:
            timestamp (float | None): Optional monotonic timestamp for the sample.
                Primarily useful for deterministic tests. The current monotonic
                time is used when omitted.

        Raises:
            DockerStatsError: If Docker statistics cannot be collected.
        """
        self.containers, self.malformed_lines = collect_stats(self.include_all)
        self.update(self.containers, time.monotonic() if timestamp is None else timestamp)
        # Record wall-clock time only after collection and state updates finish,
        # so the displayed value describes the snapshot currently on screen.
        self.last_refresh = datetime.now().astimezone()

    def update(self, containers: Sequence[ContainerStats], timestamp: float) -> None:
        """Update histories and retain the closest sample spanning the window.

        Args:
            containers (Sequence[ContainerStats]): Container counters in the
                newest Docker snapshot.
            timestamp (float): Monotonic timestamp shared by the snapshot.
        """
        self.containers = list(containers)

        # Remove histories for containers that disappeared so reused IDs and
        # long-running sessions do not retain stale data indefinitely.
        active_ids = {container.container_id for container in containers}
        for stale_id in self.histories.keys() - active_ids:
            del self.histories[stale_id]

        for container in containers:
            # An unavailable counter cannot contribute to a rate, but the
            # container remains in `self.containers` so render() can show N/A.
            if container.rx_bytes is None or container.tx_bytes is None:
                continue
            history = self.histories.setdefault(container.container_id, deque())

            # Cumulative counters should only increase. A decrease indicates a
            # reset or restart, so begin a fresh measurement window.
            if history and (
                container.rx_bytes < history[-1].rx_bytes
                or container.tx_bytes < history[-1].tx_bytes
            ):
                history.clear()
            history.append(
                Sample(timestamp=timestamp, rx_bytes=container.rx_bytes, tx_bytes=container.tx_bytes)
            )

            # Keep exactly one sample at or before the target boundary, plus all
            # newer samples. That sample is needed to guarantee a span of at
            # least `window` while bounding memory use during continuous runs.
            while len(history) >= 2 and timestamp - history[1].timestamp >= self.window:
                history.popleft()

        # Add one aggregate point only when all measurable containers have a
        # complete rate. This keeps the graph from depicting partial warm-up data.
        aggregate_rate = self.aggregate_rate()
        if aggregate_rate is not None:
            rx_rate, tx_rate = aggregate_rate
            self.throughput_history.append(
                ThroughputPoint(
                    timestamp=timestamp,
                    rx_bytes_per_second=rx_rate,
                    tx_bytes_per_second=tx_rate,
                )
            )

    def rate_for(self, container_id: str) -> Rate | None:
        """Return the current rate for a container when its window is ready.

        Args:
            container_id (str): Docker container ID used as the history key.

        Returns:
            Rate | None: Current rate, or ``None`` while history is insufficient.
        """
        return calculate_rate(self.histories.get(container_id, ()), self.window)

    def is_complete(self) -> bool:
        """Return whether every measurable container has a complete window.

        Returns:
            bool: ``True`` when each container with valid counters has a rate.
                A snapshot containing only unavailable counters is also complete.
        """
        measurable_ids = [
            container.container_id
            for container in self.containers
            if container.rx_bytes is not None and container.tx_bytes is not None
        ]
        return all(self.rate_for(container_id) is not None for container_id in measurable_ids)

    def aggregate_rate(self) -> tuple[float, float] | None:
        """Calculate complete aggregate receive and transmit rates.

        Returns:
            tuple[float, float] | None: Combined RX and TX bytes per second, or
                ``None`` if no measurable container exists or any rate is still
                warming up.
        """
        measurable_ids = [
            container.container_id
            for container in self.containers
            if container.rx_bytes is not None and container.tx_bytes is not None
        ]
        if not measurable_ids:
            return None

        rates = [self.rate_for(container_id) for container_id in measurable_ids]
        if any(rate is None for rate in rates):
            return None

        complete_rates = [rate for rate in rates if rate is not None]
        return (
            sum(rate.rx_bytes_per_second for rate in complete_rates),
            sum(rate.tx_bytes_per_second for rate in complete_rates),
        )

    def render(self) -> str:
        """Render the current snapshot as a fixed-width terminal table.

        Returns:
            str: Complete display text for the latest snapshot.
        """
        headers = ("CONTAINER", "ID", "RX/s", "TX/s", "RX TOTAL", "TX TOTAL", "SPAN")
        rows: list[tuple[str, ...]] = []

        # Sort by the user-facing name to keep row order stable between polls.
        for container in sorted(self.containers, key=lambda item: item.name.lower()):
            if container.rx_bytes is None or container.tx_bytes is None:
                rx_rate = tx_rate = rx_total = tx_total = span = "N/A"
            else:
                rate = self.rate_for(container.container_id)
                rx_total = format_bytes(container.rx_bytes)
                tx_total = format_bytes(container.tx_bytes)
                if rate is None:
                    # During warm-up, expose progress toward the minimum window
                    # rather than showing a misleading zero rate.
                    rx_rate = tx_rate = "warming up"
                    history = self.histories.get(container.container_id)
                    elapsed = history[-1].timestamp - history[0].timestamp if history else 0.0
                    span = f"{elapsed:.1f}s/{self.window:g}s"
                else:
                    rx_rate = f"{format_bytes(rate.rx_bytes_per_second)}/s"
                    tx_rate = f"{format_bytes(rate.tx_bytes_per_second)}/s"
                    span = f"{rate.span:.1f}s"
            rows.append(
                (
                    container.name,
                    container.container_id[:12],
                    rx_rate,
                    tx_rate,
                    rx_total,
                    tx_total,
                    span,
                )
            )

        # Derive each column width from both its heading and current row values.
        # This produces aligned output without a third-party table renderer.
        widths = [len(header) for header in headers]
        for row in rows:
            for index, value in enumerate(row):
                widths[index] = max(widths[index], len(value))

        def line(values: Sequence[str]) -> str:
            return "  ".join(
                value.ljust(widths[index]) for index, value in enumerate(values)
            ).rstrip()

        output = [
            f"Docker network traffic (minimum window: {self.window:g}s)",
            line(headers),
            line(tuple("-" * width for width in widths)),
        ]
        output.extend(line(row) for row in rows)
        if not rows:
            output.append("No containers found.")

        # Aggregate only containers with usable counters. Rate totals remain in
        # warm-up until every such container spans the requested window, which
        # prevents a partial aggregate from looking like a complete measurement.
        measurable = [
            container
            for container in self.containers
            if container.rx_bytes is not None and container.tx_bytes is not None
        ]
        if not measurable:
            rx_rate = tx_rate = rx_total = tx_total = "N/A"
        else:
            rx_total = format_bytes(sum(container.rx_bytes or 0 for container in measurable))
            tx_total = format_bytes(sum(container.tx_bytes or 0 for container in measurable))
            aggregate_rate = self.aggregate_rate()
            if aggregate_rate is None:
                rx_rate = tx_rate = "warming up"
            else:
                aggregate_rx, aggregate_tx = aggregate_rate
                rx_rate = f"{format_bytes(aggregate_rx)}/s"
                tx_rate = f"{format_bytes(aggregate_tx)}/s"

        rx_history = [point.rx_bytes_per_second for point in self.throughput_history]
        tx_history = [point.tx_bytes_per_second for point in self.throughput_history]
        if self.throughput_history:
            history_span = (
                self.throughput_history[-1].timestamp
                - self.throughput_history[0].timestamp
            )
            graph_status = (
                f"{history_span:.0f}s, "
                f"{len(self.throughput_history)}/{self.graph_width} samples"
            )
            rx_now = f"{format_bytes(rx_history[-1])}/s"
            tx_now = f"{format_bytes(tx_history[-1])}/s"
            rx_peak = f"{format_bytes(max(rx_history))}/s"
            tx_peak = f"{format_bytes(max(tx_history))}/s"
        else:
            graph_status = f"collecting, 0/{self.graph_width} samples"
            rx_now = tx_now = rx_peak = tx_peak = "N/A"

        refreshed_at = (
            self.last_refresh.strftime("%Y-%m-%d %H:%M:%S %Z")
            if self.last_refresh is not None
            else "not yet polled"
        )
        output.append("")
        output.append(f"Throughput history ({graph_status})")
        output.append(
            f"RX  {render_sparkline(rx_history, self.graph_width)}  "
            f"now {rx_now}  peak {rx_peak}"
        )
        output.append(
            f"TX  {render_sparkline(tx_history, self.graph_width)}  "
            f"now {tx_now}  peak {tx_peak}"
        )
        output.append("")
        output.append(
            f"Overall: RX {rx_rate} | TX {tx_rate} | "
            f"RX total {rx_total} | TX total {tx_total}"
        )
        output.append(f"Last refresh: {refreshed_at}")
        if self.malformed_lines:
            output.append(
                f"Warning: ignored {self.malformed_lines} malformed Docker stats line(s)."
            )
        return "\n".join(output)

    def run(self) -> int:
        """Poll and display traffic until completion or interruption.

        Returns:
            int: Process-style exit code: zero for normal completion or Ctrl-C,
                and one when Docker cannot be used.
        """
        if shutil.which("docker") is None:
            typer.echo("Error: Docker CLI was not found in PATH.", err=True)
            return 1

        # Rich Live rewrites one display region instead of printing a new graph
        # on every poll. Preserve normal scrolling output when explicitly asked
        # for --no-clear or when stdout is redirected to a file or pipeline.
        live_display = (
            Live(Text(""), console=Console(file=sys.stdout), auto_refresh=False)
            if self.clear_screen and sys.stdout.isatty()
            else None
        )
        self.first_render = True
        try:
            while True:
                self.poll()
                complete = self.is_complete()

                # Continuous mode renders every poll. One-shot mode stays quiet
                # during warm-up and emits only its final measurement.
                should_render = not self.once or complete or not self.containers
                if should_render:
                    rendered = self.render()
                    if live_display is None:
                        typer.echo(rendered)
                    elif self.first_render:
                        live_display.update(Text(rendered))
                        live_display.start(refresh=True)
                    else:
                        live_display.update(Text(rendered), refresh=True)
                    self.first_render = False

                if self.once and (complete or not self.containers):
                    return 0
                time.sleep(self.interval)
        except DockerStatsError as exc:
            typer.echo(f"Error: {exc}", err=True)
            return 1
        except KeyboardInterrupt:
            if live_display is None and sys.stdout.isatty():
                typer.echo()
            return 0
        finally:
            if live_display is not None and not self.first_render:
                live_display.stop()


@app.command(help="Monitor per-container Docker network traffic from cumulative counters.")
def main(
    window: Annotated[
        float,
        typer.Option(
            "--window",
            metavar="SECONDS",
            callback=validate_window,
            help="Minimum measurement window in seconds.",
        ),
    ] = 5.0,
    interval: Annotated[
        float,
        typer.Option(
            "--interval",
            metavar="SECONDS",
            callback=validate_interval,
            help="Polling interval in seconds.",
        ),
    ] = 1.0,
    include_all: Annotated[
        bool, typer.Option("--all", help="Include stopped containers.")
    ] = False,
    once: Annotated[
        bool, typer.Option("--once", help="Print one complete measurement and exit.")
    ] = False,
    no_clear: Annotated[
        bool, typer.Option("--no-clear", help="Do not clear between updates.")
    ] = False,
    graph_width: Annotated[
        int,
        typer.Option(
            "--graph-width",
            metavar="N",
            callback=validate_graph_width,
            help="Number of samples displayed in each throughput graph.",
        ),
    ] = 60,
) -> None:
    """Monitor per-container Docker network traffic from cumulative counters.

    Args:
        window (float): Minimum elapsed seconds used to calculate each rate.
        interval (float): Delay in seconds between Docker statistics polls.
        include_all (bool): Include stopped containers in Docker output.
        once (bool): Print one complete measurement and then exit.
        no_clear (bool): Preserve previous output between terminal refreshes.
        graph_width (int): Number of aggregate samples retained and displayed.

    Raises:
        typer.Exit: Always raised with the monitor's process exit code so Typer
            can terminate the command consistently.
    """
    monitor = TrafficMonitor(
        window=window,
        interval=interval,
        include_all=include_all,
        once=once,
        clear_screen=not no_clear,
        graph_width=graph_width,
    )
    raise typer.Exit(code=monitor.run())


if __name__ == "__main__":
    app()
