"""页面：源码、点选检查、直接改、撤销、退回、修改意见、展开图、预览、下载导出、候选提交"""
from __future__ import annotations

import io
import json
import mimetypes
import re
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel

from .. import config, storage, transactions
from ..bridge import build_bridge
from ..errors import error_payload
from ..experience import REGION_NAMES, element_name
from ..patcher import DEFAULT_TOKENS, PatchError, apply_operations, literal_count, locate, outline, replace_literal, style_ops, token_values

# 原型的 HTML 和 API 同源：要是有人直接在浏览器里打开预览地址，原型里的脚本就能调本机 API。
# 加上 CSP sandbox，直接打开时它也跑在隔离的沙箱里（界面里本来就是用沙箱 iframe 载入的，不受影响）
SANDBOX_CSP = {"Content-Security-Policy": "sandbox allow-scripts allow-forms allow-modals allow-popups"}

router = APIRouter()


class AnnotationIn(BaseModel):
    selector: str
    tag: str = ""
    text: str = ""
    outer_html: str = ""
    note: str
    kind: str = "element"
    targets: list[dict] = []
    bounds: dict | None = None
    in_modal: str = ""
    modal_trail: str = ""
    in_subpage: str = ""
    view_route: str = ""
    shot: str = ""   # 画笔评论的缩略图（jpeg data URL），存成文件


class EditIn(BaseModel):
    selector: str = ""
    prop: str
    value: str
    expected_hash: str
    literal: str = ""          # 脚本生成的元素改文字：它原来的字，直接换源码里那一处
    style_selector: str = ""   # 脚本生成的元素改样式：同类元素的选择器，写一条 CSS 规则
    more: dict[str, str] = {}  # 要一起改的其他样式（比如改成横向排列 = display + flex-direction），算一次修改


class CommitIn(BaseModel):
    runtime_checked: bool = False
    errors: list[str] = []


class UndoIn(BaseModel):
    change_id: str = ""


@router.post("/api/projects/{project_id}/pages/{page_id}/annotations")
def add_annotation(project_id: str, page_id: str, body: AnnotationIn):
    try:
        return storage.add_annotation(project_id, page_id, body.model_dump())
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.get("/api/projects/{project_id}/chat-images/{image_id}")
def chat_image(project_id: str, image_id: str):
    path = storage.chat_image_path(project_id, image_id)
    if not path:
        raise HTTPException(404, "图片已经清掉了")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})


@router.get("/api/projects/{project_id}/shots/{ann_id}")
def annotation_shot(project_id: str, ann_id: str):
    path = storage.shot_path(project_id, ann_id)
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


class ExpandRoutesIn(BaseModel):
    routes: list[dict] = []
    v: int = 0


class ExpandOverridesIn(BaseModel):
    overrides: dict = {}


class ExpandEntryIn(BaseModel):
    route: str = ""
    hash: str = ""
    result: dict


@router.get("/api/projects/{project_id}/pages/{page_id}/expand")
def get_expand(project_id: str, page_id: str):
    try:
        return storage.load_expand(project_id, page_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc))


@router.put("/api/projects/{project_id}/pages/{page_id}/expand/routes")
def put_expand_routes(project_id: str, page_id: str, body: ExpandRoutesIn):
    try:
        storage.save_expand_routes(project_id, page_id, body.routes, body.v)
        return {"ok": True}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@router.put("/api/projects/{project_id}/pages/{page_id}/expand/overrides")
def put_expand_overrides(project_id: str, page_id: str, body: ExpandOverridesIn):
    try:
        storage.save_expand_overrides(project_id, page_id, body.overrides)
        return {"ok": True}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@router.put("/api/projects/{project_id}/pages/{page_id}/expand/entry")
def put_expand_entry(project_id: str, page_id: str, body: ExpandEntryIn):
    try:
        storage.save_expand_entry(project_id, page_id, body.route, body.hash, body.result)
        return {"ok": True}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@router.delete("/api/projects/{project_id}/annotations/{annotation_id}")
