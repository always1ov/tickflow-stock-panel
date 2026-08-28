from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api import monitor_rules as monitor_rules_api


def test_strategy_rule_name_follows_selected_strategy(tmp_path):
    strategy = SimpleNamespace(meta={"name": "凯特勒策略"})
    strategy_engine = MagicMock()
    strategy_engine.get.return_value = strategy

    repo = MagicMock()
    repo.store.data_dir = tmp_path
    repo.resolve_asset_type.return_value = "stock"
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        repo=repo,
        strategy_engine=strategy_engine,
    )))
    model = monitor_rules_api.RuleModel(
        id="strategy_scoped_symbol",
        name="策略监控",
        type="strategy",
        asset_type="stock",
        scope="symbols",
        symbols=["300433.SZ"],
        strategy_id="keltner",
        direction="entry",
        notify_events=["pool_entry", "pool_exit"],
        conditions=[],
    )

    result = monitor_rules_api.save_rule(model, request)

    assert result["rule"]["name"] == "策略监控 · 凯特勒策略"
    strategy_engine.get.assert_called_once_with("keltner")
