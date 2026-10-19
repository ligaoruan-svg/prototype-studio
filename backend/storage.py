from __future__ import annotations

import json
import shutil
import uuid
import base64
import re
import time
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
from .paths import DATA_DIR
DATA_ROOT = DATA_DIR / "projects"
DATA_ROOT.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


KEEP_VERSIONS = 100


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
def create_project(name: str, style: str | None = None) -> dict[str, Any]:
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
    if style:
        meta["style"] = style   # 这个项目用哪套风格，见 skills.style_of
    save_meta(meta)
    return meta


@_locked
def set_style(project_id: str, style: str) -> None:
    meta = load_meta(project_id)
    meta["style"] = style
    meta["updated_at"] = now_iso()
    save_meta(meta)


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


# 发消息时带的截图：以前只在发送那一刻显示，存进对话的只有文字，刷新或做完就没了。
# 现在存成文件跟着这条消息走，一直留着（只在彻底删除项目时一起删）
CHAT_IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
CHAT_IMAGE_MAX = 8 * 1024 * 1024


def save_chat_image(project_id: str, data_url: str) -> str:
    m = re.match(r"data:(image/(?:png|jpeg|webp));base64,(.+)$", str(data_url or ""), re.S)
    if not m:
        return ""
    try:
        data = base64.b64decode(m.group(2), validate=True)
    except (ValueError, TypeError):
        return ""
    if not data or len(data) > CHAT_IMAGE_MAX:
        return ""
    image_id = safe_id("img")
    folder = project_dir(project_id) / "chat_images"
    folder.mkdir(parents=True, exist_ok=True)
    write_atomic(folder / (image_id + CHAT_IMAGE_TYPES[m.group(1)]), data)
    return image_id


def chat_image_path(project_id: str, image_id: str) -> Path | None:
    if not re.fullmatch(r"img_[a-f0-9]{10}", image_id or ""):
        raise ValueError("无效的图片编号")
    for suffix in CHAT_IMAGE_TYPES.values():
        path = project_dir(project_id) / "chat_images" / (image_id + suffix)
        if path.exists():
            return path
    return None


def shot_path(project_id: str, ann_id: str) -> Path:
    if not re.fullmatch(r"ann_[\w-]+", ann_id):
        raise ValueError("无效的评论编号")
    return project_dir(project_id) / "shots" / f"{ann_id}.jpg"


def resolve_link(meta: dict[str, Any], href: str, page_id: str = "") -> str | None:
    """原型里的链接（a.html、../orders/index.html）指向项目里的哪一页"""
    import posixpath
    clean = href.split("#",1)[0].split("?",1)[0]
    norm = lambda p: posixpath.normpath(p).lstrip("./") if p else ""
    candidates = [norm(clean)]
    if page_id:
        try:
            current = get_page(meta, page_id)
            candidates.insert(0, norm(posixpath.join(posixpath.dirname(current["path"]), clean)))
        except KeyError:
            pass
    pages = [p for p in meta.get("pages", []) if not p.get('deleted_at')]
    # 先按完整路径找（相对当前页优先）；orders/index.html 和 users/index.html 同名，只按文件名找会跳错
    for cand in candidates:
        for page in pages:
            if page["path"] == cand:
                return page["id"]
    # 路径对不上时才按文件名，而且只在唯一一个同名页面时才算
    names = [p for p in pages if any(posixpath.basename(p["path"]) == posixpath.basename(c) for c in candidates if c)]
    return names[0]["id"] if len(names) == 1 else None


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
    gone = [a.get("id", "") for a in meta.get("annotations", []) if a.get("page_id") == page_id and a.get("shot")]
    meta["annotations"] = [a for a in meta.get("annotations", []) if a.get("page_id") != page_id]
    meta["updated_at"] = now_iso()
    save_meta(meta)
    for ann_id in gone:   # 这一页评论的缩略图一起删
        try:
            shot_path(project_id, ann_id).unlink()
        except (OSError, ValueError):
            pass
    if not re.fullmatch(r"page_[\w-]+", page_id):
        return
    for folder in (pdir / "versions" / page_id, pdir / "expand" / page_id, pdir / "changes" / page_id):
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
    # 历史版本保留第一版 + 最近 KEEP_VERSIONS 版：每版是一整页副本，以前只增不删
    if len(versions) > KEEP_VERSIONS + 1:
        drop = versions[1:len(versions) - KEEP_VERSIONS]
        versions[:] = versions[:1] + versions[len(versions) - KEEP_VERSIONS:]
        for old in drop:
            try:
                (project_dir(project_id) / old["file"]).unlink()
            except (OSError, KeyError):
                pass
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
    # 画笔评论的缩略图（带红圈的那块页面）：存成单独的图片文件，project.json 里只记一个标记
    shot = str(payload.get("shot") or "")
    if shot.startswith("data:image/jpeg;base64,") and len(shot) < 400_000:
        import base64
        try:
            data = base64.b64decode(shot.split(",", 1)[1], validate=True)
            folder = project_dir(project_id) / "shots"
            folder.mkdir(parents=True, exist_ok=True)
            write_atomic(folder / f"{ann['id']}.jpg", data)
            ann["shot"] = True
        except (ValueError, OSError):
            pass
    meta.setdefault("annotations", []).append(ann)
    meta["updated_at"] = now_iso()
    save_meta(meta)
    return ann


@_locked
def delete_annotation(project_id: str, ann_id: str) -> None:
    meta = load_meta(project_id)
    meta["annotations"] = [a for a in meta.get("annotations", []) if a.get("id") != ann_id]
    save_meta(meta)
    try:
        shot_path(project_id, ann_id).unlink()
    except (OSError, ValueError):
        pass



CHAT_DIFF_LINES = 80


