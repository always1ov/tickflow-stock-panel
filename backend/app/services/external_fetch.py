"""[fork 增强] R117 外部网页「抓取模式」的取数层。

用途: 「盘面参考」里那个外部页面, 从 iframe 内嵌改成**后端抓原文 + 前端跑
用户自己写的格式化代码 + 固定版式渲染**。这里只负责第一步 —— 把用户填的
URL 抓回来, 原样返回文本, 不解析、不落盘、不进能力路由矩阵。

为什么要走后端: 浏览器直连第三方站点几乎必然被 CORS 挡掉, 而这是用户自己
指定的地址, 由服务端代取是唯一可行路径。

**代取 = SSRF 面**, 所以这里的守卫不是可选项:
  - 只放 http/https, 地址里不许带账号密码;
  - 主机名解析出的**每一个** IP 都必须是公网地址 —— 环回/私网/链路本地/
    保留段一律拒绝(面板跑在家里的 NAS 上, 内网服务都在同一网段, 一旦这个
    口子能打内网, 等于把整个局域网暴露给填 URL 的人; 何况面板还支持
    AUTH_DISABLED 免登录);
  - 重定向**逐跳重新校验**(不能用 httpx 的 follow_redirects —— 那样 302
    到 127.0.0.1 就绕过了首跳检查), 最多 3 跳;
  - 响应大小与超时都有硬上限, 边下边数, 超了直接断。
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import threading
import time
from urllib.parse import urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_S = 12.0
MAX_BYTES = 2 * 1024 * 1024   # 2MB —— 单页原文的合理上限, 超了多半是抓错了东西
MAX_REDIRECTS = 3
_TTL_S = 10.0                 # 多标签页/自动刷新合并成同一次上游请求

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}   # url → (抓取时刻, 结果)


class FetchError(Exception):
    """抓取失败(地址不合法 / 被守卫拒绝 / 上游异常)。消息直接给用户看。"""


def _guard_host(host: str) -> None:
    """主机名必须解析到公网地址 —— 任一解析结果落在内网段就整体拒绝。"""
    if not host:
        raise FetchError("网站地址缺少主机名")
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        raise FetchError(f"域名解析失败: {host} ({e.strerror or e})") from e
    for info in infos:
        addr = info[4][0]
        # IPv6 带 scope id(fe80::1%eth0)时 ip_address 不认, 截掉再判
        try:
            ip = ipaddress.ip_address(addr.split("%", 1)[0])
        except ValueError:
            raise FetchError(f"无法识别的地址: {addr}") from None
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise FetchError(
                f"出于安全考虑不抓取内网地址({host} → {ip})。"
                "这个接口只允许抓公网页面。",
            )


def _normalize(url: str) -> str:
    """校验并规范化 URL, 不合法直接抛。"""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in {"http", "https"}:
        raise FetchError("只支持 http / https 开头的完整地址")
    if parts.username or parts.password:
        raise FetchError("地址里不能带账号密码")
    if not parts.hostname:
        raise FetchError("网站地址缺少主机名")
    _guard_host(parts.hostname)
    return urlunsplit(parts)


def _decode(body: bytes, content_type: str) -> str:
    """按 charset → utf-8 → gb18030 的顺序解码(国内站点常是 GBK 系)。"""
    charset = ""
    if "charset=" in content_type.lower():
        charset = content_type.lower().split("charset=", 1)[1].split(";")[0].strip(" \"'")
    for enc in [charset, "utf-8", "gb18030"]:
        if not enc:
            continue
        try:
            return body.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", errors="replace")


def _client() -> httpx.Client:
    """HTTP 客户端工厂 —— 抽出来是为了测试能塞 MockTransport。"""
    return httpx.Client(timeout=TIMEOUT_S, follow_redirects=False)


def _http_get(url: str) -> tuple[int, str, bytes, str]:
    """单跳 GET(不自动跟随重定向)。返回 (状态码, content-type, 内容, location)。"""
    with _client() as client:
        with client.stream("GET", url, headers={"User-Agent": _UA}) as resp:
            location = resp.headers.get("location", "")
            content_type = resp.headers.get("content-type", "")
            if resp.is_redirect:
                resp.close()
                return resp.status_code, content_type, b"", location
            chunks: list[bytes] = []
            size = 0
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise FetchError(
                        f"页面超过 {MAX_BYTES // 1024 // 1024}MB 上限, 已中断 —— "
                        "抓取模式是给数据接口/小页面用的",
                    )
                chunks.append(chunk)
            return resp.status_code, content_type, b"".join(chunks), ""


def fetch(url: str, *, force: bool = False) -> dict:
    """抓一次原文。TTL 内直接回缓存; 失败抛 FetchError(不留缓存)。"""
    target = _normalize(url)
    now = time.time()
    if not force:
        with _lock:
            hit = _cache.get(target)
        if hit and (now - hit[0]) < _TTL_S:
            return dict(hit[1], cached=True)

    current = target
    for hop in range(MAX_REDIRECTS + 1):
        try:
            status, content_type, body, location = _http_get(current)
        except FetchError:
            raise
        except httpx.HTTPError as e:
            raise FetchError(f"抓取失败: {type(e).__name__}: {e}") from e
        if not location:
            break
        if hop >= MAX_REDIRECTS:
            raise FetchError(f"重定向超过 {MAX_REDIRECTS} 跳, 已放弃")
        # 逐跳重新校验 —— 302 到内网是典型的 SSRF 绕过手法
        nxt = httpx.URL(current).join(location)
        current = _normalize(str(nxt))
    else:  # pragma: no cover - 循环必然从 break 或 raise 退出
        raise FetchError("重定向处理异常")

    text = _decode(body, content_type)
    result = {
        "ok": True,
        "status": status,
        "url": current,
        "content_type": content_type,
        "bytes": len(body),
        "text": text,
        "fetched_at": now,
        "cached": False,
    }
    with _lock:
        _cache[target] = (now, result)
        if len(_cache) > 32:      # 用户就配一两个地址, 这里只防病态增长
            _cache.clear()
            _cache[target] = (now, result)
    return dict(result)
