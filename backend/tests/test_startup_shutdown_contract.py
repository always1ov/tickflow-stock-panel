"""启动 / 停机契约测试 —— 防止「加了启动、忘了停机」。

背景
----
`main.py` 的 `_application_lifespan` 在可读性重构中被拆成 24 个具名装配步骤,
启动流程与停机流程从此分处两个函数(`_application_lifespan` / `_shutdown_services`)。
这在可读性上是收益,但**新增了一个真实风险**:以前启动与停机写在同一段代码里、
肉眼可见;现在新增一个后台服务时容易只加启动、忘了在停机表里加对应项。
这类遗漏在运行时几乎不可见 —— 退出时线程/连接不被清理,只在某些场景
(进程无法退出、端口未释放、日志缓冲丢失)才暴露。

本测试用**静态方式**把这条契约钉住:只读 `main.py` 源码做 AST 分析,
不导入任何应用模块,因此不依赖 polars / fastapi / numba,能在任何环境运行。

不变量
------
1. `main.py` 里每一个挂到 `app.state` 的属性,必须满足三者之一:
   a. 出现在 `_shutdown_services` 的停机表里;
   b. 在 `_shutdown_services` 内被显式停机(属性访问或 `getattr` 字符串形式);
   c. 在 `_NO_LIFECYCLE` 白名单里,且写明了「为什么它不需要停机」。
   新增属性而三处都没处置时本测试失败 —— 强制作者做一次判断。
2. `_register_routers` 注册的 router 序列被冻结,防止路由被误删或重排
   (FastAPI 在多条规则重叠时,匹配结果与注册顺序有关)。
"""

from __future__ import annotations

import ast
from pathlib import Path

MAIN_PY = Path(__file__).resolve().parents[1] / "app" / "main.py"

# ── 无生命周期白名单 ────────────────────────────────────────────────
# 挂到 app.state 但**不需要**停机动作的对象。每一项都必须写明理由,
# 否则后来的人无法判断它到底是"真的不用停"还是"忘了停"。
_NO_LIFECYCLE: dict[str, str] = {
    # 数据层与只读上下文:无后台线程,随进程一起消失
    "datastore": "纯数据存储对象, 无后台线程",
    "repo": "KlineRepository, 数据访问层, 无生命周期",
    "capabilities": "能力集合, 启动时算完即只读",
    "data_dir_persistent": "布尔标志 (data_dir 是否为持久化挂载点)",
    "extension_load_errors": "二次开发扩展的加载错误列表, 纯数据",
    "extension_registry": "扩展注册表, 无后台线程",
    "indicators_ready": "布尔标志, 标记 enriched 缓存是否预热完成",
    # 被调用方驱动的引擎: 无常驻线程/连接, 因此无需 stop
    "monitor_engine": "MonitorRuleEngine — 规则内存态, 由请求/刷新驱动, 无常驻任务",
    "sector_monitor_service": "SectorMonitorService — 无 stop() 方法, 计算型服务",
    "strategy_engine": "StrategyEngine — 无 stop() 方法, 由请求驱动",
    "strategy_monitor": "策略监控配置对象, 纯内存态",
}

# ── 常驻后台服务(必须停机)─────────────────────────────────────────
# 这些服务持有后台线程或长连接,漏停会导致进程退不干净。
_MUST_BE_STOPPED = (
    "pull_scheduler",
    "financial_scheduler",
    "quote_service",
    "depth_service",
    "wecom_bot_service",
    "minute_refresh",
)

# ── 路由注册序列(冻结)─────────────────────────────────────────────
# 与本次可读性重构的基线提交 ae7b550 逐条一致 —— 即「重构前后路由顺序完全没变」
# 这件事本身就是被测断言,不是靠人工核对。新增路由请追加到末尾,并同步本列表。
# 为什么顺序值得冻结: FastAPI 在多条路径规则重叠时,匹配结果取决于注册先后,
# 因此「重排 router」是一种不会报错、只会静默改变行为的改动。
_EXPECTED_ROUTERS = (
    "core_router",
    "auth_api.router",
    "kline.router",
    "watchlist.router",
    "screener.router",
    "backtest.router",
    "factors.router",
    "mining.router",
    # [R327] R59 的 AI 操盘手换成了转折模拟盘, 路由跟着换名
    "flip_paper.router",
    "intraday.router",
    "indices.router",
    "overview.router",
    "today.router",
    "usage_notes.router",
    "focus.router",
    "global_indices.router",
    "external_page.router",
    "abnormal.router",
    "regime.router",
    "analysis.router",
    "pipeline.router",
    "data.router",
    "ext_data.router",
    "financials.router",
    "stock_analysis.router",
    "market_recap.router",
    "settings_api.router",
    "strategy.router",
    "signals.router",
    "monitor_rules.router",
    "lots.router",
    "alerts.router",
    "rps.router",
    # [R326] 上游 v0.2.4 新增: 盘中板块轮动监控。**这条守卫正是这么用的** ——
    # 同步上游时它当场报出「新增: ['sector_rotation.router']」, 确认是作者有意
    # 新增的功能之后才登记进来。
    "sector_rotation.router",
)