def compact_diff(diff):
    """存进对话记录的改动只留前 80 行、每行 240 字。以前整份 diff（最多 400 行 × 1600 字）跟着对话存进
    project.json 保留很多条，文件能涨到几十 MB，而项目列表、每张预览图片都要整份读它"""
    hunks, left = [], CHAT_DIFF_LINES
    for hunk in diff.get('hunks', []):
        if left <= 0: break
        lines = [{**line, 'text': str(line.get('text', ''))[:240]} for line in hunk.get('lines', [])[:left]]
        left -= len(lines)
        hunks.append({**hunk, 'lines': lines})
    shown = sum(len(h['lines']) for h in hunks)
    total = sum(len(h.get('lines', [])) for h in diff.get('hunks', []))
    return {**diff, 'hunks': hunks, 'truncated': bool(diff.get('truncated')) or shown < total}


# 对话框里显示、project.json 里存的条数。给 AI 的上下文只取最近 10 条（conversation.history_context），
# 所以这里多存不多花 token；全部历史另外记在 chat_log.jsonl
CHAT_KEEP = 200


@_locked
def append_chat(project_id: str, role: str, content: str, extra: dict[str, Any] | None = None) -> None:
    meta = load_meta(project_id)
    # seq 一直往上数：project.json 里只留最近 CHAT_KEEP 条，记忆整理靠它知道「上次整理到哪了」
    meta["chat_seq"] = int(meta.get("chat_seq", 0) or 0) + 1
    entry = {"id": safe_id("msg"), "role": role, "content": content, "created_at": now_iso(), "seq": meta["chat_seq"]}
    if extra:
        entry.update(extra)
    meta.setdefault("chat", []).append(entry)
    meta["chat"] = meta["chat"][-CHAT_KEEP:]
    for item in meta["chat"]:   # 旧版本存进来的整份 diff 顺手瘦身
        if isinstance(item.get("diff"), dict) and sum(len(h.get("lines", [])) for h in item["diff"].get("hunks", [])) > CHAT_DIFF_LINES:
            item["diff"] = compact_diff(item["diff"])
    meta["updated_at"] = now_iso()
    save_meta(meta)
    # 完整的对话另外按行追加一份：更早的也能被「查以前的对话」找到，截图编号也记着
    try:
        page = next((p.get("title", "") for p in meta.get("pages", []) if p["id"] == entry.get("page_id")), "")
        record = {"seq": entry["seq"], "role": role, "content": str(content)[:2000], "created_at": entry["created_at"], "page": page}
        if entry.get("image"):
            record["image"] = entry["image"]
        line = json.dumps(record, ensure_ascii=False)
        with open(project_dir(project_id) / "chat_log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def search_chat_log(project_id: str, query: str, limit: int = 6) -> list[dict[str, Any]]:
    words = [w for w in re.split(r"\s+", str(query or "").strip()) if w][:5]
    path = project_dir(project_id) / "chat_log.jsonl"
    if not words or not path.exists():
        return []
    hits = []
    for raw in path.read_text("utf-8", errors="replace").splitlines():
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        text = str(row.get("content") or "")
        if all(w.lower() in text.lower() for w in words):
            at = text.lower().find(words[0].lower())
            hits.append({**row, "content": text[max(0, at - 80): at + 220]})
    return hits[-limit:][::-1]


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
    root = _expand_dir(project_id, page_id)
    write_atomic(root / "routes.json", json.dumps({"routes": clean, "v": int(version or 0)}, ensure_ascii=False))
    # 页面清单变了（菜单删了某页）：清单外、而且一天没碰过的展开结果删掉。每次打开都要整份读一遍它们
    keep = {_route_file(r["hash"]) for r in clean} | {_route_file("")}
    if clean:
        for path in root.glob("*.json"):
            if path.name in ("routes.json", "overrides.json") or path.name in keep:
                continue
            try:
                if time.time() - path.stat().st_mtime > 86400:
                    path.unlink()
            except OSError:
                pass


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
    root = _expand_dir(project_id, page_id)    # 先验编号（不许拿来穿目录）
    get_page(load_meta(project_id), page_id)   # 页面已经删了（展开还在后台跑完晚到）就别再把目录建回来
    body = json.dumps({"route": route[:200], "hash": version_hash[:80], "result": result}, ensure_ascii=False)
    if len(body) > 8_000_000:
        raise ValueError("这个页面的展开结果太大，没有保存")
    write_atomic(root / _route_file(route), body)


RUN_TRACES_KEEP = 30


def save_run_trace(project_id: str, trace: dict) -> None:
    """一次运行的过程（每轮调了什么工具、成没成、token）记到 runs/ 下，只留最近 30 次。撞到轮次上限、绕路时回头查。"""
    folder = project_dir(project_id) / "runs"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = folder / f"{stamp}-{uuid.uuid4().hex[:6]}.json"
    path.write_text(json.dumps({"at": stamp, **trace}, ensure_ascii=False, indent=1), encoding="utf-8")
    for old in sorted(folder.glob("*.json"))[:-RUN_TRACES_KEEP]:
        try:
            old.unlink()
        except OSError:
            pass


def save_failed_candidate(project_id: str, html: str, errors: list, reason: str = "") -> None:
    """运行检查没过的候选版本：连同报错存到 runs/，最多留 10 份。"""
    folder = project_dir(project_id) / "runs"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    (folder / f"failed-{stamp}.html").write_text(html, encoding="utf-8")
    (folder / f"failed-{stamp}.json").write_text(json.dumps({"errors": errors, "reason": reason[:200]}, ensure_ascii=False, indent=1), encoding="utf-8")
    for old in sorted(folder.glob("failed-*.html"))[:-10]:
        for p in (old, old.with_suffix(".json")):
            try:
                p.unlink()
            except OSError:
                pass
