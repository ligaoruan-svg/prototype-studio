"""项目：新建（选风格）、导入、列表、回收站、改名、删除、换风格"""
from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import skills, storage, transactions
from ..agent import is_fresh_shell
from ..paths import APP_ROOT as ROOT
from ..safety import to_utf8, zip_member_ok

router = APIRouter()


class NewProjectIn(BaseModel):
    name: str = "未命名原型"
    style: str = "none"   # builtin:简洁后台 / mine:文件夹名 / none，见 skills.style_of


class StyleIn(BaseModel):
    style: str


class RenameIn(BaseModel):
    name: str


class RestoreItemIn(BaseModel):
    project_id: str
    page_id: str = ""


@router.put("/api/projects/{project_id}/style")
def set_project_style(project_id: str, body: StyleIn):
    try:
        style = skills.check_style(body.style)
        with transactions.LOCK:
            storage.set_style(project_id, style)
            swapped = _swap_blank_pages(project_id, style)
    except FileNotFoundError:
        raise HTTPException(404, "项目不存在")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "style": style, "swapped": swapped}


def _swap_blank_pages(project_id: str, style: str) -> int:
    """换风格时，还没写内容的页面（空外壳、空白骨架）顺手换成新风格的样子：里面没东西可丢，
    不换的话页面还是旧风格的外壳，AI 却按新风格的规矩写，两头对不上。写过内容的页面一律不动"""
    meta = storage.load_meta(project_id)
    blank = _starter_html(meta["name"], "none")
    fresh = _starter_html(meta["name"], style)
    count = 0
    for page in meta["pages"]:
        if page.get("deleted_at"):
            continue
        source = storage.read_page(project_id, page["id"])
        if source != fresh and (is_fresh_shell(source) or source == blank):
            storage.write_page(project_id, page["id"], fresh, "换风格：页面还是空的，换成新风格的样子")
            transactions.invalidate(project_id, page["id"])
            count += 1
    return count


def _starter_html(name: str, style: str) -> str:
    """新项目的第一页：选了带外壳的风格就直接是那套外壳（打开就看得到样子），否则是通用的空白骨架"""
    import html as html_lib
    from .. import skill_digest
    found = skill_digest.find_shell({"style": style})
    if found:
        shell = found[2]
        shell = re.sub(r"<title>[^<]*</title>", lambda _: f"<title>{html_lib.escape(name)}</title>", shell, count=1)
        js_name = json.dumps(name, ensure_ascii=False).replace("<", "\\u003c")
        return shell.replace("const APP_NAME='示例系统';", f"const APP_NAME={js_name};", 1)
    html = (ROOT / "sample" / "starter.html").read_text('utf-8')
    return html.replace('新原型', html_lib.escape(name))


@router.post("/api/projects/new")
def new_project(body: NewProjectIn):
    try:
        style = skills.check_style(body.style)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    name = body.name.strip()[:80] or "未命名原型"
    html = _starter_html(name, style)   # 先备好第一页：读不到就别建出一个空项目
    project = storage.create_project(name, style)
    (storage.project_dir(project['id']) / 'source' / 'index.html').write_text(html, 'utf-8')
    storage.add_page(project['id'], 'index.html', project['name'])
    return storage.load_meta(project['id'])


@router.get("/api/projects")
def projects():
    return storage.list_projects()


ZIP_MAX_TOTAL = 300 * 1024 * 1024   # 解压后最多这么大（防压缩炸弹把磁盘写满）
ZIP_MAX_FILES = 3000


def _safe_extract(zf: zipfile.ZipFile, target: Path):
    infos = [i for i in zf.infolist() if zip_member_ok(i.filename)]
    if len(infos) > ZIP_MAX_FILES or sum(i.file_size for i in infos) > ZIP_MAX_TOTAL:
        raise HTTPException(400, f"压缩包太大：最多 {ZIP_MAX_FILES} 个文件、解压后 {ZIP_MAX_TOTAL // 1024 // 1024}MB")
    root = target.resolve()
    for info in infos:
        out = target.joinpath(*PurePosixPath(info.filename).parts)
        if root not in out.resolve().parents and out.resolve() != root:
            continue
        if info.is_dir():
            out.mkdir(parents=True, exist_ok=True)
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)


