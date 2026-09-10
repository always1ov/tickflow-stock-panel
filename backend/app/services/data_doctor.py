"""[fork 增强 R271] 数据体检 —— 盘上那些跟着功能一起长出来的老文件, 到底缺了什么。

## 为什么需要它

用户: 「我不断改这个系统, 不断沿用以前的数据, 但是本地的数据可能不完整 —— 我加了
东西或者删除了东西, 但是系统没有重头开始, 会有残留的数据文件, 缺字段或者不完整」。

这是长期演进的自建系统最典型的一类问题, 而且**它不会报错**。这套代码读盘时几乎处处
用 `.get()`, 所以缺字段不崩 —— 可那正是更阴的地方: **缺字段被静默当成「用户没设过」**。
`positions.json` 就是活例子: 它的文档字符串到今天仍写着结构是 `{held, cost, updated_at}`,
而 `weight`(仓位比例)是后加的; 老记录没有它, 系统只会当你从没填过仓位, 于是组合层面
的「总仓位 vs 姿态基调」「当前→目标差额」全部按空值走, 一声不吭。

## 三类, 处置办法完全相反

    用户数据    自选/分组、持仓标记、模拟盘账本、消息面、把握分台账、偏好
                **不可重算** —— 缺字段只能按默认值补齐, 少一条就是真丢了
    派生数据    行情分区、enriched 快照、AI 报告、回测结果
                **可重算** —— 坏了删掉重跑就行, 补它反而是在给假数据续命
    孤儿文件    功能删掉了、文件还留在盘上
                先确认真没人读, 再删

**本模块只报告与补齐, 一个字节都不删。** 删除是不可逆的, 而这里判断"没人读"靠的是
一张手写注册表 —— 注册表漏了一项, 自动删除就等于把用户数据删了。报告出来让人自己定,
代价只是多点一下。

## 注册表怎么保证不过时

这张表最大的风险是**它自己会过时**: 今天列全, 下次加个 store 又漏, 于是体检报告
说"一切正常", 而漏掉的那个正在悄悄丢字段。所以不靠人记得更新 ——
`test_data_doctor` 会扫源码里所有 `data_dir / "user_data" / …` 的引用,
**只要出现没登记的文件就红**。注册表的完整性由测试保证, 不由自觉保证。
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

USER_DIR = "user_data"

#: 记录的组织方式。
#:
#: - ``object``      整个文件就是一个对象(偏好、市场基调这类单例)
#: - ``record_map``  ``{key: record}``(持仓标记按 symbol 存)
#: - ``record_list`` ``[record, ...]``(分组、笔记)
#: - ``nested``      记录藏在某个键下面(模拟盘: traders → books → positions)
#: - ``opaque``      目录 / 二进制 / 逐行 JSONL —— 只查在不在、读不读得动
SHAPE_OBJECT = "object"
SHAPE_RECORD_MAP = "record_map"
SHAPE_RECORD_LIST = "record_list"
SHAPE_OPAQUE = "opaque"

KIND_USER = "user"
KIND_DERIVED = "derived"

#: 文件是怎么存的 —— **和"记录怎么组织"是两回事, 第一版把这两件事混成了一维, 结果
#: 拿 UTF-8 去读二进制 parquet、拿整份 `json.loads` 去读逐行 JSONL, 两处健康的数据
#: 被报成「读不动」。体检误报比不报更糟: 人看两次假警报之后就再也不看它了。
FMT_JSON = "json"
"""整份是一个 JSON。"""
FMT_JSONL = "jsonl"
"""每行一个 JSON —— 整份丢给 `json.loads` 必然在第二行报 "Extra data"。"""
FMT_PARQUET = "parquet"
"""二进制列存 —— 一个字节都不能按文本读。"""
FMT_DIR = "dir"
FMT_SECRET = "secret"
"""口令散列 / 明文 Key —— 一个字节都不读。"""


@dataclass(frozen=True)
class Store:
    """一处存储的体检口径。"""

    rel: str
    """相对 data_dir 的路径。"""
    cn: str
    """给人看的名字。"""
    kind: str = KIND_USER
    fmt: str = FMT_JSON
    """怎么把它读进来。**跟 shape 是两回事** —— 见 FMT_* 的说明。"""
    shape: str = SHAPE_OPAQUE
    list_key: str = ""
    """record_list 藏在对象的哪个键下; 空表示文件本身就是数组。"""
    fields: dict[str, Any] = field(default_factory=dict)
    """**后加的字段 → 补齐时用的默认值。**

    只列"后来才加、老记录会缺"的那些。必填字段(比如 symbol)不在这里 —— 那种缺失
    不是补默认值能解决的, 补出来的是一条假记录, 只该报出来让人自己看。
    """
    required: tuple[str, ...] = ()
    """缺了就说明这条记录本身有问题的字段。只报, 不补。"""
    note: str = ""


#: 注册表。**新增任何 user_data 下的存储都要在这里登记** —— 有测试盯着。
STORES: tuple[Store, ...] = (
    Store("user_data/watchlist.parquet", "自选标的", fmt=FMT_PARQUET,
          fields={"symbol": None, "added_at": None, "note": None, "group_ids": None},
          note="读盘时已自带老 schema 兼容(group_id → group_ids); 这里查列在不在, 不改"),
    Store("user_data/watchlist_groups.json", "自选分组", shape=SHAPE_RECORD_LIST,
          required=("id", "name"), fields={"color": "sky"},
          note="color 是后加的; 缺了前端会拿不到配色"),
    Store("user_data/positions.json", "持仓标记", shape=SHAPE_RECORD_MAP,
          fields={"held": False, "cost": None, "weight": None, "updated_at": ""},
          note="weight(仓位比例)是后加的 —— 缺了会被当成「没填仓位」, 组合层面的提示全部失效"),
    Store("user_data/paper_traders.json", "模拟盘账本", shape=SHAPE_OPAQUE,
          note="账本读取自带老数据迁移(单本平铺 → books)。结构深, 不做字段级补齐"),
    Store("user_data/usage_notes.json", "消息面记录", shape=SHAPE_RECORD_LIST,
          required=("id",),
          fields={"status": "", "horizon": "news", "pinned": False,
                  "digest": "", "due_at": None},
          note="horizon(时效/埋伏/规律)与 digest 都是后加的"),
    Store("user_data/news_desk_summary.json", "消息面总览", shape=SHAPE_OBJECT,
          fields={"text": "", "as_of": "", "item_count": 0}),
    Store("user_data/score_ledger.json", "把握分台账", shape=SHAPE_OPAQUE),
    Store("user_data/signals.json", "AI 个股信号", shape=SHAPE_OPAQUE),
    Store("user_data/ai_pick_ledger.json", "AI 优选台账", shape=SHAPE_OPAQUE),
    Store("user_data/portfolio_history.json", "组合净值历史", shape=SHAPE_OPAQUE),
    Store("user_data/preferences.json", "偏好设置", shape=SHAPE_OBJECT),
    Store("user_data/today_prefs.json", "今日总览偏好", shape=SHAPE_OBJECT),
    Store("user_data/today_ai.json", "今日 AI 导读", shape=SHAPE_OPAQUE, kind=KIND_DERIVED),
    Store("user_data/market_mode.json", "大盘红绿灯", shape=SHAPE_OPAQUE, kind=KIND_DERIVED),
    Store("user_data/seesaw_history.json", "板块跷跷板", shape=SHAPE_OPAQUE, kind=KIND_DERIVED),
    Store("user_data/livermore.json", "利弗莫尔趋势", shape=SHAPE_OPAQUE, kind=KIND_DERIVED),
    Store("user_data/pattern_digest.json", "形态提炼", shape=SHAPE_OPAQUE, kind=KIND_DERIVED),
    Store("user_data/focus_overrides.json", "关注清单覆盖", shape=SHAPE_OPAQUE),
    Store("user_data/focus_snapshot.json", "关注清单快照", shape=SHAPE_OPAQUE, kind=KIND_DERIVED),
    Store("user_data/external_page_view.json", "外部网页配置", shape=SHAPE_OPAQUE),
    Store("user_data/external_view_latest.json", "外部网页缓存", shape=SHAPE_OPAQUE,
          kind=KIND_DERIVED),
    Store("user_data/research_candidates.json", "回测候选池", shape=SHAPE_OPAQUE),
    Store("user_data/alerts.jsonl", "告警流水", fmt=FMT_JSONL,
          note="每行一个 JSON —— 整份 json.loads 必然在第二行报错, 得逐行读"),
    Store("user_data/auth.json", "访问密码", fmt=FMT_SECRET,
          note="**一个字节都不读** —— 里面是口令散列, 不该出现在任何报告里"),
    Store("user_data/secrets.json", "API Key", fmt=FMT_SECRET,
          note="**一个字节都不读** —— 里面是明文 Key, 不该出现在任何报告里"),
    Store("user_data/lots", "持仓批次", fmt=FMT_DIR),
    Store("user_data/monitor_rules", "监控规则", fmt=FMT_DIR),
    Store("user_data/custom_signals", "自定义信号", fmt=FMT_DIR),
    Store("user_data/custom_factors", "自定义因子", fmt=FMT_DIR),
    Store("user_data/strategy_overrides", "策略参数覆盖", fmt=FMT_DIR),
    Store("user_data/auction_scan", "竞价扫描", fmt=FMT_DIR, kind=KIND_DERIVED),
    Store("user_data/news_desk", "消息面附件", fmt=FMT_DIR,
          note="图片凝练成功后原件即删, 目录里剩的是还没凝练成功的"),

    # [R272] 下面这六处是**真机上跑了一次体检才发现漏登记的** —— 它们的路径不是
    # `data_dir / "user_data" / "字面量"`, 而是走 `JsonReportStore(filename)` 或模块常量,
    # 而第一版的守卫只认字面量, 于是它们全被当成了「孤儿」报给用户。
    Store("user_data/ai_reports.json", "AI 大盘研判报告", kind=KIND_DERIVED,
          shape=SHAPE_RECORD_LIST, required=("id",)),
    Store("user_data/ai_stock_reports.json", "AI 个股分析报告", kind=KIND_DERIVED,
          shape=SHAPE_RECORD_LIST, required=("id",)),
    Store("user_data/ai_market_recaps.json", "AI 复盘归档", kind=KIND_DERIVED,
          shape=SHAPE_RECORD_LIST, required=("id",)),
    Store("user_data/ladder_ai_reports.json", "连板梯队 AI 复盘", kind=KIND_DERIVED,
          shape=SHAPE_RECORD_LIST, required=("id",)),
    Store("user_data/strategy_cache.json", "策略结果缓存", kind=KIND_DERIVED,
          note="纯缓存, 最容易长得很大 —— 删掉会自动重算"),
    Store("user_data/strategy_run_timings.json", "策略耗时统计", kind=KIND_DERIVED),
)

#: 内容一个字节都不读的存储 —— 里面是口令散列与明文 Key。
#:
#: 体检报告会经过接口、可能被截图、被贴进聊天。**把密钥读进内存再放进报告, 是拿一个
#: 运维便利去换一条泄密通道。** 这两处只查"在不在、大小多少"。
NEVER_READ = frozenset({"user_data/auth.json", "user_data/secrets.json"})

_BY_REL = {s.rel: s for s in STORES}


def _records(payload: Any, store: Store) -> list[dict] | None:
    """按声明的形状取出待检查的记录列表; 形状对不上返回 None。"""
    if store.shape == SHAPE_OBJECT:
        return [payload] if isinstance(payload, dict) else None
    if store.shape == SHAPE_RECORD_MAP:
        if not isinstance(payload, dict):
            return None
        return [v for v in payload.values() if isinstance(v, dict)]
    if store.shape == SHAPE_RECORD_LIST:
        raw = payload.get(store.list_key) if (store.list_key and isinstance(payload, dict)) \
            else payload
        if not isinstance(raw, list):
            return None
        return [v for v in raw if isinstance(v, dict)]
    return None


def _read_payload(p: Path, store: Store, out: dict[str, Any]) -> Any | None:
    """按声明的格式把内容读进来。读不动就在 out 上留下原因并返回 None。

    **格式必须逐种处理, 不能一律 UTF-8 + json.loads。** 第一版就是那么写的, 于是
    二进制 parquet 和逐行 JSONL 这两份完全健康的数据被报成「读不动」——
    **体检误报比不报更糟**: 人看两次假警报之后就再也不看它了。
    """
    if store.fmt == FMT_SECRET:
        out["readable"] = True
        return None                      # 一个字节都不读
    if store.fmt == FMT_PARQUET:
        try:
            import polars as pl
            lf = pl.scan_parquet(p)
            out["readable"] = True
            out["records"] = int(lf.select(pl.len()).collect().item())
            # parquet 的"字段"就是列 —— 缺列在这里查得出来
            return {"__columns__": list(lf.collect_schema().names())}
        except Exception as e:  # noqa: BLE001
            out["readable"] = False
            out["error"] = f"读不动: {e}"
            return None
    if store.fmt == FMT_JSONL:
        bad = 0
        rows: list[dict] = []
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:  # noqa: BLE001, PERF203
                    bad += 1
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
        except Exception as e:  # noqa: BLE001
            out["readable"] = False
            out["error"] = f"读不动: {e}"
            return None
        out["readable"] = True
        out["records"] = len(rows)
        if bad:
            out["error"] = f"有 {bad} 行不是合法 JSON(多半是写到一半被打断的)"
        return {"__rows__": rows}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        out["readable"] = True
        return payload
    except Exception as e:  # noqa: BLE001
        out["readable"] = False
        out["error"] = f"读不动: {e}"
        return None


def inspect_store(data_dir: Path, store: Store) -> dict[str, Any]:
    """体检一处存储。**纯读, 不写盘。**"""
    p = Path(data_dir) / store.rel
    out: dict[str, Any] = {
        "rel": store.rel, "cn": store.cn, "kind": store.kind, "fmt": store.fmt,
        "note": store.note, "exists": p.exists(), "bytes": 0,
        "readable": None, "records": None,
        "missing": {}, "incomplete": {}, "error": "",
    }
    if not p.exists():
        return out
    if p.is_dir():
        files = [f for f in p.rglob("*") if f.is_file()]
        out["readable"] = True
        out["records"] = len(files)
        out["bytes"] = sum(f.stat().st_size for f in files)
        return out
    out["bytes"] = p.stat().st_size

    payload = _read_payload(p, store, out)
    if payload is None:
        return out

    # parquet: 只比列名
    if isinstance(payload, dict) and "__columns__" in payload:
        cols = set(payload["__columns__"])
        out["missing"] = {k: out["records"] or 0 for k in store.fields if k not in cols}
        return out
    if isinstance(payload, dict) and "__rows__" in payload:
        rows: list[dict] | None = payload["__rows__"]
    else:
        rows = _records(payload, store)
        if rows is None:
            if store.shape != SHAPE_OPAQUE:
                out["error"] = "结构和预期对不上(可能是更早的版本写的)"
            return out
        out["records"] = len(rows)

    for name in store.fields:
        n = sum(1 for r in rows if name not in r)
        if n:
            out["missing"][name] = n
    for name in store.required:
        n = sum(1 for r in rows if not r.get(name))
        if n:
            out["incomplete"][name] = n
    return out


def find_orphans(data_dir: Path) -> list[dict[str, Any]]:
    """`user_data/` 下有、注册表里没有的东西 —— 多半是退役功能留下的。

    **只报不删。** 判断"没人读"靠的是那张手写注册表, 而注册表可能漏 ——
    自动删除等于拿一张可能不全的表去删用户数据。
    """
    root = Path(data_dir) / USER_DIR
    if not root.is_dir():
        return []
    known = {s.rel for s in STORES}
    out: list[dict[str, Any]] = []
    for p in sorted(root.iterdir()):
        rel = f"{USER_DIR}/{p.name}"
        if rel in known:
            continue
        # 备份不算孤儿: `.bak-时间戳` 是体检留的, `.bak` 是各个 store 自己留的
        # (paper_traders / watchlist 保存时都会留一份)。把它们报成孤儿等于催人删备份。
        if ".bak" in p.name or p.name.endswith(".tmp"):
            continue
        size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() \
            else p.stat().st_size
        out.append({"rel": rel, "is_dir": p.is_dir(), "bytes": size})
    return out


def scan(data_dir: Path) -> dict[str, Any]:
    """整份体检报告。纯读。"""
    stores = [inspect_store(Path(data_dir), s) for s in STORES]
    orphans = find_orphans(Path(data_dir))
    fixable = [s for s in stores if s["missing"] and _BY_REL[s["rel"]].kind == KIND_USER]
    return {
        "stores": stores,
        "orphans": orphans,
        "summary": {
            "checked": len(stores),
            "present": sum(1 for s in stores if s["exists"]),
            "unreadable": sum(1 for s in stores if s["readable"] is False),
            "with_missing": len(fixable),
            "with_incomplete": sum(1 for s in stores if s["incomplete"]),
            "orphans": len(orphans),
        },
    }


def _fill(payload: Any, store: Store) -> tuple[Any, int]:
    """按默认值补齐缺失字段, 返回(新内容, 补了几条)。纯函数。"""
    filled = 0

    def patch(rec: dict) -> dict:
        nonlocal filled
        add = {k: v for k, v in store.fields.items() if k not in rec}
        if not add:
            return rec
        filled += 1
        # **补在后面而不是覆盖** —— 已有的值一个都不动
        return {**rec, **add}

    if store.shape == SHAPE_OBJECT and isinstance(payload, dict):
        return patch(payload), filled
    if store.shape == SHAPE_RECORD_MAP and isinstance(payload, dict):
        return {k: (patch(v) if isinstance(v, dict) else v) for k, v in payload.items()}, filled
    if store.shape == SHAPE_RECORD_LIST:
        if store.list_key and isinstance(payload, dict) and isinstance(payload.get(store.list_key), list):
            rows = [patch(v) if isinstance(v, dict) else v for v in payload[store.list_key]]
            return {**payload, store.list_key: rows}, filled
        if isinstance(payload, list):
            return [patch(v) if isinstance(v, dict) else v for v in payload], filled
    return payload, filled


def heal(data_dir: Path, rels: list[str]) -> dict[str, Any]:
    """给指定的用户数据补齐缺失字段。**改动前先备份, 一条记录都不删。**

    只补 `fields` 里声明过默认值的那些。必填字段的缺失(`required`)不补 ——
    补出来的是一条假记录, 那种只该报出来让人自己看。
    """
    from app.services.json_store import atomic_write_json, lock_for

    done: list[dict[str, Any]] = []
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for rel in rels:
        store = _BY_REL.get(rel)
        if store is None:
            done.append({"rel": rel, "ok": False, "error": "没登记的存储, 不动"})
            continue
        if store.kind != KIND_USER or not store.fields:
            done.append({"rel": rel, "ok": False, "error": "这一处不做字段级补齐"})
            continue
        p = Path(data_dir) / rel
        if not p.exists():
            done.append({"rel": rel, "ok": False, "error": "文件不存在"})
            continue
        try:
            with lock_for(p):
                payload = json.loads(p.read_text(encoding="utf-8"))
                new, filled = _fill(payload, store)
                if not filled:
                    done.append({"rel": rel, "ok": True, "filled": 0, "backup": ""})
                    continue
                backup = p.with_name(f"{p.name}.bak-{stamp}")
                shutil.copy2(p, backup)          # 先备份, 再写
                atomic_write_json(p, new)
            done.append({"rel": rel, "ok": True, "filled": filled, "backup": backup.name})
        except Exception as e:  # noqa: BLE001
            logger.warning("data doctor heal %s failed: %s", rel, e)
            done.append({"rel": rel, "ok": False, "error": str(e)})
    return {"results": done}
