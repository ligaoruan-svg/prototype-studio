from __future__ import annotations

import io
import json
import mimetypes
import re
import shutil
import zipfile
import queue
import threading
import uuid
import logging
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import storage, config, transactions, components, memory, skills
from .agent import run_agent
from .atomicio import write_atomic
from .bridge import build_bridge
from .safety import host_name, zip_member_ok, to_utf8
from .patcher import apply_operations, locate, outline, token_values, DEFAULT_TOKENS, PatchError
from starlette.concurrency import run_in_threadpool
from .deepseek_client import chat
from .errors import WorkError, error_payload
from .experience import REGION_NAMES, element_name

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = ROOT / "frontend" / "dist"
app = FastAPI(title="原型工坊", version=config.VERSION)


# 本机工具也会被别的网站"顺手"调用：浏览器里任何网页都能往 127.0.0.1 发表单。
# 改东西的请求必须来自原型工坊自己的页面（Origin 和 Host 一致）；原型预览跑在沙箱里，Origin 是 null，也拦掉。
from urllib.parse import urlsplit as _urlsplit
from fastapi.responses import JSONResponse as _JSONResponse


# DNS rebinding：恶意网站把自己的域名临时解析到 127.0.0.1，浏览器就把它当成同源，
# Origin 和 Host 都是 evil.com:5173，上面的比较拦不住。所以 Host 本身必须是本机地址。
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}


@app.middleware("http")
async def same_origin_only(request, call_next):
    if host_name(request.headers.get("host", "")) not in LOCAL_HOSTS:
        return _JSONResponse({"detail": "原型工坊只接受本机地址（127.0.0.1 / localhost）的访问"}, status_code=400)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin is not None and _urlsplit(origin).netloc != request.headers.get("host", ""):
            return _JSONResponse({"detail": "只接受原型工坊自己页面发来的修改请求"}, status_code=403)
        # 没带 Origin 的浏览器请求（老式表单之类），看 Sec-Fetch-Site：不是同源发来的一律不收
        site = request.headers.get("sec-fetch-site")
        if origin is None and site and site not in ("same-origin", "none"):
            return _JSONResponse({"detail": "只接受原型工坊自己页面发来的修改请求"}, status_code=403)
    return await call_next(request)


# 原型的 HTML 和 API 同源：要是有人直接在浏览器里打开预览地址，原型里的脚本就能调本机 API。
# 加上 CSP sandbox，直接打开时它也跑在隔离的沙箱里（界面里本来就是用沙箱 iframe 载入的，不受影响）
SANDBOX_CSP = {"Content-Security-Policy": "sandbox allow-scripts allow-forms allow-modals allow-popups"}


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


class AgentIn(BaseModel):
    page_id: str
    message: str
    model: str = ""
    selection: dict | None = None
    runtime_feedback: str = ""
    reference: dict | None = None
    scene: dict | None = None   # 预览现场：停在哪页、最近点过什么、报过什么错
    intent: str = Field(default='auto', pattern='^(auto|discuss|edit)$')
    include_annotations: bool = True


class EditIn(BaseModel):
    selector: str = ""
    prop: str
    value: str
    expected_hash: str


class CommitIn(BaseModel):
    runtime_checked: bool = False
    errors: list[str] = []


class ConfigIn(BaseModel):
    base_url: str
    model: str
    api_key: str = ""
    supports_vision: bool = False
    max_tokens: int = Field(default=32000, ge=1024, le=131072)
    context_budget: int = Field(default=200_000, ge=20_000, le=2_000_000)
    max_rounds: int = Field(default=24, ge=4, le=60)
    stream: bool = True


class SpecIn(BaseModel):
    content: str


class UndoIn(BaseModel):
    change_id: str = ""


class NewProjectIn(BaseModel):
    name: str = "未命名原型"


class RenameIn(BaseModel):
    name: str


class RestoreItemIn(BaseModel):
    project_id: str
    page_id: str = ""


