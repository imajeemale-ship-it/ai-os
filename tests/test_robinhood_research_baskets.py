from ai_os.robinhood_research_baskets import BASKETS, strategy_allowed


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
    assert tactical["policy"].max_spread_pct == 0.08
    assert core["policy"].max_spread_pct == 0.08
    assert tactical["exit_rule"] == {"profit_target_pct": 0.20, "loss_limit_pct": -0.15}
    assert core["exit_rule"] == {"profit_target_pct": 0.30, "loss_limit_pct": -0.20}


def test_strategy_allowlist_requires_a_matching_method():
    assert strategy_allowed(["breakout_continuation"], {"breakout_continuation"})
    assert not strategy_allowed(["dean_ahrens_unusual_flow_proxy"], {"pullback_continuation_uptrend"})