# ── 取数辅助 ────────────────────────────────────────────────────────
def _parse_main() -> ast.Module:
    return ast.parse(MAIN_PY.read_text(encoding="utf-8"))


def _find_func(tree: ast.Module, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(
        f"main.py 里找不到函数 {name}() —— 函数被改名或删除后请同步本测试"
    )


def _is_app_state(node: ast.AST) -> bool:
    """判断节点是否是 `app.state`。"""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "state"
        and isinstance(node.value, ast.Name)
        and node.value.id == "app"
    )


def _app_state_attrs(tree: ast.AST) -> set[str]:
    """收集 `app.state.<attr>` 形态的属性名。"""
    return {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and _is_app_state(n.value)
    }


def _app_state_getattr_names(tree: ast.AST) -> set[str]:
    """收集 `getattr(app.state, "<attr>", ...)` 形态的字符串名。

    停机函数为了容错写的是 `getattr(app.state, "watchdog", None)` 而不是
    `app.state.watchdog` —— 纯属性节点扫描抓不到这种写法,必须单独认。
    """
    out: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and _is_app_state(node.args[0])
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            out.add(node.args[1].value)
    return out


def _shutdown_table_names(tree: ast.Module) -> set[str]:
    """取出 `_shutdown_services` 里 (属性名, 停止方法名) 表格的属性名。"""
    shutdown_func = _find_func(tree, "_shutdown_services")
    table: set[str] = set()
    for node in ast.walk(shutdown_func):
        if isinstance(node, ast.Tuple):
            for elt in node.elts:
                if (
                    isinstance(elt, ast.Tuple)
                    and len(elt.elts) == 2
                    and all(
                        isinstance(e, ast.Constant) and isinstance(e.value, str)
                        for e in elt.elts
                    )
                ):
                    table.add(elt.elts[0].value)
    return table


# ── 测试 ────────────────────────────────────────────────────────────
def test_router_registration_order_is_frozen() -> None:
    """_register_routers 的 include_router 序列必须与冻结列表逐条一致。"""
    func = _find_func(_parse_main(), "_register_routers")

    actual = tuple(
        ast.unparse(node.args[0])
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "include_router"
        and node.args
    )

    added = sorted(set(actual) - set(_EXPECTED_ROUTERS))
    removed = sorted(set(_EXPECTED_ROUTERS) - set(actual))
    assert actual == _EXPECTED_ROUTERS, (
        "路由注册序列变了。\n"
        f"  新增: {added}\n"
        f"  缺失: {removed}\n"
        f"  仅顺序变化: {set(actual) == set(_EXPECTED_ROUTERS) and actual != _EXPECTED_ROUTERS}\n"
        "确认是有意的之后,同步更新本测试的 _EXPECTED_ROUTERS。"
    )


def test_every_app_state_attribute_has_a_shutdown_plan() -> None:
    """每个挂到 app.state 的属性都必须有停机安排,或被白名单明确豁免。"""
    tree = _parse_main()
    all_attrs = _app_state_attrs(tree)
    shutdown_func = _find_func(tree, "_shutdown_services")

    handled = (
        _shutdown_table_names(tree)
        | _app_state_attrs(shutdown_func)          # 显式停机: app.state.scheduler.shutdown()
        | _app_state_getattr_names(shutdown_func)  # 容错停机: getattr(app.state, "watchdog", None)
        | set(_NO_LIFECYCLE)
    )

    unhandled = sorted(all_attrs - handled)
    assert not unhandled, (
        f"这些 app.state 属性既不在停机表、也没有白名单豁免: {unhandled}\n"
        "请在 _shutdown_services 里补停机项;确实无需停机的,"
        "在 _NO_LIFECYCLE 里加一行并写明理由。"
    )

    # 反向校验:白名单不能有失效条目,避免它慢慢腐烂成一张废纸
    stale = sorted(set(_NO_LIFECYCLE) - all_attrs)
    assert not stale, f"_NO_LIFECYCLE 里有已不存在的属性: {stale} —— 请删掉。"


def test_resident_services_are_in_the_shutdown_table() -> None:
    """持有后台线程/长连接的服务必须在停机表里(回归保护)。"""
    table = _shutdown_table_names(_parse_main())
    missing = sorted(set(_MUST_BE_STOPPED) - table)
    assert not missing, (
        f"停机表里少了这些常驻服务: {missing} —— 它们都有后台线程/长连接,必须停机。"
    )