def del_annotation(project_id: str, annotation_id: str):
    storage.delete_annotation(project_id, annotation_id)
    return {"ok": True}


@router.post("/api/projects/{project_id}/pages/{page_id}/restore/{version}")
def restore(project_id: str, page_id: str, version: int):
    try:
        meta = storage.load_meta(project_id)
        page = storage.get_page(meta, page_id)
        entry = next(v for v in page['versions'] if v['version'] == version)
        source = storage.read_page(project_id, page_id)
        restored = (storage.project_dir(project_id) / entry['file']).read_bytes().decode('utf-8', errors='replace')
        return transactions.stage(project_id, page_id, source, restored, f'恢复 v{version}', 'restore')
    except Exception as exc:
        raise HTTPException(400, str(exc))


@router.get("/api/projects/{project_id}/pages/{page_id}/download")
def download_page(project_id: str, page_id: str):
    path = storage.page_file(project_id, page_id)
    return FileResponse(path, filename=path.name, media_type="text/html")


@router.get("/api/projects/{project_id}/export")
def export_project(project_id: str):
    meta = storage.load_meta(project_id)
    deleted_paths = {p['path'] for p in meta['pages'] if p.get('deleted_at')}
    source = storage.project_dir(project_id) / "source"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in source.rglob("*"):
            if p.is_file() and p.relative_to(source).as_posix() not in deleted_paths:
                zf.write(p, str(p.relative_to(source)))
        zf.writestr("prototype-agent-project.json", json.dumps({"name":meta["name"],"exported_from":f"原型工坊 v{config.VERSION}"}, ensure_ascii=False, indent=2))
    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{project_id}.zip"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


@router.get("/api/projects/{project_id}/resolve")
def resolve_page(project_id: str, href: str, page_id: str = ""):
    meta = storage.load_meta(project_id)
    return {"page_id": storage.resolve_link(meta, href, page_id)}


@router.get("/preview-assets/{project_id}/{asset_path:path}")
def preview_asset(project_id: str, asset_path: str):
    try:
        meta = storage.load_meta(project_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, "项目不存在或已移入回收站")
    root = (storage.project_dir(project_id) / "source").resolve()
    path = (root / asset_path).resolve()
    if root not in path.parents and path != root:
        raise HTTPException(403)
    if not path.exists() or not path.is_file():
        raise HTTPException(404)
    if any(p.get('deleted_at') and (root / p['path']).resolve() == path for p in meta['pages']):
        raise HTTPException(404, "页面已移入回收站")
    media = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    risky = media in {"text/html", "image/svg+xml", "application/xhtml+xml", "text/xml", "application/xml"}
    return FileResponse(path, media_type=media, headers=SANDBOX_CSP if risky else None)


@router.get("/preview/{project_id}/{page_id}", response_class=HTMLResponse)
def preview(project_id: str, page_id: str):
    try:
        meta = storage.load_meta(project_id)
        page = storage.get_page(meta, page_id)
        html = storage.read_page(project_id, page_id)
    except Exception:
        raise HTTPException(404)
    return preview_html(project_id, page_id, page, html)


def preview_html(project_id, page_id, page, html):
    parent = str(Path(page["path"]).parent).replace("\\", "/")
    base = f"/preview-assets/{project_id}/" + ("" if parent == "." else parent.rstrip("/") + "/")
    base_tag = f'<base href="{base}">'
    if "<base" not in html.lower():
        if "<head" in html.lower():
            idx = html.lower().find(">", html.lower().find("<head")) + 1
            html = html[:idx] + base_tag + html[idx:]
        else:
            html = base_tag + html
    bridge = build_bridge(project_id, page_id)
    head = re.search(r'<head\b[^>]*>', html, re.I)
    if head:
        idx = head.end()
        html = html[:idx] + bridge + html[idx:]
    else:
        html += bridge
    return HTMLResponse(html, headers={"Cache-Control":"no-store", **SANDBOX_CSP})


