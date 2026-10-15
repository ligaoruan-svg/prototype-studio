from __future__ import annotations

import json
import shutil
import uuid
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .atomicio import write_atomic

import functools
import threading

# project.json 是「读出来 → 改 → 整份写回」。两个请求同时这么干（比如提交修改的同时记一条意见），
# 后写的会把先写的整个盖掉：意见丢了，或者撤销记录 / 版本号丢了。所有改它的地方都排这一把锁。
# 可重入：提交流程里本来就握着它再调这里的函数。
META_LOCK = threading.RLock()


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with META_LOCK:
            return fn(*args, **kwargs)
    return wrapper

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "projects"
DATA_ROOT.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def project_dir(project_id: str) -> Path:
    if not re.fullmatch(r"p_[a-f0-9]{10}", project_id):
        raise ValueError("无效项目 ID")
    return DATA_ROOT / project_id


def meta_path(project_id: str) -> Path:
    return project_dir(project_id) / "project.json"


def load_meta(project_id: str, include_deleted: bool = False) -> dict[str, Any]:
    path = meta_path(project_id)
    if not path.exists():
        raise FileNotFoundError(project_id)
    meta = json.loads(path.read_text("utf-8"))
    if meta.get("deleted_at") and not include_deleted:
        raise FileNotFoundError("项目已在回收站中，请先恢复")
    return meta


def save_meta(meta: dict[str, Any]) -> None:
    pdir = project_dir(meta["id"])
    pdir.mkdir(parents=True, exist_ok=True)
    write_atomic(meta_path(meta["id"]), json.dumps(meta, ensure_ascii=False, indent=2))


@_locked
def create_project(name: str) -> dict[str, Any]:
    pid = safe_id("p")
    pdir = project_dir(pid)
    (pdir / "source").mkdir(parents=True)
    (pdir / "versions").mkdir(parents=True)
    meta = {
        "id": pid,
        "name": name or "未命名原型",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "pages": [],
        "annotations": [],
        "chat": [],
    }
    save_meta(meta)
    return meta


def list_projects() -> list[dict[str, Any]]:
    items = []
    for path in DATA_ROOT.iterdir():
        if not path.is_dir() or not (path / "project.json").exists():
            continue
        try:
            meta = json.loads((path / "project.json").read_text("utf-8"))
            if meta.get("deleted_at"):
                continue
            active_pages = [p for p in meta.get("pages", []) if not p.get("deleted_at")]
            items.append({
                "id": meta["id"],
                "name": meta.get("name", "未命名原型"),
                "updated_at": meta.get("updated_at", ""),
                "page_count": len(active_pages),
                "pages": [{k: p[k] for k in ("id", "title", "path", "version")} for p in active_pages],
            })
        except Exception:
            continue
    return sorted(items, key=lambda x: x.get("updated_at", ""), reverse=True)


@_locked
def add_page(project_id: str, rel_path: str, title: str | None = None) -> dict[str, Any]:
    meta = load_meta(project_id)
    page_id = safe_id("page")
    page = {
        "id": page_id,
        "path": rel_path.replace("\\", "/"),
        "title": title or Path(rel_path).stem,
        "version": 1,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "versions": [],
    }
    meta["pages"].append(page)
    meta["updated_at"] = now_iso()
    save_meta(meta)
    snapshot_version(project_id, page_id, reason="导入原型")
    return page


def get_page(meta: dict[str, Any], page_id: str) -> dict[str, Any]:
    for page in meta.get("pages", []):
        if page["id"] == page_id and not page.get("deleted_at"):
            return page
    raise KeyError(page_id)


def page_file(project_id: str, page_id: str) -> Path:
    meta = load_meta(project_id)
    page = get_page(meta, page_id)
    return project_dir(project_id) / "source" / page["path"]


