"""Unit tests for the Oracle SGA and PGA memory tree."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from oracle.python.memory_tree import MemoryAllocation, build_pga_tree, build_sga_tree, format_bytes


def render(value) -> str:
    """Render a Rich object to plain text."""
    output = StringIO()
    Console(file=output, force_terminal=False, width=160).print(value)
    return output.getvalue()


def test_format_bytes_uses_readable_binary_units() -> None:
    """Large byte values should be easy to scan."""
    assert format_bytes(200 * 1024**3) == "200.00 GiB"
    assert format_bytes(512 * 1024**2) == "512.00 MiB"


def test_sga_tree_groups_allocations_under_largest_pool_first() -> None:
    """SGA pools and their allocations should form a size-sorted hierarchy."""
    tree = build_sga_tree(
        200 * 1024**3,
        {
            "large pool": [MemoryAllocation("PX msg pool", 10 * 1024**3)],
            "shared pool": [
                MemoryAllocation("sql area", 12 * 1024**3),
                MemoryAllocation("library cache", 8 * 1024**3),
            ],
        },
    )

    output = render(tree)

    assert "SGA  200.00 GiB" in output
    assert output.index("shared pool") < output.index("large pool")
    assert "sql area  12.00 GiB  (60.00% of parent)" in output


def test_sga_threshold_rolls_small_allocations_into_other() -> None:
    """A threshold should retain the pool total while reducing tree noise."""
    tree = build_sga_tree(
        100 * 1024**2,
        {"shared pool": [MemoryAllocation("large", 80 * 1024**2), MemoryAllocation("small", 2 * 1024**2)]},
        min_bytes=10 * 1024**2,
    )

    output = render(tree)

    assert "large" in output
    assert "Other (1 allocations below threshold)  2.00 MiB" in output
    assert "small" not in output


def test_pga_tree_uses_total_allocated_as_parent() -> None:
    """PGA percentages should be based on total PGA allocated."""
    tree = build_pga_tree(
        [
            MemoryAllocation("total PGA allocated", 40 * 1024**3),
            MemoryAllocation("total PGA inuse", 30 * 1024**3),
            MemoryAllocation("total freeable PGA memory", 5 * 1024**3),
        ]
    )

    output = render(tree)

    assert "PGA  40.00 GiB" in output
    assert "total PGA inuse  30.00 GiB  (75.00% of parent)" in output
    assert output.count("total PGA allocated") == 0
