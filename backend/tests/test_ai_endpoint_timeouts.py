"""[R231] 会调大模型的前端接口必须放宽超时 —— 守住一次同步上游带来的回归。

## 这条测试是来补一个真事故的

用户: 「检查一遍我的 ai, 用不了了, 一直报错请求超时(30s)·
/api/stock-analysis/signal/688802.SH」。

根因**不在 fork 自己写的代码里**: 作者在 `f03bc38`(2026-09-07)给
`frontend/src/lib/api.ts` 的 `request()` 加了全局 30 秒超时。他的理由完全
正当 —— 后端依赖 polars, 偶发挂起时若无超时会占满浏览器同源连接池, 表现
为整页请求全部排队"已停止"。他也给自己的回测/筛选接口开了 300s 豁免
(`COMPUTE_REQUEST_TIMEOUT_MS`)。

但 **fork 的 AI 接口一个都没拿到豁免**。09-08 那次合并 v0.2.3 之后, 它们
就被静默套上了 30 秒, 而一次 LLM 出文本超过 30 秒是常态不是异常。

症状为什么是"有的 AI 能用、有的不能": 个股分析 / 复盘 / 财报 / RPS 轮动
四个走的是**原生 fetch**(压根不过 `request()`), 没有闸; 其余走 `request()`
的全被掐。这种"一半好一半坏"最难查, 因为它看起来不像配置问题。

## 为什么这条测试写在后端

前端没有测试框架(package.json 里只有 dev/build/preview/lint)。而这件事
必须有一道自动检查 —— 它**恰恰是靠人看 review 看不出来的那类回归**:
上游那次提交里没有一行代码提到 AI, diff 里也看不见任何 fork 文件。

所以这里把 `api.ts` 当文本读。跨语言是难看了点, 但比"下次同步上游再栽一次"强。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

API_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "api.ts"

# 会真正让模型出一段文本的**客户端方法**。加新的 AI 接口时**这张表要跟着加** ——
# 漏了的话这条测试不会报错, 但用户会在 30 秒后看到超时。
#
# 按方法名而不是按 URL 路径定位, 是第一版写完就撞上的坑: 同一个路径常常
# 挂着一读一写两个方法(`/api/usage-notes/summary` 的 Get 与 Build 就是),
# 按路径找会命中先出现的那个读接口, 于是既漏判又误判。方法名是唯一的。
AI_METHODS = {
    "generateStockSignal": "单只 AI 买卖信号(用户报的就是这个)",
    "todayAi": "今日总览 AI 导读·优选",
    "ladderAiReview": "连板梯队 AI 复盘",
    "watchlistImportText": "粘整篇文章 → AI 认票并按小分队归类",
    "customSignalsAiGenerate": "自定义信号 AI 生成",
    "regimeSeesawDetect": "跷跷板 AI 甄别",
    "usageNoteDigest": "消息面单条凝练",
    "usageNotesSummaryBuild": "消息面「一大段总的」",
    "todayScoreLedgerDigest": "台账 AI 提炼",
}

# **故意**留在默认 30s 的。它们要么压根不调模型, 要么快失败才是对的。
NOT_AI_METHODS = {
    "strategyAiStatus": "读配置状态",
    "ladderAiReports": "读历史报告",
    "todayAiTrackRecord": "纯事后统计",
    "usageNotesSummaryGet": "读已存的那一段, 不重新生成",
    "strategyAiTest": "调模型, 但只发「Reply exactly: OK」—— 连通性测试要的就是快失败",
}


@pytest.fixture(scope="module")
def api_ts() -> str:
    if not API_TS.exists():
        pytest.skip(f"拿不到 {API_TS}(只跑后端时正常)")
    return API_TS.read_text(encoding="utf-8")


def test_放宽超时的常量还在且够长(api_ts: str):
    """常量本身被删掉或改小, 是这条链最容易断的一环。"""
    m = re.search(r"const AI_REQUEST_TIMEOUT_MS = ([\d_]+)", api_ts)
    assert m, "AI_REQUEST_TIMEOUT_MS 不见了 —— AI 接口会退回默认 30s"
    ms = int(m.group(1).replace("_", ""))
    assert ms >= 120_000, f"AI 超时只有 {ms / 1000:.0f}s, 一次长回答就会被掐"


def _body_of(api_ts: str, method: str) -> str:
    """截出 `method: (...) => request<...>(...)` 这一段的正文。

    用"到下一个顶层方法名为止"来断句 —— 不给 TypeScript 写解析器, 这里要的
    只是"发现漏改", 一个足够稳的窗口就够。
    """
    m = re.search(rf"^  {re.escape(method)}:", api_ts, re.M)
    assert m, f"api.ts 里找不到方法 `{method}` —— 改名了? 这张表要同步更新"
    tail = api_ts[m.end():]
    nxt = re.search(r"^  [A-Za-z_][\w]*:", tail, re.M)
    return tail[: nxt.start()] if nxt else tail[:800]


@pytest.mark.parametrize("method", sorted(AI_METHODS))
def test_每个会调模型的接口都放宽了超时(api_ts: str, method: str):
    body = _body_of(api_ts, method)
    assert "AI_REQUEST_TIMEOUT_MS" in body, (
        f"`{method}`({AI_METHODS[method]})会调大模型, 却在用默认 30s 超时 —— "
        f"用户会看到「请求超时(30s)」。给它加 timeoutMs: AI_REQUEST_TIMEOUT_MS。"
    )


@pytest.mark.parametrize("method", sorted(NOT_AI_METHODS))
def test_不调模型的接口继续守着默认超时(api_ts: str, method: str):
    """反向也要守: 把 300s 无差别撒到所有接口, 等于把作者那道闸整个废掉,
    而那道闸防的是真问题(polars 挂起占满连接池, 整页请求全部卡死)。"""
    body = _body_of(api_ts, method)
    assert "AI_REQUEST_TIMEOUT_MS" not in body, (
        f"`{method}`({NOT_AI_METHODS[method]})不该拿 AI 的放宽超时 —— "
        f"那道 30s 闸是防浏览器连接池被占满的, 别无差别地废掉它"
    )


def test_原生_fetch_那几个不受这道闸管(api_ts: str):
    """记一笔口径, 免得下次有人"顺手统一"成 request() 就把它们也掐了。

    个股分析 / 复盘 / 财报 / RPS 轮动 / 策略流式构建走的是原生 `fetch`,
    完全不过 `request()`, 所以没有超时 —— 这正是本次事故里"一半 AI 还能用"
    的原因。要把它们并进 `request()` 的话, **必须同时带上 AI 超时**。
    """
    for path in ("/api/stock-analysis/analyze", "/api/market-recap/analyze",
                 "/api/financials/analyze", "/api/rps/rotation-analyze"):
        i = api_ts.find(path)
        assert i >= 0, f"api.ts 里找不到 {path}"
        head = api_ts[max(0, i - 120): i]
        assert "await fetch(" in head, (
            f"{path} 从原生 fetch 改成 request() 了 —— 那就会被 30s 闸掐死, "
            f"必须同时加 timeoutMs: AI_REQUEST_TIMEOUT_MS"
        )