@_locked
def rename_item(project_id: str, name: str, page_id: str = "") -> None:
    name = name.strip()
    if not name or len(name) > 80:
        raise ValueError("名称需为 1–80 个字符")
    meta = load_meta(project_id)
    target = get_page(meta, page_id) if page_id else meta
    target["title" if page_id else "name"] = name
    target["updated_at"] = meta["updated_at"] = now_iso()
    save_meta(meta)


@_locked
def trash_item(project_id: str, page_id: str = "") -> None:
    meta = load_meta(project_id)
    target = get_page(meta, page_id) if page_id else meta
    target["deleted_at"] = meta["updated_at"] = now_iso()
    save_meta(meta)


@_locked
def restore_item(project_id: str, page_id: str = "") -> None:
    meta = load_meta(project_id, include_deleted=True)
    if page_id:
        if meta.get("deleted_at"):
            raise ValueError("请先恢复所属项目")
        target = next((p for p in meta["pages"] if p["id"] == page_id), None)
        if target is None:
            raise KeyError("页面不存在")
    else:
        target = meta
    if not target.get("deleted_at"):
        raise ValueError("此项不在回收站中")
    target.pop("deleted_at")
    target["updated_at"] = meta["updated_at"] = now_iso()
    save_meta(meta)


# 彻底删除：只删回收站里的东西，删了就没了（项目连同它的源码副本、历史版本、展开结果一起删；
# 最初导入时你电脑上的那个文件不在这里，不受影响）
@_locked
def purge_item(project_id: str, page_id: str = "") -> None:
    meta = load_meta(project_id, include_deleted=True)
    pdir = project_dir(project_id)
    if not page_id:
        if not meta.get("deleted_at"):
            raise ValueError("只能彻底删除回收站里的项目")
        shutil.rmtree(pdir)
        return
    page = next((p for p in meta.get("pages", []) if p["id"] == page_id), None)
    if page is None:
        raise KeyError("页面不存在")
    if not page.get("deleted_at"):
        raise ValueError("只能彻底删除回收站里的页面")
    meta["pages"] = [p for p in meta["pages"] if p["id"] != page_id]
    meta["annotations"] = [a for a in meta.get("annotations", []) if a.get("page_id") != page_id]
    meta["updated_at"] = now_iso()
    save_meta(meta)
    if not re.fullmatch(r"page_[\w-]+", page_id):
        return
    for folder in (pdir / "versions" / page_id, pdir / "expand" / page_id):
        shutil.rmtree(folder, ignore_errors=True)
    # 源码副本：别的页面没在用同一个文件才删（资源图片、样式随项目留着）
    path = str(page.get("path") or "")
    if path and not any(p.get("path") == path for p in meta["pages"]):
        source = (pdir / "source" / path).resolve()
        if source.is_file() and (pdir / "source").resolve() in source.parents:
            source.unlink()


def purge_all() -> int:
    count = 0
    for item in list_trash():
        try:
            purge_item(item["project_id"], item.get("page_id", ""))
            count += 1
        except (ValueError, KeyError, FileNotFoundError):
            continue   # 所属项目已经先被删掉了
    return count


def list_trash() -> list[dict[str, Any]]:
    result = []
    for path in DATA_ROOT.iterdir():
        if not path.is_dir() or not (path / "project.json").exists():
            continue
        try:
            meta = load_meta(path.name, include_deleted=True)
            if meta.get("deleted_at"):
                result.append({"kind":"project", "project_id":meta['id'], "name":meta['name'],
                               "deleted_at":meta['deleted_at'], "page_count":len(meta.get('pages', []))})
            else:
                for page in meta.get('pages', []):
                    if page.get('deleted_at'):
                        result.append({"kind":"page", "project_id":meta['id'], "page_id":page['id'],
                                       "name":page['title'], "project_name":meta['name'], "deleted_at":page['deleted_at']})
        except (ValueError, KeyError, FileNotFoundError):
            continue
    return sorted(result, key=lambda item: item['deleted_at'], reverse=True)


