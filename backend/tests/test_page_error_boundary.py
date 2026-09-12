"""[R321] 防白屏 —— 一页渲染崩了只坏这一页。

这组守卫扫前端源码, 钉住三件事:

  1. Layout 的正文区被 `PageErrorBoundary` 包着, 而且边界在 Suspense **外面**
     (lazy chunk 拿不到时错是从 Suspense 里抛出来的, 边界在里面接不住);
  2. 边界按路径复位 —— 换页即重来, 不然点到哪一页都还是那张错误卡;
  3. 三条顶层路由各挂 `errorElement`, 接壳自己崩与 404。

全部走 `code_of`(剥掉注释再断言)—— 这个仓库里"断言被自己的注释喂饱"已经发生过
五次。
"""
from __future__ import annotations

import re

from tests.frontend_source import code_of

BOUNDARY = "components/PageErrorBoundary.tsx"
LAYOUT = "components/Layout.tsx"
ROUTER = "router.tsx"


# ---------- Layout 接线 ----------

def _main_block() -> str:
    """Layout 里 `<motion.main` 到 `</motion.main>` 那一段 —— 正文区。"""
    code = code_of(LAYOUT)
    start = code.index("<motion.main")
    end = code.index("</motion.main>", start)
    return code[start:end]


def test_R321_正文区被边界包着且边界在_Suspense_外面():
    main = _main_block()
    b_open = main.index("<PageErrorBoundary")
    s_open = main.index("<Suspense", b_open)
    outlet = main.index("<Outlet />", s_open)
    s_close = main.index("</Suspense>", outlet)
    b_close = main.index("</PageErrorBoundary>", s_close)
    assert b_open < s_open < outlet < s_close < b_close


def test_R321_边界按路径复位():
    main = _main_block()
    tag = main[main.index("<PageErrorBoundary"):]
    tag = tag[:tag.index(">")]
    assert "resetKey={location.pathname}" in tag, \
        "resetKey 必须是 location.pathname —— 换页就得放手让新页渲染"


def test_R321_Layout_真的_import_了边界():
    code = code_of(LAYOUT)
    assert re.search(r"import \{[^}]*\bPageErrorBoundary\b[^}]*\} from '@/components/PageErrorBoundary'", code)


# ---------- 边界本体 ----------

def test_R321_边界是真的_ErrorBoundary():
    code = code_of(BOUNDARY)
    cls = code[code.index("class PageErrorBoundary"):]
    assert "static getDerivedStateFromError" in cls
    assert "componentDidCatch" in cls


def test_R321_resetKey_一变就清错误():
    code = code_of(BOUNDARY)
    cls = code[code.index("class PageErrorBoundary"):]
    upd = cls[cls.index("componentDidUpdate"):]
    upd = upd[:upd.index("render()")]
    assert "prev.resetKey !== this.props.resetKey" in upd
    assert "setState({ error: null })" in upd


def test_R321_没错时原样渲染子树_有错时给错误卡():
    code = code_of(BOUNDARY)
    cls = code[code.index("class PageErrorBoundary"):]
    render = cls[cls.index("render()"):]
    assert "if (this.state.error === null) return this.props.children" in render
    assert "<ErrorCard" in render
    assert "onRetry=" in render, "边界那一层要能原地重试 —— 它有可回退的树"


def test_R321_错误卡两个出口_刷新与重试():
    code = code_of(BOUNDARY)
    card = code[code.index("export function ErrorCard"):code.index("interface Props")]
    assert "window.location.reload()" in card
    assert "刷新页面" in card
    assert "重试" in card
    assert 'role="alert"' in card


def test_R321_部署后的旧_chunk_单独说_刷新就好():
    code = code_of(BOUNDARY)
    fn = code[code.index("export function isStaleChunkError"):code.index("function describe")]
    for needle in ("ChunkLoadError", "dynamically imported module", "Loading chunk"):
        assert needle in fn, f"少认了一种旧 chunk 报错: {needle}"
    card = code[code.index("export function ErrorCard"):code.index("interface Props")]
    assert "isStaleChunkError(error)" in card
    assert "页面代码已更新" in card


def test_R321_路由级错误页认得_404():
    code = code_of(BOUNDARY)
    page = code[code.index("export function RouteErrorPage"):]
    assert "useRouteError()" in page
    assert "isRouteErrorResponse(err) && err.status === 404" in page
    assert "没有这一页" in page
    assert 'to="/today"' in page, "整页错误没有壳, 得给一条回家的路"


# ---------- router ----------

def test_R321_三条顶层路由各挂_errorElement():
    code = code_of(ROUTER)
    body = code[code.index("createBrowserRouter(["):]
    for path in ("'/onboarding'", "'/login'"):
        line = next(l for l in body.splitlines() if f"path: {path}" in l)
        assert "errorElement: <RouteErrorPage />" in line, f"{path} 没挂 errorElement"
    root = body[body.index("path: '/',"):body.index("children: [")]
    assert "errorElement: <RouteErrorPage />" in root, "根路由没挂 errorElement —— 壳自己崩了没人接"


def test_R321_router_真的_import_了错误页():
    code = code_of(ROUTER)
    assert "import { RouteErrorPage } from './components/PageErrorBoundary'" in code
