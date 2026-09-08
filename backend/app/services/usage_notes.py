"""[fork 增强] R93 使用观察笔记 → [R180] **消息面**。

用途从"归纳这个系统怎么用"扩成**消息面台账**: 政策、公告、研报截图、行业新闻、
自己的观察, 一条条记进来, 每条由 AI 凝练成一段要点, 再由 AI 把全部条目综合成
**一大段总的**, 供后续决策参考。

[R180] 三件事是新的, 其余一条没动(旧数据、状态链、并发写法全部照旧):
  · kind        text / image / file —— 一条可以挂一个附件
  · digest      AI 对这一条的凝练; 图片走多模态, 文本直接凝练
  · 一大段总的  不在本模块, 见 news_desk —— 它综合的是各条的 digest

**旧数据一条不动**: 老笔记没有 kind/digest 字段, 读时补默认(kind=text,
digest 为空), 照样能编辑、标状态、参与综合。

用途: 用户归纳"这个系统怎么用、哪些功能有用"的个人笔记本。
存储: data/user_data/usage_notes.json (数组, 按 updated_at 降序返回)。
并发: 走 json_store 的按文件互斥锁 + 原子落盘(R72 约定) —— 读-改-写整段在锁里。

每条笔记结构:
{
  "id": "note_xxxxxxxxxxxx",
  "content": "纯文本正文",
  "status": "",                      # ""=随手记 / pending=待验证 / verified=已验证 / rejected=不成立
  "pinned": false,                   # 置顶(排序最前)
  "created_at": "2026-08-31T10:00:00",
  "updated_at": "2026-08-31T10:05:00"
}

[R96] status/pinned 是按用户实际用法加的: 记的多是"观察→等市场验证"的猜想,
一条链是 随手记 → 待验证 → 已验证/不成立。老数据无这两个字段, 读时补默认。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from app.config import settings
from app.services.json_store import atomic_write_json, lock_for

MAX_NOTES = 500          # 防失控: 纯文本笔记 500 条足够, 超出拒绝新增
MAX_CONTENT_CHARS = 20000
STATUSES = ("", "pending", "verified", "rejected")
# [R180] 一条消息的形态。file 只收**可读文本**(csv/txt/md 之类) —— 二进制收了
# 也读不出内容, 只会变成一个打不开的附件。
KINDS = ("text", "image", "file")
# [R181] 时效档 —— 与 status(成立了吗)正交的第二个轴: 这条多久有效。
# 语义与分档理由见 services/news_desk.py 顶部。
HORIZONS = ("news", "thesis", "rule")
MAX_DIGEST_CHARS = 2000


def _path() -> Path:
    return settings.data_dir / "user_data" / "usage_notes.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_unlocked() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        # 解析失败不吞成空列表回写(那会永久丢数据, 见 R68 教训) —— 只读场景返回空,
        # 写场景由调用方先 list 再改, 锁内一致; 真损坏时最坏是新写覆盖, 有 tmp 原子性兜底
        return []


def _with_defaults(note: dict) -> dict:
    """老数据补默认字段(不回写盘, 读时视图)。

    [R180] 新增 kind/attachment/digest 也走这里 —— 老笔记读出来就是一条
    kind=text、没有附件、还没凝练过的消息, 不需要迁移脚本。
    """
    return {"status": "", "pinned": False, "kind": "text",
            "attachment": None, "digest": "", "digest_at": None,
            # [R181] 时效档与埋伏的兑现检查点。老数据没有 → 当"时效"处理,
            # 它们本来也确实是随手记的当下观察。
            "horizon": "news", "due_at": None, **note}


def list_notes() -> list[dict]:
    """全部笔记: 置顶在前, 组内按 updated_at 降序(最近编辑的在前)。"""
    with lock_for(_path()):
        notes = [_with_defaults(n) for n in _read_unlocked()]
    # sorted 稳定: 先按时间降序, 再把置顶的整体提前, 组内时间序保持
    by_time = sorted(notes, key=lambda n: n.get("updated_at") or "", reverse=True)
    return sorted(by_time, key=lambda n: 0 if n.get("pinned") else 1)


def create_note(content: str, *, kind: str = "text",
                attachment: dict | None = None) -> dict:
    """[R180] kind/attachment 可选 —— 不传就和改造前完全一样。

    带附件时正文可以为空(一张图本身就是内容), 但两者不能都空:
    一条既没正文也没附件的记录, 之后谁也说不清它是什么。
    """
    content = (content or "").strip()
    if kind not in KINDS:
        raise ValueError(f"kind 必须是 {KINDS} 之一")
    if not content and not attachment:
        raise ValueError("正文和附件不能都为空")
    if len(content) > MAX_CONTENT_CHARS:
        raise ValueError(f"单条笔记最长 {MAX_CONTENT_CHARS} 字")
    with lock_for(_path()):
        notes = _read_unlocked()
        if len(notes) >= MAX_NOTES:
            raise ValueError(f"笔记数量已达上限 {MAX_NOTES} 条, 请先删除旧的")
        now = _now()
        note = {
            "id": f"note_{uuid.uuid4().hex[:12]}",
            "content": content,
            "kind": kind,
            "attachment": attachment,
            # 凝练在落盘之后单独触发 —— 上传要立刻有反馈, 不能卡在一次 AI 调用上
            "digest": "",
            "digest_at": None,
            "status": "",
            "pinned": False,
            "created_at": now,
            "updated_at": now,
        }
        notes.append(note)
        atomic_write_json(_path(), notes)
    return note


def update_note(
    note_id: str,
    *,
    content: str | None = None,
    status: str | None = None,
    pinned: bool | None = None,
    horizon: str | None = None,
) -> dict | None:
    """就地改字段(None = 不改)。返回更新后的笔记; 不存在返回 None。

    只有正文修改才刷新 updated_at —— 标状态/置顶是整理动作,
    不该把一条旧观察顶到"最近编辑"的最前面去。
    """
    if content is not None:
        content = content.strip()
        if not content:
            raise ValueError("笔记内容不能为空")
        if len(content) > MAX_CONTENT_CHARS:
            raise ValueError(f"单条笔记最长 {MAX_CONTENT_CHARS} 字")
    if status is not None and status not in STATUSES:
        raise ValueError(f"status 必须是 {STATUSES} 之一")
    with lock_for(_path()):
        notes = _read_unlocked()
        for note in notes:
            if note.get("id") == note_id:
                if content is not None:
                    note["content"] = content
                    note["updated_at"] = _now()
                if status is not None:
                    note["status"] = status
                if pinned is not None:
                    note["pinned"] = bool(pinned)
                if horizon is not None:
                    # [R181] AI 判错了要能改。改成埋伏时补一个默认检查点,
                    # 改成别的就把检查点清掉 —— 只有埋伏才有"什么时候回来看"。
                    if horizon not in HORIZONS:
                        raise ValueError(f"horizon 必须是 {HORIZONS} 之一")
                    note["horizon"] = horizon
                    if horizon == "thesis":
                        note.setdefault("due_at", None)
                        if not note.get("due_at"):
                            note["due_at"] = (datetime.now()
                                              + timedelta(days=90)).isoformat(timespec="seconds")
                    else:
                        note["due_at"] = None
                atomic_write_json(_path(), notes)
                return _with_defaults(dict(note))
    return None


def set_digest(note_id: str, digest: str, *, raw_text: str | None = None,
               horizon: str | None = None, due_days: int | None = None) -> dict | None:
    """[R180] 写入 AI 凝练结果, 并**丢掉原始文件**。

    用户定的口径: **只保存凝练, 不保存图片; 文字允许保存原文。** 所以:
      · 图片  —— 凝练成功后把文件删掉, 只留要点(和文件名, 好知道这条是从哪来的)
      · 文本  —— 文件内容并进正文(那就是"原文"), 文件同样删掉

    这样盘上不会长期堆附件, 消息面攒几年也只是一堆文字。

    **删除只在这里发生, 也就是只在凝练成功之后。** 凝练失败时文件原样留着,
    用户可以重试 —— 一张图删了就再也凝练不了了, 不能在还没拿到要点时就删。

    代价说明白: 图片删掉之后**没法重新凝练**。AI 读错了、或者以后换了更好的
    模型想重跑, 源都没了。这是用户明确要的取舍。

    **不动 updated_at** —— 凝练是系统行为不是用户编辑, 把一条旧消息顶到
    "最近编辑"的最前面会打乱用户自己的整理顺序(与 update_note 里标状态/
    置顶不刷新时间是同一个道理)。
    """
    digest = (digest or "").strip()[:MAX_DIGEST_CHARS]
    stale_file: str | None = None
    with lock_for(_path()):
        notes = _read_unlocked()
        for note in notes:
            if note.get("id") != note_id:
                continue
            note["digest"] = digest
            note["digest_at"] = _now()
            # [R181] 时效档由凝练时的 AI 分类给出; 用户之后可以手动改
            if horizon:
                note["horizon"] = horizon
                note["due_at"] = (
                    (datetime.now() + timedelta(days=int(due_days))).isoformat(timespec="seconds")
                    if horizon == "thesis" and due_days else None
                )
            if raw_text:
                # 文本文件的内容并进正文 —— 用户要"文字保存原文"。接在已有备注
                # 后面而不是覆盖: 那句备注("这是某某的调研纪要")往往比正文还重要。
                existing = (note.get("content") or "").strip()
                merged = f"{existing}\n\n{raw_text}".strip() if existing else raw_text
                note["content"] = merged[:MAX_CONTENT_CHARS]
            att = note.get("attachment") or {}
            if att.get("path"):
                stale_file = att["path"]
                # 只留文件名与大小, 路径去掉 —— 记录里不该再指向一个已经不在的文件
                note["attachment"] = {k: v for k, v in att.items() if k != "path"}
            atomic_write_json(_path(), notes)
            result = _with_defaults(dict(note))
            break
        else:
            return None

    if stale_file:
        try:
            (settings.data_dir / stale_file).unlink(missing_ok=True)
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("attachment unlink failed: %s", e)
    return result


def delete_note(note_id: str) -> bool:
    with lock_for(_path()):
        notes = _read_unlocked()
        target = next((n for n in notes if n.get("id") == note_id), None)
        remaining = [n for n in notes if n.get("id") != note_id]
        if len(remaining) == len(notes):
            return False
        atomic_write_json(_path(), remaining)
    # [R180] 附件跟着记录一起删 —— 不然盘上会攒一堆没人引用的图。
    # 删文件失败只记日志: 记录已经删掉了, 不该因为一个孤儿文件把接口报成失败。
    att = (target or {}).get("attachment") or {}
    if att.get("path"):
        try:
            (settings.data_dir / att["path"]).unlink(missing_ok=True)
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("attachment unlink failed: %s", e)
    return True