def read_page(project_id: str, page_id: str) -> str:
    with page_file(project_id, page_id).open(encoding="utf-8", errors="replace", newline="") as source:
        return source.read()


@_locked
def write_page(project_id: str, page_id: str, content: str, reason: str) -> dict[str, Any]:
    meta = load_meta(project_id)
    page = get_page(meta, page_id)
    path = project_dir(project_id) / "source" / page["path"]
    write_atomic(path, content)
    page["version"] = int(page.get("version", 1)) + 1
    page["manual_edits"] = []
    page["updated_at"] = now_iso()
    meta["updated_at"] = now_iso()
    save_meta(meta)
    return snapshot_version(project_id, page_id, reason=reason)


@_locked
def snapshot_version(project_id: str, page_id: str, reason: str) -> dict[str, Any]:
    meta = load_meta(project_id)
    page = get_page(meta, page_id)
    source = project_dir(project_id) / "source" / page["path"]
    vnum = int(page.get("version", 1))
    vdir = project_dir(project_id) / "versions" / page_id
    vdir.mkdir(parents=True, exist_ok=True)
    vfile = vdir / f"v{vnum}.html"
    if source.exists():
        shutil.copy2(source, vfile)
    entry = {
        "version": vnum,
        "reason": reason,
        "created_at": now_iso(),
        "file": str(vfile.relative_to(project_dir(project_id))).replace("\\", "/"),
    }
    versions = page.setdefault("versions", [])
    versions[:] = [v for v in versions if v.get("version") != vnum]
    versions.append(entry)
    meta["updated_at"] = now_iso()
    save_meta(meta)
    return entry



def active_annotations(meta: dict[str, Any], page_id: str) -> list[dict[str, Any]]:
    return [a for a in meta.get("annotations", []) if a.get("page_id") == page_id and a.get("status", "active") == "active"]


