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
from pathlib import Path

TMP_PREFIX = ".ptw-tmp."


def write_atomic(path, data: str | bytes, mode: int | None = None) -> None:
    path = Path(path)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    path.parent.mkdir(parents=True, exist_ok=True)
    # 临时文件必须和目标同目录：os.replace 跨文件系统会失败，而 /tmp 常是另一个盘。
    tmp = path.parent / f"{TMP_PREFIX}{path.name}.{os.getpid()}.tmp"
    _sweep(path)
    try:
        if mode is None:
            # os.replace 会连权限一起换掉。文件已存在就沿用它原来的权限，
            # 免得把用户自己 chmod 过的设置悄悄改回去；新文件才用 0600。
            try:
                mode = os.stat(path).st_mode & 0o777
            except OSError:
                mode = 0o600
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp, mode)              # os.open 会被 umask 削权，这里补回来
        os.replace(tmp, path)
        _sync_dir(path.parent)           # 让这次改名本身也落盘
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


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
            if leftover.name.startswith(stem) and leftover.name.endswith(".tmp"):
                try:
                    leftover.unlink()
                except OSError:
                    pass
    except OSError:
        pass
