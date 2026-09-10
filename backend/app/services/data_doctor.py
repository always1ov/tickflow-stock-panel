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


@dataclass(frozen=True)
class Store:
    """一处存储的体检口径。"""

    rel: str
    """相对 data_dir 的路径。"""
    cn: str
    """给人看的名字。"""
    kind: str = KIND_USER
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
    Store("user_data/watchlist.parquet", "自选标的", shape=SHAPE_OPAQUE,
          note="读盘时已自带老 schema 兼容(group_id → group_ids), 这里只查读不读得动"),
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
    Store("user_data/alerts.jsonl", "告警流水", shape=SHAPE_OPAQUE,
          note="逐行 JSONL, 只查读不读得动"),
    Store("user_data/auth.json", "访问密码", shape=SHAPE_OPAQUE,
          note="**不体检内容** —— 里面是口令散列, 不该被读出来放进任何报告"),
    Store("user_data/secrets.json", "API Key", shape=SHAPE_OPAQUE,
          note="**不体检内容** —— 里面是明文 Key, 不该被读出来放进任何报告"),
    Store("user_data/lots", "持仓批次", shape=SHAPE_OPAQUE),
    Store("user_data/monitor_rules", "监控规则", shape=SHAPE_OPAQUE),
    Store("user_data/custom_signals", "自定义信号", shape=SHAPE_OPAQUE),
    Store("user_data/custom_factors", "自定义因子", shape=SHAPE_OPAQUE),
    Store("user_data/strategy_overrides", "策略参数覆盖", shape=SHAPE_OPAQUE),
    Store("user_data/auction_scan", "竞价扫描", shape=SHAPE_OPAQUE, kind=KIND_DERIVED),
    Store("user_data/news_desk", "消息面附件", shape=SHAPE_OPAQUE,
          note="图片凝练成功后原件即删, 目录里剩的是还没凝练成功的"),
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


def inspect_store(data_dir: Path, store: Store) -> dict[str, Any]:
    """体检一处存储。**纯读, 不写盘。**"""
    p = Path(data_dir) / store.rel
    out: dict[str, Any] = {
        "rel": store.rel, "cn": store.cn, "kind": store.kind,
        "note": store.note, "exists": p.exists(),
        "readable": None, "records": None,
        "missing": {}, "incomplete": {}, "error": "",
    }
    if not p.exists():
        return out
    if p.is_dir():
        out["readable"] = True
        out["records"] = sum(1 for _ in p.rglob("*") if _.is_file())
        return out
    if store.rel in NEVER_READ:
        # 只看得见"在不在、多大", 内容一个字节不读
        out["readable"] = True
        out["records"] = None
        return out
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        out["readable"] = True
    except Exception as e:  # noqa: BLE001
        out["readable"] = False
        out["error"] = f"读不动: {e}"
        return out

    rows = _records(payload, store)
    if rows is None:
        # opaque 或形状对不上都走这里。形状对不上本身值得报 —— 但只在声明了形状时才算异常
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
        # 备份文件是体检自己留下的, 不算孤儿
        if ".bak-" in p.name or p.name.endswith(".tmp"):
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