@_locked
def add_annotation(project_id: str, page_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    meta = load_meta(project_id)
    get_page(meta, page_id)
    ann = {
        "id": safe_id("ann"),
        "page_id": page_id,
        "selector": payload.get("selector", ""),
        "tag": payload.get("tag", ""),
        "text": payload.get("text", ""),
        "outer_html": payload.get("outer_html", "")[:5000],
        "note": payload.get("note", "").strip(),
        "kind": payload.get("kind", "element"),
        "targets": payload.get("targets", [])[:16],
        "bounds": payload.get("bounds"),
        # 在弹窗里选中的：记下是哪个弹窗、怎么点开，AI 逐条处理时直接去找拼它的函数
        "in_modal": str(payload.get("in_modal") or "")[:80],
        "modal_trail": str(payload.get("modal_trail") or "")[:200],
        # 子页面（列表点进去的详情）和它所在的业务页面路由：重复的按钮、同名弹窗靠它们分清
        "in_subpage": str(payload.get("in_subpage") or "")[:80],
        "view_route": str(payload.get("view_route") or "")[:200],
        "created_at": now_iso(),
        "status": "active",
    }
    meta.setdefault("annotations", []).append(ann)
    meta["updated_at"] = now_iso()
    save_meta(meta)
    return ann


@_locked
def delete_annotation(project_id: str, ann_id: str) -> None:
    meta = load_meta(project_id)
    meta["annotations"] = [a for a in meta.get("annotations", []) if a.get("id") != ann_id]
    save_meta(meta)



@_locked
def append_chat(project_id: str, role: str, content: str, extra: dict[str, Any] | None = None) -> None:
    meta = load_meta(project_id)
    entry = {"id": safe_id("msg"), "role": role, "content": content, "created_at": now_iso()}
    if extra:
        entry.update(extra)
    meta.setdefault("chat", []).append(entry)
    meta["chat"] = meta["chat"][-40:]
    meta["updated_at"] = now_iso()
    save_meta(meta)


# ===== 展开视图的快照 =====
# 一键展开全部页面要几分钟，结果存在磁盘上：重启服务、刷新浏览器都不用重来。
# 每个页面（原型里的路由）一个文件，改了版本也先留着，前端拿它做底子同步。
def _expand_dir(project_id: str, page_id: str) -> Path:
    if not re.fullmatch(r"page_[\w-]+", page_id):
        raise ValueError("页面编号无效")
    return project_dir(project_id) / "expand" / page_id


def _route_file(route: str) -> str:
    # 路由是 #factor-list 这样的东西；文件名只留安全字符，再带一段哈希防重名
    import hashlib
    slug = re.sub(r"[^\w-]+", "_", route.lstrip("#"))[:40] or "default"
    return f"{slug}-{hashlib.sha1(route.encode('utf-8')).hexdigest()[:8]}.json"


def load_expand(project_id: str, page_id: str) -> dict[str, Any]:
    load_meta(project_id)
    root = _expand_dir(project_id, page_id)
    out: dict[str, Any] = {"routes": [], "entries": {}, "overrides": {}}
    fixes = root / "overrides.json"
    if fixes.exists():
        try:
            out["overrides"] = json.loads(fixes.read_text(encoding="utf-8")).get("overrides", {})
        except (OSError, ValueError):
            pass
    index = root / "routes.json"
    if index.exists():
        try:
            saved = json.loads(index.read_text(encoding="utf-8"))
            out["routes"] = saved.get("routes", [])
            out["routes_v"] = int(saved.get("v", 0) or 0)
        except (OSError, ValueError):
            pass
    for path in sorted(root.glob("*.json")) if root.exists() else []:
        if path.name in ("routes.json", "overrides.json"):
            continue
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            out["entries"][item["route"]] = {"hash": item.get("hash", ""), "result": item.get("result")}
        except (OSError, ValueError, KeyError):
            continue
    return out


def save_expand_routes(project_id: str, page_id: str, routes: list[dict[str, Any]], version: int = 0) -> None:
    load_meta(project_id)
    clean = []
    for r in routes[:80]:
        item = {"hash": str(r.get("hash", ""))[:200], "title": str(r.get("title", ""))[:60]}
        # 用户纠正「其实是别的业务页面」时加进来的页面：记下是哪页哪个按钮加的，撤销纠正时一起拿掉
        if r.get("added"):
            item.update({"added": str(r["added"])[:80], "from": str(r.get("from", ""))[:200]})
        clean.append(item)
    write_atomic(_expand_dir(project_id, page_id) / "routes.json", json.dumps({"routes": clean, "v": int(version or 0)}, ensure_ascii=False))


# 用户纠正过的认法：{路由: {按钮文字: "jump" | "subpage" | "tab"}}，下次展开按这个来
OVERRIDE_KINDS = {"jump", "subpage", "tab"}


def save_expand_overrides(project_id: str, page_id: str, overrides: dict[str, Any]) -> None:
    load_meta(project_id)
    clean: dict[str, dict[str, str]] = {}
    for route, items in list(overrides.items())[:80]:
        if not isinstance(items, dict):
            continue
        kept = {str(label)[:80]: kind for label, kind in list(items.items())[:200] if kind in OVERRIDE_KINDS}
        if kept:
            clean[str(route)[:200]] = kept
    write_atomic(_expand_dir(project_id, page_id) / "overrides.json", json.dumps({"overrides": clean}, ensure_ascii=False))


def save_expand_entry(project_id: str, page_id: str, route: str, version_hash: str, result: dict[str, Any]) -> None:
    load_meta(project_id)
    body = json.dumps({"route": route[:200], "hash": version_hash[:80], "result": result}, ensure_ascii=False)
    if len(body) > 8_000_000:
        raise ValueError("这个页面的展开结果太大，没有保存")
    write_atomic(_expand_dir(project_id, page_id) / _route_file(route), body)
