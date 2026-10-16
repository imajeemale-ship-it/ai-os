import json
from datetime import datetime, timezone

from ai_os.robinhood_research_baskets import BASKETS, candidate_confirmed, entry_opened_today, entry_window_open, strategy_allowed


def test_baskets_have_separate_windows_and_ledgers():
    tactical = BASKETS["tactical"]
    core = BASKETS["core_trend"]
    assert (tactical["policy"].min_dte, tactical["policy"].max_dte) == (7, 21)
    assert (core["policy"].min_dte, core["policy"].max_dte) == (30, 60)
    assert tactical["ledger"] != core["ledger"]


def test_baskets_enforce_budget_spread_and_distinct_exits():
    tactical = BASKETS["tactical"]
    core = BASKETS["core_trend"]
    assert tactical["policy"].max_premium == 250.0
    assert tactical["policy"].target_min_premium == 100.0
    assert tactical["policy"].max_spread_pct == 0.05
    assert core["policy"].max_spread_pct == 0.05
    assert tactical["policy"].slippage_pct == 0.0
    assert core["policy"].slippage_pct == 0.0
    assert tactical["exit_rule"] == {"profit_target_pct": 0.20, "loss_limit_pct": -0.15}
    assert core["exit_rule"] == {"profit_target_pct": 0.30, "loss_limit_pct": -0.20}


def test_strategy_allowlist_requires_a_matching_method():
    assert strategy_allowed(["breakout_continuation"], {"breakout_continuation"})
    assert not strategy_allowed(["dean_ahrens_unusual_flow_proxy"], {"pullback_continuation_uptrend"})


def test_entry_opened_today_enforces_one_daily_entry(tmp_path):
    ledger = tmp_path / "basket.jsonl"
    ledger.write_text(json.dumps({
        "status": "filled_and_scored",
        "created_at": "2026-10-15T14:50:00+00:00",
    }) + "\n")
    assert entry_opened_today(
        ledger,
        datetime(2026, 10, 15, 20, 0, tzinfo=timezone.utc),
    )
    assert not entry_opened_today(
        ledger,
        datetime(2026, 10, 16, 20, 0, tzinfo=timezone.utc),
    )


def test_candidate_confirmation_requires_trend_and_correct_signal():
    uptrend = {"established_uptrend": True}
    assert candidate_confirmed("tactical", ["dean_ahrens_unusual_flow_proxy"], uptrend)
    assert not candidate_confirmed("tactical", ["dean_ahrens_unusual_flow_proxy"], {"established_uptrend": False})
    assert candidate_confirmed("core_trend", ["pullback_continuation_uptrend"], uptrend)
    assert not candidate_confirmed("core_trend", ["dean_ahrens_unusual_flow_proxy"], uptrend)


def test_entry_window_avoids_open_and_late_day():
    assert not entry_window_open(datetime(2026, 10, 16, 13, 45, tzinfo=timezone.utc))
    assert entry_window_open(datetime(2026, 10, 16, 14, 5, tzinfo=timezone.utc))
    assert not entry_window_open(datetime(2026, 10, 16, 20, 0, tzinfo=timezone.utc))