def _code_epoch() -> float:
    """后端代码和提示词最后一次改动的时间：比服务启动时间新，说明在跑的是旧代码"""
    newest = 0.0
    for folder in (ROOT / "backend", ROOT / "prompts"):
        for path in folder.rglob("*"):
            if path.suffix in {".py", ".md"} and "tests" not in path.parts and "__pycache__" not in path.parts:
                try:
                    newest = max(newest, path.stat().st_mtime)
                except OSError:
                    pass
    return newest


@app.get("/api/health")
def health():
    return {"ok": True, "version": config.VERSION, "service": "prototype-agent",
            "started_epoch": config.STARTED_EPOCH, "code_epoch": _code_epoch()}


@app.get("/api/config")
def get_config():
    return config.public()


@app.post("/api/config")
def save_config(body: ConfigIn):
    try:
        return config.save(body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))


class SwitchIn(BaseModel):
    id: str


class ProfileIn(ConfigIn):
    id: str = ""
    name: str = Field(default="", max_length=30)
    activate: bool = False


class TestIn(BaseModel):
    id: str = ""


@app.post("/api/config/profiles")
def save_profile(body: ProfileIn):
    """新增或修改一个绑定的模型（不一定马上用它）"""
    try:
        values = body.model_dump()
        return config.save_profile(values, values.pop("id"), values.pop("activate"))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/config/switch")
def switch_model(body: SwitchIn):
    try:
        return config.switch(body.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/config/profiles/{profile_id}")
def delete_profile(profile_id: str):
    try:
        return config.forget_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


PING_TOOL = {"type": "function", "function": {"name": "ping", "description": "连接测试用：被调用就说明支持工具调用。",
             "parameters": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}}}


@app.post("/api/config/test")
def test_config(body: TestIn | None = None):
    try:
        settings = config.profile_settings(body.id if body else "")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not settings['api_key']:
        raise HTTPException(400, "请先保存 API 密钥")
    key = settings['api_key']
    try:
        result = chat(key, settings['model'], [{"role":"user","content":"Reply OK only."}], base_url=settings['base_url'], max_tokens=min(512, settings['max_tokens']))
    except Exception as exc:
        raise HTTPException(400, str(exc).replace(key, '[密钥]'))
    # 能连上不等于能干活：生成和修改页面全靠「调用工具」。用一个小工具试一下它会不会按要求调用，
    # 并且按真正干活时的方式发（开了逐字显示就走流式），这样测通了就是真能用
    tools, tool_error = False, ""
    try:
        probe = chat(key, settings['model'],
                     [{"role": "user", "content": "这是连接测试。请调用 ping 工具，参数 ok 填 true。只调用工具，不要输出别的文字。"}],
                     [PING_TOOL], base_url=settings['base_url'], max_tokens=min(512, settings['max_tokens']),
                     on_delta=(lambda *a, **k: None) if settings.get('stream', True) else None)
        tools = bool(((probe.get('choices') or [{}])[0].get('message') or {}).get('tool_calls'))
        if not tools:
            tool_error = "模型回了文字，没有调用工具"
    except Exception as exc:
        tool_error = str(exc).replace(key, '[密钥]')[:300]
    return {"ok": bool(result.get('choices')), "usage": result.get('usage', {}), "tools": tools, "tool_error": tool_error}


SPEC_PATH = ROOT / "prompts" / "design-spec.md"


@app.get("/api/design-spec")
def get_design_spec():
    return {"content": SPEC_PATH.read_text("utf-8")}


@app.put("/api/design-spec")
def save_design_spec(body: SpecIn):
    text = body.content.strip()
    if not 40 <= len(text) <= 20000:
        raise HTTPException(400, "设计规范应在 40 到 20000 字之间")
    write_atomic(SPEC_PATH, text + "\n")
    return {"ok": True, "chars": len(text)}