@router.post("/api/projects/upload")
async def upload_project(file: UploadFile = File(...), name: str = Form("")):
    filename = file.filename or "prototype.html"
    raw = await file.read()
    return await run_in_threadpool(_import_upload, filename, raw, name)


def _import_upload(filename: str, raw: bytes, name: str):
    suffix = Path(filename).suffix.lower()
    # 先验文件、再建项目：以前传错文件（.txt、坏 zip、zip 里没有网页）会在列表里留下一个空项目
    if suffix not in {".html", ".htm", ".zip"}:
        raise HTTPException(400, "目前支持 HTML 页面或包含多页面的 ZIP")
    archive = None
    if suffix == ".zip":
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as exc:
            raise HTTPException(400, "ZIP 文件损坏") from exc
        if not any(zip_member_ok(i.filename) and PurePosixPath(i.filename).suffix.lower() in {".html", ".htm"}
                   for i in archive.infolist()):
            raise HTTPException(400, "ZIP 中没有 HTML 页面")
    project = storage.create_project(name or Path(filename).stem, "none")   # 导入的原型默认不套风格，保持原样
    source = storage.project_dir(project["id"]) / "source"
    try:
        if archive is None:
            target = source / Path(filename).name
            target.write_bytes(to_utf8(raw))
            storage.add_page(project["id"], target.name, Path(filename).stem)
        else:
            with archive:
                _safe_extract(archive, source)
            for p in sorted(p for p in source.rglob("*") if p.suffix.lower() in {".html", ".htm"}):
                p.write_bytes(to_utf8(p.read_bytes()))
                storage.add_page(project["id"], str(p.relative_to(source)).replace("\\", "/"), p.stem)
    except BaseException:
        shutil.rmtree(storage.project_dir(project["id"]), ignore_errors=True)
        raise
    return storage.load_meta(project["id"])


@router.get("/api/projects/{project_id}")
def get_project(project_id: str):
    try:
        meta = storage.load_meta(project_id)
        meta['pages'] = [p for p in meta['pages'] if not p.get('deleted_at')]
        meta['style'] = skills.style_of(meta)
        for page in meta['pages']:
            entries = transactions.undo_entries(page)
            page['undo_count'] = len(entries)
            page['last_undo_id'] = entries[-1]['id'] if entries else ''
            # Pages saved before the unified timeline have no edit_history; their
            # version count is the honest lower bound, so never report fewer.
            page['modification_count'] = max(len(page.get('edit_history', [])), int(page.get('version', 1)) - 1)
        return meta
    except FileNotFoundError:
        raise HTTPException(404, "项目不存在")


@router.get("/api/trash")
def list_trash():
    return storage.list_trash()


@router.post("/api/trash/restore")
def restore_item(body: RestoreItemIn):
    try:
        with transactions.LOCK:
            storage.restore_item(body.project_id, body.page_id)
        return {"ok": True}
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.post("/api/trash/purge")
def purge_item(body: RestoreItemIn):
    try:
        with transactions.LOCK:
            storage.purge_item(body.project_id, body.page_id)
            transactions.invalidate(body.project_id, body.page_id)
        return {"ok": True}
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.post("/api/trash/empty")
def empty_trash():
    with transactions.LOCK:
        items = storage.list_trash()
        count = storage.purge_all()
        for item in items:
            transactions.invalidate(item["project_id"], item.get("page_id", ""))
    return {"ok": True, "count": count}


@router.patch("/api/projects/{project_id}")
def rename_project(project_id: str, body: RenameIn):
    try:
        with transactions.LOCK:
            storage.rename_item(project_id, body.name)
        return {"ok": True}
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.patch("/api/projects/{project_id}/pages/{page_id}")
def rename_page(project_id: str, page_id: str, body: RenameIn):
    try:
        with transactions.LOCK:
            storage.rename_item(project_id, body.name, page_id)
        return {"ok": True}
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    try:
        with transactions.LOCK:
            storage.trash_item(project_id)
            transactions.invalidate(project_id)
        return {"ok": True, "recoverable": True}
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@router.delete("/api/projects/{project_id}/pages/{page_id}")
def delete_page(project_id: str, page_id: str):
    try:
        with transactions.LOCK:
            storage.trash_item(project_id, page_id)
            transactions.invalidate(project_id, page_id)
        return {"ok": True, "recoverable": True}
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))