@router.get('/api/projects/{project_id}/pages/{page_id}/source')
def page_source(project_id: str, page_id: str):
    source = storage.read_page(project_id, page_id)
    return {'source': source, 'hash': transactions.digest(source), 'tokens': token_values(source),
            'defaults': DEFAULT_TOKENS, 'regions': [{**r,'label':REGION_NAMES.get(r['name'],'自定义区域')} for r in outline(source)]}


@router.get('/api/projects/{project_id}/pages/{page_id}/inspect')
def inspect_element(project_id: str, page_id: str, selector: str, text: str = "", style_selector: str = ""):
    source = storage.read_page(project_id, page_id)
    try:
        node, span = locate(source, selector)
        safe_text = not node.find() and node.name not in {'input', 'img', 'select', 'textarea', 'script', 'style'}
        return {'editable': True, 'text_editable': safe_text, 'text': node.get_text(),
                'name': element_name({'tag':node.name,'text':node.get_text(' ',strip=True)}),
                'line': node.sourceline, 'html': source[span.start:span.end][:4000], 'hash': transactions.digest(source)}
    except PatchError as exc:
        # 源码里没有它的标签（脚本生成的）：样式按同类元素改，文字看源码里能不能找到原样的那一处
        return {'editable': False, 'text_editable': False, 'reason': str(exc), 'hash': transactions.digest(source),
                'dynamic': bool(style_selector), 'literal_count': literal_count(source, text) if text else 0}


@router.post('/api/projects/{project_id}/pages/{page_id}/edit')
def manual_edit(project_id: str, page_id: str, body: EditIn):
    try:
        source = storage.read_page(project_id, page_id)
        if body.expected_hash != transactions.digest(source):
            raise PatchError('页面已更新，请刷新后重试')
        if body.prop.startswith('--'):
            ops = [{'action':'set_token', 'name':body.prop, 'value':body.value}]
        elif body.prop == 'text' and body.literal:
            result = replace_literal(source, body.literal, body.value)
            return transactions.stage(project_id, page_id, source, result, '微调文字', targets=[{'selector':body.selector}] if body.selector else [])
        elif body.style_selector:
            ops = style_ops(source, 'set_rule', body.style_selector, body.prop, body.value, body.more)
        else:
            node, _ = locate(source, body.selector)
            if body.prop == 'text':
                if node.find() or node.name in {'input','img','select','textarea','script','style'}:
                    raise PatchError('该元素包含子结构，请选中具体文字或交给 AI 修改')
                ops = [{'action':'set_text','selector':body.selector,'value':body.value}]
            else:
                ops = style_ops(source, 'set_style', body.selector, body.prop, body.value, body.more)
        result, _ = apply_operations(source, ops)
        return transactions.stage(project_id, page_id, source, result, '微调', targets=[{'selector':body.selector}] if body.selector else [])
    except (PatchError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@router.post('/api/projects/{project_id}/pages/{page_id}/undo')
def undo_manual(project_id: str, page_id: str, body: UndoIn = UndoIn()):
    try:
        return transactions.undo(project_id, page_id, body.change_id)
    except PatchError as exc:
        raise HTTPException(400, str(exc))


@router.get('/api/candidates/{token}/preview', response_class=HTMLResponse)
def candidate_preview(token: str):
    try:
        item = transactions.get(token)
        meta = storage.load_meta(item['project_id'])
        page = storage.get_page(meta, item['page_id'])
        return preview_html(item['project_id'], item['page_id'], page, item['after'])
    except PatchError as exc:
        raise HTTPException(404, str(exc))


@router.post('/api/candidates/{token}/commit')
def commit_candidate(token: str, body: CommitIn):
    try:
        return transactions.commit(token, body.errors, body.runtime_checked)
    except PatchError as exc:
        raise HTTPException(409, error_payload(exc))
