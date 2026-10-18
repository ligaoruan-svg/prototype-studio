"""原子写文件。

data/ 下的 project.json 装着页面清单、版本记录、撤销栈、标注和记忆——
原地覆写时进程被杀、磁盘写满或断电，都会留下一个被截断的 JSON，
整个项目就此打不开。页面源码同理，那是用户真正的东西。

所以这里一律先写同目录下的临时文件，fsync 落盘，再 os.replace 换上去。
os.replace 在 POSIX 上是原子的：任何时刻读到的要么是完整的旧版，要么是完整的新版，
不存在半截的中间态。失败时临时文件会被清掉，原文件一个字节都没动过。
"""
from __future__ import annotations

import os
import secrets
import threading
import time
from pathlib import Path

TMP_PREFIX = ".ptw-tmp."


def write_atomic(path, data: str | bytes, mode: int | None = None) -> None:
    path = Path(path)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    path.parent.mkdir(parents=True, exist_ok=True)
    # 临时文件必须和目标同目录：os.replace 跨文件系统会失败，而 /tmp 常是另一个盘。
    # 文件名里带上进程号 + 线程号 + 随机串：同一进程的两个线程同时写同一个文件时，不会共用一个临时文件
    tmp = path.parent / f"{TMP_PREFIX}{path.name}.{os.getpid()}.{threading.get_ident()}-{secrets.token_hex(4)}.tmp"
    _sweep(path)
    try:
        if mode is None:
            # os.replace 会连权限一起换掉。文件已存在就沿用它原来的权限，
            # 免得把用户自己 chmod 过的设置悄悄改回去；新文件才用 0600。
            try:
                mode = os.stat(path).st_mode & 0o777
            except OSError:
                mode = 0o600
        # O_BINARY：Windows 上不加会按文本模式写，换行被改成 \r\n
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), mode)
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, mode)              # os.open 会被 umask 削权，这里补回来
        _replace(tmp, path)
        _sync_dir(path.parent)           # 让这次改名本身也落盘
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _replace(tmp: Path, path: Path) -> None:
    """Windows 上目标文件正被别的线程读着时 os.replace 会报「拒绝访问」，稍等重试几次"""
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 9:
                raise
            time.sleep(0.05 * (attempt + 1))


def _sync_dir(directory: Path) -> None:
    """目录项的 fsync；某些平台不支持，失败不影响已经换上去的文件。"""
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _sweep(path: Path) -> None:
    """清掉同一目标遗留的临时文件。

    进程被 SIGKILL 或断电时，except 分支根本没机会跑，临时文件就留在 data/ 里了。
    这些文件永远不会被读，但会一直堆积。下次写同一个目标时顺手扫掉：
    只认自己的前缀和这个文件名，不碰别人的东西；扫不掉也不影响这次写入。
    """
    stem = f"{TMP_PREFIX}{path.name}."
    try:
        for leftover in path.parent.iterdir():
            if leftover.name.startswith(stem) and leftover.name.endswith(".tmp") and _abandoned(leftover, stem):
                try:
                    leftover.unlink()
                except OSError:
                    pass
    except OSError:
        pass


def _abandoned(leftover: Path, stem: str) -> bool:
    """别的进程留下的（进程早没了），或者放了十分钟以上的，才算没人要的。
    本进程别的线程正在写的临时文件不能删，否则它换上去的时候会找不到文件。"""
    pid = leftover.name[len(stem):].split(".", 1)[0]
    if pid != str(os.getpid()):
        return True
    try:
        return time.time() - leftover.stat().st_mtime > 600
    except OSError:
        return False
