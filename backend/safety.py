"""本机服务的几道安全关：只认本机地址、压缩包条目能不能落盘、导入的网页统一成 UTF-8。
不依赖 FastAPI，单独测得到。"""
from __future__ import annotations

import re
from pathlib import PurePosixPath


def host_name(netloc: str) -> str:
    netloc = netloc.strip().lower()
    if netloc.startswith("["):
        return netloc[1:netloc.find("]")] if "]" in netloc else netloc
    return netloc.rsplit(":", 1)[0] if netloc.count(":") == 1 else netloc


def zip_member_ok(name: str) -> bool:
    """压缩包里的条目能不能落盘：不许绝对路径、..、反斜杠（Windows 上会被当成目录分隔符逃出目标文件夹）、
    盘符，也不要 macOS 打包时带的 __MACOSX 和隐藏文件"""
    if "\\" in name or re.match(r"^[A-Za-z]:", name):
        return False
    p = PurePosixPath(name)
    return not (p.is_absolute() or ".." in p.parts or any(part.startswith(("__MACOSX", ".")) for part in p.parts))


def to_utf8(raw: bytes) -> bytes:
    """导入的网页统一转成 UTF-8：以前按原字节存、按 UTF-8 读，GBK 页面第一次修改后中文全变成乱码"""
    try:
        raw.decode("utf-8")
        return raw
    except UnicodeDecodeError:
        pass
    head = raw[:4096].decode("ascii", errors="ignore")
    m = re.search(r"""charset\s*=\s*["']?([\w-]+)""", head, re.I)
    for enc in ([m.group(1)] if m else []) + ["gb18030", "big5"]:
        try:
            text = raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
        text = re.sub(r"""(charset\s*=\s*["']?)[\w-]+""", r"\g<1>utf-8", text, count=1, flags=re.I)
        return text.encode("utf-8")
    return raw