@app.post("/api/design-spec/extract")
async def extract_design_tokens(file: UploadFile = File(...)):
    """从一份现成页面里读出它定义的 CSS 变量，交给用户确认后再写进规范。"""
    raw = (await file.read())[:4_000_000].decode("utf-8", errors="replace")
    found = await run_in_threadpool(token_values, raw)   # 解析几 MB 的页面别卡住其他请求（包括正在推进度的那条）
    tokens = {name: value.strip()[:40] for name, value in found.items() if len(name) <= 40}
    if not tokens:
        raise HTTPException(400, "这份文件里没有找到 :root 上的 CSS 变量定义")
    return {"tokens": dict(sorted(tokens.items())), "count": len(tokens)}


# ===== 记忆：参照 Claude 的做法，两层（这个项目 / 所有项目）、按类别、能暂停能清空、能一句话改、会自己整理 =====
def _memory_llm():
    """记忆整理和「一句话改记忆」用的模型调用：不带工具，只要一段 JSON。"""
    settings = config.load()
    key = settings.get("api_key")
    if not key:
        raise HTTPException(400, "请先在设置中保存 API 密钥")
    def ask(prompt: str) -> str:
        resp = chat(key, settings["model"], [{"role": "user", "content": prompt}], None,
                    base_url=settings["base_url"], max_tokens=1500)
        return ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return ask


SYNTHESIZING: set[str] = set()


def synthesize_later(project_id: str) -> None:
    """一次修改 / 回复结束后在后台看一眼：攒够几条新发言就整理一次记忆。失败了不打扰用户。"""
    if project_id in SYNTHESIZING:
        return
    try:
        meta = storage.load_meta(project_id)
        if memory.state_of(meta).get("paused") or memory.pending_count(meta) < memory.SYNTH_EVERY or not config.load().get("api_key"):
            return
    except Exception:
        return
    SYNTHESIZING.add(project_id)   # 先占上：两次修改紧挨着结束时别起两个整理
    def go():
        try:
            memory.synthesize(project_id, _memory_llm())
        except Exception:
            logging.getLogger(__name__).warning("记忆整理没成功", exc_info=True)
        finally:
            SYNTHESIZING.discard(project_id)
    threading.Thread(target=go, daemon=True).start()


