"""[R269] 读前端源码的共用工具 —— 给那几组「扫前端」的守卫用。

这个仓库里有好几组测试是**扫前端源码**来钉住版面与接线的(决策台列序、消息面折叠、
导入弹窗分队映射、前端脱敏……)。它们都需要同一件事: 把注释剥掉再断言。

**为什么值得单独拿出来**: 这个仓库里已经发生过五次「断言被自己的注释喂饱」——
断言里查的标识符, 正好也写在我为这段代码加的说明文字里, 于是测试永远绿。第一版
修法是"跳过以 // 或 {/* 开头的行", 那个修法对跨行的 `{/* … */}` **只剥了首行**,
坑还在。函数复制到第四个文件的时候, 等于把这个坑也复制了四份。

所以: 一处实现, 一处修。
"""
from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
SRC = FRONTEND / "src"


def read_src(rel: str) -> str:
    """读 `frontend/src` 下的一个文件(原样, 含注释)。"""
    return (SRC / rel).read_text(encoding="utf-8")


def code_lines(text: str) -> str:
    """剥掉注释, 只留代码。

    **按块剥, 不是按行首剥。** 只看行首的话, 跨行 `{/* … */}` 里除第一行以外的说明
    文字全都留在结果里, 断言照样会被自己的注释喂饱。行内注释(`code() // 说明`)也要
    剥 —— 说明就写在代码同一行的情况同样常见。
    """
    out: list[str] = []
    in_block = False
    for raw in text.splitlines():
        line = raw
        while True:
            if in_block:
                end = line.find("*/")
                if end < 0:
                    line = ""
                    break
                line = line[end + 2:]
                in_block = False
                continue
            start = line.find("/*")
            if start < 0:
                break
            head = line[:start].rstrip().removesuffix("{")
            end = line.find("*/", start + 2)
            if end < 0:
                line = head
                in_block = True
                break
            line = head + line[end + 2:].removeprefix("}")
        # 行内 `//` —— 只在它不在字符串里时才算注释。这里用一个够用的近似:
        # 前面出现过奇数个引号就当它在字符串里(URL 里的 `//` 正是这种情况)。
        idx = line.find("//")
        while idx >= 0:
            prefix = line[:idx]
            if prefix.count('"') % 2 == 0 and prefix.count("'") % 2 == 0 \
                    and prefix.count("`") % 2 == 0:
                line = prefix
                break
            idx = line.find("//", idx + 2)
        stripped = line.strip()
        if not stripped:
            continue
        out.append(line)
    return "\n".join(out)


def code_of(rel: str) -> str:
    """`read_src` + `code_lines` 的常用组合。"""
    return code_lines(read_src(rel))
