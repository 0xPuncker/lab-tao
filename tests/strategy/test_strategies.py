"""Unit tests for strategy.strategies (pure conversion strategies)."""

from __future__ import annotations

import pytest
from strategy.history import PricePoint
from strategy.strategies import STRATEGIES, convert_immediately, dca_weekly, hold_forever

_DAY = 24 * 3600


def _series(prices: list[float], spacing: float = _DAY, start: float = 0.0) -> list[PricePoint]:
    """Build a price series with given prices and uniform time spacing."""
    return [PricePoint(netuid=1, alpha_price_tao=p, ts=start + i * spacing) for i, p in enumerate(prices)]


def test_convert_immediately_realizes_full_alpha_at_each_price() -> None:
    prices = _series([1.0, 2.0, 3.0])
    result = convert_immediately(alpha_per_point=1.0, prices=prices)
    assert result.tao_realized == pytest.approx(6.0)
    assert result.alpha_remaining == 0.0
    assert result.n_conversions == 3
    assert result.avg_conversion_price == pytest.approx(2.0)


def test_hold_forever_zero_realized_full_alpha_remaining() -> None:
    prices = _series([1.0, 2.0, 3.0, 4.0])
    result = hold_forever(alpha_per_point=2.0, prices=prices)
    assert result.tao_realized == 0.0
    assert result.alpha_remaining == pytest.approx(8.0)
    assert result.n_conversions == 0


def test_dca_weekly_converts_at_seven_day_marks() -> None:
    """15 daily points (ts 0..14d) → conversions land on day 7 and day 14."""
    prices = _series([1.0] * 15, spacing=_DAY)
    result = dca_weekly(alpha_per_point=1.0, prices=prices)
    # Day 7 (point index 7): 8 alpha accumulated, converts at price 1.0 → 8 tao.
    # Day 14 (point index 14): 7 more alpha accumulated, converts at price 1.0 → 7 tao.
    assert result.n_conversions == 2
    assert result.tao_realized == pytest.approx(15.0)
    assert result.alpha_remaining == 0.0


def test_dca_weekly_short_series_holds_everything() -> None:
    """Series shorter than a week → no conversions, all alpha sits in remaining."""
    prices = _series([1.0] * 5, spacing=_DAY)
    result = dca_weekly(alpha_per_point=1.0, prices=prices)
    assert result.n_conversions == 0
    assert result.tao_realized == 0.0
    assert result.alpha_remaining == pytest.approx(5.0)


def test_alpha_accounting_invariant_across_all_strategies() -> None:
    """alpha_remaining + alpha_converted_via_tao_realized must equal total emitted."""
    prices = _series([2.0] * 21, spacing=_DAY)  # 3 weeks of daily points at price 2
    alpha_per_point = 1.5
    total_emitted = alpha_per_point * len(prices)
    for strat in STRATEGIES.values():
        result = strat(alpha_per_point, prices)
        if result.avg_conversion_price > 0:
            converted = result.tao_realized / result.avg_conversion_price
        else:
            converted = 0.0
        assert converted + result.alpha_remaining == pytest.approx(total_emitted), (
            f"invariant broken for {result.name}: converted={converted} remaining={result.alpha_remaining}"
        )


def test_all_strategies_handle_empty_series() -> None:
    for strat in STRATEGIES.values():
        result = strat(1.0, [])
        assert result.tao_realized == 0.0
        assert result.alpha_remaining == 0.0
        assert result.n_conversions == 0
        assert result.avg_conversion_price == 0.0


def test_strategies_registry_has_three_entries() -> None:
    assert set(STRATEGIES.keys()) == {"convert_immediately", "hold_forever", "dca_weekly"}