@app.get("/api/projects/{project_id}/memory")
def list_memory(project_id: str):
    try:
        snap = memory.snapshot(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    return {**snap, "memory": snap["project"]["memory"], "synthesizing": project_id in SYNTHESIZING}


class MemoryIn(BaseModel):
    note: str
    category: str = ""
    scope: str = "project"


class MemoryPatch(BaseModel):
    text: str = ""
    category: str = ""


class MemoryEditIn(BaseModel):
    instruction: str


class MemoryScopeIn(BaseModel):
    scope: str = "project"
    paused: bool = False


@app.post("/api/projects/{project_id}/memory")
def add_memory(project_id: str, body: MemoryIn):
    try:
        return memory.add(project_id, body.note, body.category, body.scope, "manual")
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/projects/{project_id}/memory/{note_id}")
def patch_memory(project_id: str, note_id: str, body: MemoryPatch):
    try:
        return memory.update(project_id, note_id, body.text, body.category)
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/projects/{project_id}/memory/{note_id}")
def delete_memory(project_id: str, note_id: str):
    return {"ok": memory.remove(project_id, note_id)}


@app.post("/api/projects/{project_id}/memory/edit")
def edit_memory(project_id: str, body: MemoryEditIn):
    try:
        return memory.edit_by_instruction(project_id, body.instruction, _memory_llm())
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/projects/{project_id}/memory/synthesize")
def synthesize_memory(project_id: str):
    try:
        return memory.synthesize(project_id, _memory_llm(), force=True)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/projects/{project_id}/memory/pause")
def pause_memory(project_id: str, body: MemoryScopeIn):
    memory.set_paused(project_id, body.scope, body.paused)
    return {"ok": True}


@app.post("/api/projects/{project_id}/memory/clear")
def clear_memory(project_id: str, body: MemoryScopeIn):
    memory.clear(project_id, body.scope)
    return {"ok": True}


@app.get("/api/components")
def list_components():
    return {"components": components.listing(), "skills": skills.listing()}


@app.delete("/api/skills/{name}")
def remove_skill(name: str):
    return {"ok": skills.remove(name)}


@app.post("/api/components")
async def add_component(file: UploadFile = File(...), name: str = Form("")):
    source = (name or file.filename or "").strip()
    raw = await file.read()
    # 解压、写文件放到线程里做：在事件循环里做会让所有请求（包括 AI 正在推的进度）一起卡住
    return await run_in_threadpool(_add_component, source, raw)


def _add_component(source: str, raw: bytes):
    try:
        if source.lower().endswith(".zip"):
            if len(raw) > components.MAX_ZIP_BYTES:
                raise HTTPException(400, f"压缩包太大（最多 {components.MAX_ZIP_BYTES // 1024 // 1024}MB）")
            data = raw   # 以前截断压缩后的字节，zip 目录在文件末尾，超过上限的包一律报「损坏」
            try:
                # 带 SKILL.md 的按 skill 收，保留整包结构；否则退回拆成零散组件。
                return {"kind": "skill", **skills.import_archive(data)}
            except ValueError as exc:
                if "没有 SKILL.md" not in str(exc):
                    raise
            return {"kind": "components", **components.import_archive(data)}
        if not source.lower().endswith(tuple(components.WANTED)):
            raise HTTPException(400, "支持 .html、.md，或整包 .zip")
        target = components.safe_name(source)
        saved = components.save(target, raw[:components.MAX_BYTES + 1].decode("utf-8", errors="replace"))
        return {"kind": "components", "imported": [saved["name"]], "skipped": [], "skipped_count": 0}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/components/{name}")
def remove_component(name: str):
    try:
        components.delete(name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.post("/api/projects/new")
def new_project(body: NewProjectIn):
    html = (ROOT / "sample" / "starter.html").read_text('utf-8')   # 先读模板：读不到就别建出一个空项目
    project = storage.create_project(body.name.strip()[:80] or "未命名原型")
    import html as html_lib
    html = html.replace('新原型', html_lib.escape(project['name']))
    (storage.project_dir(project['id']) / 'source' / 'index.html').write_text(html, 'utf-8')
    storage.add_page(project['id'], 'index.html', project['name'])
    return storage.load_meta(project['id'])


@app.get("/api/projects")
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


@app.post("/api/projects/upload")
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
    project = storage.create_project(name or Path(filename).stem)
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


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    try:
        meta = storage.load_meta(project_id)
        meta['pages'] = [p for p in meta['pages'] if not p.get('deleted_at')]
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


@app.get("/api/trash")
def list_trash():
    return storage.list_trash()


@app.post("/api/trash/restore")
def restore_item(body: RestoreItemIn):
    try:
        with transactions.LOCK:
            storage.restore_item(body.project_id, body.page_id)
        return {"ok": True}
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/trash/purge")
def purge_item(body: RestoreItemIn):
    try:
        with transactions.LOCK:
            storage.purge_item(body.project_id, body.page_id)
            transactions.invalidate(body.project_id, body.page_id)
        return {"ok": True}
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/trash/empty")
def empty_trash():
    with transactions.LOCK:
        items = storage.list_trash()
        count = storage.purge_all()
        for item in items:
            transactions.invalidate(item["project_id"], item.get("page_id", ""))
    return {"ok": True, "count": count}


@app.patch("/api/projects/{project_id}")
def rename_project(project_id: str, body: RenameIn):
    try:
        with transactions.LOCK:
            storage.rename_item(project_id, body.name)
        return {"ok": True}
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/projects/{project_id}/pages/{page_id}")
def rename_page(project_id: str, page_id: str, body: RenameIn):
    try:
        with transactions.LOCK:
            storage.rename_item(project_id, body.name, page_id)
        return {"ok": True}
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    try:
        with transactions.LOCK:
            storage.trash_item(project_id)
            transactions.invalidate(project_id)
        return {"ok": True, "recoverable": True}
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/projects/{project_id}/pages/{page_id}")
def delete_page(project_id: str, page_id: str):
    try:
        with transactions.LOCK:
            storage.trash_item(project_id, page_id)
            transactions.invalidate(project_id, page_id)
        return {"ok": True, "recoverable": True}
    except (ValueError, KeyError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/projects/{project_id}/pages/{page_id}/annotations")
def add_annotation(project_id: str, page_id: str, body: AnnotationIn):
    try:
        return storage.add_annotation(project_id, page_id, body.model_dump())
    except Exception as exc:
        raise HTTPException(400, str(exc))


class ExpandRoutesIn(BaseModel):
    routes: list[dict] = []
    v: int = 0


class ExpandOverridesIn(BaseModel):
    overrides: dict = {}


class ExpandEntryIn(BaseModel):
    route: str = ""
    hash: str = ""
    result: dict


@app.get("/api/projects/{project_id}/pages/{page_id}/expand")
def get_expand(project_id: str, page_id: str):
    try:
        return storage.load_expand(project_id, page_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc))


@app.put("/api/projects/{project_id}/pages/{page_id}/expand/routes")
def put_expand_routes(project_id: str, page_id: str, body: ExpandRoutesIn):
    try:
        storage.save_expand_routes(project_id, page_id, body.routes, body.v)
        return {"ok": True}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@app.put("/api/projects/{project_id}/pages/{page_id}/expand/overrides")
def put_expand_overrides(project_id: str, page_id: str, body: ExpandOverridesIn):
    try:
        storage.save_expand_overrides(project_id, page_id, body.overrides)
        return {"ok": True}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@app.put("/api/projects/{project_id}/pages/{page_id}/expand/entry")
def put_expand_entry(project_id: str, page_id: str, body: ExpandEntryIn):
    try:
        storage.save_expand_entry(project_id, page_id, body.route, body.hash, body.result)
        return {"ok": True}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/projects/{project_id}/annotations/{annotation_id}")
def del_annotation(project_id: str, annotation_id: str):
    storage.delete_annotation(project_id, annotation_id)
    return {"ok": True}


@app.post("/api/projects/{project_id}/agent/chat")
def agent_chat(project_id: str, body: AgentIn, x_deepseek_key: str | None = Header(default=None)):
    settings, key = agent_settings(body, x_deepseek_key)
    try:
        return run_agent(project_id, body.page_id, body.message, key, body.model or settings['model'],
                         settings['base_url'], body.selection, body.runtime_feedback, body.reference, settings['max_tokens'],
                         settings.get('context_budget', 200_000), settings.get('max_rounds', 24),
                         intent=body.intent, include_annotations=body.include_annotations, scene=body.scene)
    except Exception as exc:
        if not isinstance(exc, (WorkError, PatchError)):
            logging.getLogger(__name__).exception('Unexpected agent request failure')
            exc = WorkError('internal', '本地服务内部错误')
        payload = error_payload(exc)
        payload['detail'] = payload['detail'].replace(key, '[密钥]')
        raise HTTPException(400, payload)


def agent_settings(body, supplied_key=None):
    settings = config.load()
    key = supplied_key or settings['api_key']
    if not key:
        raise HTTPException(400, error_payload(WorkError('model_account', '请先在设置中保存 API 密钥')))
    if body.reference:
        if not settings['supports_vision']:
            raise HTTPException(400, '截图理解需要支持视觉的模型，请在设置中配置并启用')
        image = body.reference.get('data_url', '')
        if not re.fullmatch(r'data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+', image) or len(image) > 12_000_000:
            raise HTTPException(400, '图片格式无效或超过限制')
    return settings, key


# 正在跑的 AI 修改：run_id → 停止信号。点「停止」或关掉页面（连接断开）都会置位，
# agent 在两轮之间 / 两步之间看到就停下；已改好的部分照常走检查和保存。
RUNS: dict[str, threading.Event] = {}


class StopIn(BaseModel):
    run_id: str


@app.post('/api/projects/{project_id}/agent/stop')
def agent_stop(project_id: str, body: StopIn):
    flag = RUNS.get(body.run_id)
    if flag:
        flag.set()
    return {'ok': bool(flag)}


@app.post('/api/projects/{project_id}/agent/stream')
def agent_stream(project_id: str, body: AgentIn):
    settings, key = agent_settings(body)
    events = queue.Queue()
    run_id = uuid.uuid4().hex[:12]
    stop = RUNS[run_id] = threading.Event()
    def work():
        try:
            result = run_agent(project_id, body.page_id, body.message, key, body.model or settings['model'],
                               settings['base_url'], body.selection, body.runtime_feedback, body.reference,
                               settings['max_tokens'], settings.get('context_budget', 200_000),
                               settings.get('max_rounds', 24),
                               on_event=events.put, intent=body.intent, include_annotations=body.include_annotations, scene=body.scene,
                               stream=settings.get('stream', True), should_stop=stop.is_set)
            events.put({'type':'complete','result':result})
            synthesize_later(project_id)
        except Exception as exc:
            if not isinstance(exc, (WorkError, PatchError)):
                logging.getLogger(__name__).exception('Unexpected streamed agent failure')
                exc = WorkError('internal', '本地服务内部错误')
            payload = error_payload(exc)
            payload['detail'] = payload['detail'].replace(key, '[密钥]')
            events.put({'type':'error','error':payload})
        finally:
            events.put(None)
            RUNS.pop(run_id, None)
    def generate():
        finished = False
        try:
            yield 'data: ' + json.dumps({'type':'started','label':'正在理解你的需求','run_id':run_id}, ensure_ascii=False) + '\n\n'
            threading.Thread(target=work, daemon=True).start()
            while True:
                try: event = events.get(timeout=2)
                except queue.Empty:
                    yield ': heartbeat\n\n'
                    continue
                if event is None:
                    finished = True
                    break
                yield 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'
        finally:
            # 页面关了 / 刷新了，连接断开：别让后台继续花钱调模型
            if not finished:
                stop.set()
    return StreamingResponse(generate(), media_type='text/event-stream', headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})


@app.post("/api/projects/{project_id}/pages/{page_id}/restore/{version}")
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


@app.get("/api/projects/{project_id}/pages/{page_id}/download")
def download_page(project_id: str, page_id: str):
    path = storage.page_file(project_id, page_id)
    return FileResponse(path, filename=path.name, media_type="text/html")


@app.get("/api/projects/{project_id}/export")
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


@app.get("/api/projects/{project_id}/resolve")
def resolve_page(project_id: str, href: str, page_id: str = ""):
    meta = storage.load_meta(project_id)
    clean = href.split("#",1)[0].split("?",1)[0]
    candidates = [clean.lstrip("./")]
    if page_id:
        try:
            current = storage.get_page(meta, page_id)
            parent = Path(current["path"]).parent
            candidates.insert(0, str((parent / clean).as_posix()).lstrip("./"))
        except Exception:
            pass
    for page in meta.get("pages", []):
        if page.get('deleted_at'):
            continue
        if page["path"] in candidates or any(Path(page["path"]).name == Path(c).name for c in candidates):
            return {"page_id": page["id"]}
    return {"page_id": None}


@app.get("/preview-assets/{project_id}/{asset_path:path}")
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


@app.get("/preview/{project_id}/{page_id}", response_class=HTMLResponse)
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


@app.get('/api/projects/{project_id}/pages/{page_id}/source')
def page_source(project_id: str, page_id: str):
    source = storage.read_page(project_id, page_id)
    return {'source': source, 'hash': transactions.digest(source), 'tokens': token_values(source),
            'defaults': DEFAULT_TOKENS, 'regions': [{**r,'label':REGION_NAMES.get(r['name'],'自定义区域')} for r in outline(source)]}


@app.get('/api/projects/{project_id}/pages/{page_id}/inspect')
def inspect_element(project_id: str, page_id: str, selector: str):
    source = storage.read_page(project_id, page_id)
    try:
        node, span = locate(source, selector)
        safe_text = not node.find() and node.name not in {'input', 'img', 'select', 'textarea', 'script', 'style'}
        return {'editable': True, 'text_editable': safe_text, 'text': node.get_text(),
                'name': element_name({'tag':node.name,'text':node.get_text(' ',strip=True)}),
                'line': node.sourceline, 'html': source[span.start:span.end][:4000], 'hash': transactions.digest(source)}
    except PatchError as exc:
        return {'editable': False, 'text_editable': False, 'reason': str(exc), 'hash': transactions.digest(source)}


@app.post('/api/projects/{project_id}/pages/{page_id}/edit')
def manual_edit(project_id: str, page_id: str, body: EditIn):
    try:
        source = storage.read_page(project_id, page_id)
        if body.expected_hash != transactions.digest(source):
            raise PatchError('页面已更新，请刷新后重试')
        if body.prop.startswith('--'):
            ops = [{'action':'set_token', 'name':body.prop, 'value':body.value}]
        else:
            node, _ = locate(source, body.selector)
            if body.prop == 'text':
                if node.find() or node.name in {'input','img','select','textarea','script','style'}:
                    raise PatchError('该元素包含子结构，请选中具体文字或交给 AI 修改')
                ops = [{'action':'set_text','selector':body.selector,'value':body.value}]
            else:
                ops = []
                match = re.fullmatch(r'var\((--[\w-]+)\)', body.value)
                if match and match[1] not in token_values(source):
                    if match[1] not in DEFAULT_TOKENS:
                        raise PatchError('未知设计变量')
                    ops.append({'action':'set_token','name':match[1],'value':DEFAULT_TOKENS[match[1]]})
                ops.append({'action':'set_style','selector':body.selector,'name':body.prop,'value':body.value})
        result, _ = apply_operations(source, ops)
        return transactions.stage(project_id, page_id, source, result, '微调', targets=[{'selector':body.selector}] if body.selector else [])
    except (PatchError, ValueError) as exc:
        raise HTTPException(400, str(exc))


@app.post('/api/projects/{project_id}/pages/{page_id}/undo')
def undo_manual(project_id: str, page_id: str, body: UndoIn = UndoIn()):
    try:
        return transactions.undo(project_id, page_id, body.change_id)
    except PatchError as exc:
        raise HTTPException(400, str(exc))


@app.get('/api/candidates/{token}/preview', response_class=HTMLResponse)
def candidate_preview(token: str):
    try:
        item = transactions.get(token)
        meta = storage.load_meta(item['project_id'])
        page = storage.get_page(meta, item['page_id'])
        return preview_html(item['project_id'], item['page_id'], page, item['after'])
    except PatchError as exc:
        raise HTTPException(404, str(exc))


@app.post('/api/candidates/{token}/commit')
def commit_candidate(token: str, body: CommitIn):
    try:
        return transactions.commit(token, body.errors, body.runtime_checked)
    except PatchError as exc:
        raise HTTPException(409, error_payload(exc))


# 界面文件名里没有版本号（app.css、App.js 一直是这个名字）。
# Starlette 只发 etag 和 last-modified，不发 Cache-Control，浏览器就按启发式规则
# 自己判定「这个文件还新鲜」，连问都不问服务器——改了代码、重启了服务，页面还是老样子，
# 只能靠人记得按 Cmd+Shift+R。这里要求每次都回来核对；没变就是 304，本地几乎不花时间。
NO_CACHE = {"Cache-Control": "no-cache"}


class FreshFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


if FRONTEND_DIST.exists():
    assets = FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", FreshFiles(directory=assets), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path in {'api','preview','preview-assets'} or path.startswith(("api/", "preview/", "preview-assets/")):
            raise HTTPException(404)
        candidate = (FRONTEND_DIST / path).resolve()
        if FRONTEND_DIST.resolve() not in candidate.parents and candidate != FRONTEND_DIST.resolve():
            raise HTTPException(404)
        if path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate, headers=NO_CACHE)
        return FileResponse(FRONTEND_DIST / "index.html", headers=NO_CACHE)
