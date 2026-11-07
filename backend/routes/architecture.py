"""架构：画布上的页面树。读、存；从原型读（展开图 → 页面树，画布上还没同步的改动照旧留着，见 arch_expand.refresh_canvas）。
在画布上改结构用对话里的「架构」模式（见 arch_chat，走 agent/stream），或者直接在画布上手动改；改了的「同步到原型」在界面上拼成一段话交给 AI"""
from __future__ import annotations

import copy

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import arch_expand, architecture, storage

router = APIRouter()


class ArchIn(BaseModel):
    architecture: dict


class RefreshIn(BaseModel):
    page_id: str = ""


class AcceptIn(BaseModel):
    ids: list[str] = []


def _project(project_id: str) -> dict:
    try:
        return storage.load_meta(project_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, "项目不存在") from exc


def _page_id(meta: dict, page_id: str) -> str:
    page_id = page_id or (meta.get("pages") or [{}])[0].get("id", "")
    storage.get_page(meta, page_id)
    return page_id


def bundle(project_id: str, arch: dict | None, **extra) -> dict:
    """架构 + 检查 + 计数，再带上 base（界面拿画布和它比，就知道还有几处没同步）"""
    return {**architecture.bundle(arch), "base": architecture.load_base(project_id), **extra}


@router.get("/api/projects/{project_id}/architecture")
def get_architecture(project_id: str):
    _project(project_id)
    return bundle(project_id, architecture.load(project_id))


@router.put("/api/projects/{project_id}/architecture")
def put_architecture(project_id: str, body: ArchIn):
    _project(project_id)
    raw = dict(body.architecture or {})
    # 界面手里那份可能是梳理出来之前读的，没带 spec：别把存着的业务梳理冲掉
    if "spec" not in raw:
        stored = architecture.load(project_id) or {}
        if stored.get("spec"):
            raw["spec"] = stored["spec"]
    return bundle(project_id, architecture.save(project_id, raw))


# 从原型读：原型里新做出来的补进画布；画布上还没同步的改动（加的、删的、改名的、改字段的）照旧留着
@router.post("/api/projects/{project_id}/architecture/refresh")
def refresh(project_id: str, body: RefreshIn):
    meta = _project(project_id)
    nodes = arch_expand.expand_tree(project_id, _page_id(meta, body.page_id))
    current = architecture.load(project_id)
    if not nodes:
        return bundle(project_id, current, refreshed=False, reason="no_expand")
    arch = current or architecture.empty()
    tree, base = arch_expand.refresh_canvas(arch.get("nodes") or [], architecture.load_base(project_id), nodes)
    arch["nodes"] = tree
    arch["name"] = arch.get("name") or meta.get("name", "")
    saved = architecture.save(project_id, arch)
    architecture.save_base(project_id, base)
    return bundle(project_id, saved, refreshed=True)


# 同步到原型做完了（AI 改好了，或者说原型里本来就有）：这几处记成已同步——并进 base，就不再算「没同步」。
# 加的那些算原型里有了（不再是虚线）。原型里其实没有的，下次从原型读时会标成「原型里已经没有」
@router.post("/api/projects/{project_id}/architecture/accept")
def accept(project_id: str, body: AcceptIn):
    _project(project_id)
    arch, base = architecture.load(project_id), architecture.load_base(project_id)
    want = set(body.ids)
    if not arch or base is None or not want:
        return bundle(project_id, arch)
    ops = [op for op in arch_expand.diff(base, arch.get("nodes") or []) if (op.get("id") or op.get("node", {}).get("id")) in want]
    if not ops:
        return bundle(project_id, arch)
    added = {n.get("id") for op in ops if op["op"] == "add" for n, _, _ in arch_expand._walk([op["node"]])}
    for n, _, _ in arch_expand._walk(arch.get("nodes") or []):
        if n.get("id") in added:
            n["proto"] = n["seen"] = True
    architecture.save_base(project_id, arch_expand.replay(copy.deepcopy(base), copy.deepcopy(ops)))
    return bundle(project_id, architecture.save(project_id, arch))
