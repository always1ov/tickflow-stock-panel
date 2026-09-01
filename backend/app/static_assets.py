"""[fork R153] 前端静态资源直出: 长缓存 + 预压缩协商。

只管 ``/assets`` 下那些带内容 hash 的文件(Vite 产物), 不碰任何 API 路径 ——
API 响应的压缩由各端点自己决定(上游 bc9461d 给分时/日K 批量做了可选 gzip),
这里不加全局中间件, 免得把 SSE 流也裹进缓冲里。

两件事:
1. ``Cache-Control: immutable`` —— 文件名带 hash, 内容变则名变, 所以可以让浏览器
   一年内**连问都不问**。原来 StaticFiles 不带缓存头, 浏览器每次打开都要对每个
   文件发一次条件请求(304 也是一次往返), 首屏十几个文件就是十几次往返。
   index.html 仍由 spa_fallback 以 no-store 直出, 所以发新版本不受影响。
2. 预压缩直出 —— 构建时(``frontend/scripts/compress-dist.mjs``)已生成同名 ``.br``
   / ``.gz``, 这里按 Accept-Encoding 直接发那份, 不在请求路径上压缩, 零 CPU。
   没有对应压缩文件(如 woff2 本身已压缩)就原样发, 行为与原来完全一致。
"""
from __future__ import annotations

import mimetypes
import os
from os import PathLike

from starlette.datastructures import Headers
from starlette.responses import FileResponse, Response
from starlette.staticfiles import NotModifiedResponse, StaticFiles
from starlette.types import Scope

IMMUTABLE = "public, max-age=31536000, immutable"
# 优先级顺序: br 更小, 客户端两者都接受时先给 br
_ENCODINGS: tuple[tuple[str, str], ...] = (("br", ".br"), ("gzip", ".gz"))


def accepted_encodings(header: str) -> set[str]:
    """``gzip, deflate, br;q=1.0`` → {"gzip", "deflate", "br"}; q=0 的剔除。"""
    out: set[str] = set()
    for part in header.split(","):
        token, _, params = part.strip().partition(";")
        token = token.strip().lower()
        if not token:
            continue
        q = 1.0
        for p in params.split(";"):
            k, _, v = p.strip().partition("=")
            if k.strip().lower() == "q":
                try:
                    q = float(v)
                except ValueError:
                    q = 0.0
        if q > 0:
            out.add(token)
    return out


class HashedAssets(StaticFiles):
    """带 hash 文件名的静态目录: 长缓存 + 预压缩协商。"""

    def file_response(
        self,
        full_path: PathLike,
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        request_headers = Headers(scope=scope)
        accepted = accepted_encodings(request_headers.get("accept-encoding", ""))
        # Content-Type 一律按**原文件名**判, 发的是 .br/.gz 时也得是 text/javascript
        media_type = mimetypes.guess_type(str(full_path))[0] or "application/octet-stream"
        headers = {"Cache-Control": IMMUTABLE, "Vary": "Accept-Encoding"}

        path: PathLike | str = full_path
        stat = stat_result
        for encoding, ext in _ENCODINGS:
            if encoding not in accepted:
                continue
            candidate = f"{os.fspath(full_path)}{ext}"
            try:
                st = os.stat(candidate)
            except OSError:
                continue
            path, stat = candidate, st
            headers["Content-Encoding"] = encoding
            break

        response = FileResponse(
            path, status_code=status_code, headers=headers,
            media_type=media_type, stat_result=stat,
        )
        if self.is_not_modified(response.headers, request_headers):
            return NotModifiedResponse(response.headers)
        return response
