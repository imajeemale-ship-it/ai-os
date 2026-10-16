from ai_os.telegram_control import command_kind


def test_telegram_command_routing():
    assert command_kind("status") == "status"
    assert command_kind("/why") == "why"
    assert command_kind("pause") == "pause"
    assert command_kind("continue") == "resume"


def test_trade_commands_remain_blocked():
    assert command_kind("buy AAPL") == "blocked_trade"
    assert command_kind("enable live trading") == "blocked_trade"
    assert command_kind("exercise this option") == "blocked_trade"


def test_unknown_message_returns_help():
    assert command_kind("hello there") == "help"
