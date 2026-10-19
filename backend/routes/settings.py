"""健康检查、模型配置（多套模型、测试连接）、设计规范、组件库和 skill、风格清单"""
from __future__ import annotations

import sys

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .. import components, config, skills
from ..atomicio import write_atomic
from ..deepseek_client import chat
from ..patcher import token_values
from ..paths import APP_ROOT as ROOT, SPEC_FILE

router = APIRouter()


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


@router.get("/api/health")
def health():
    # 打包成桌面应用后代码就是装进去的那一份，不存在「改了代码没重启」，界面上不提示重启
    packaged = bool(getattr(sys, "frozen", False))
    return {"ok": True, "version": config.VERSION, "service": "prototype-agent", "packaged": packaged,
            "started_epoch": config.STARTED_EPOCH, "code_epoch": 0 if packaged else _code_epoch()}


@router.get("/api/config")
def get_config():
    return config.public()


@router.post("/api/config")
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


@router.post("/api/config/profiles")
def save_profile(body: ProfileIn):
    """新增或修改一个绑定的模型（不一定马上用它）"""
    try:
        values = body.model_dump()
        return config.save_profile(values, values.pop("id"), values.pop("activate"))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/api/config/switch")
def switch_model(body: SwitchIn):
    try:
        return config.switch(body.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/api/config/profiles/{profile_id}")
def delete_profile(profile_id: str):
    try:
        return config.forget_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


PING_TOOL = {"type": "function", "function": {"name": "ping", "description": "连接测试用：被调用就说明支持工具调用。",
             "parameters": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}}}


@router.post("/api/config/test")
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


SPEC_PATH = SPEC_FILE


@router.get("/api/design-spec")
def get_design_spec():
    return {"content": SPEC_PATH.read_text("utf-8")}


@router.put("/api/design-spec")
def save_design_spec(body: SpecIn):
    text = body.content.strip()
    if not 40 <= len(text) <= 20000:
        raise HTTPException(400, "设计规范应在 40 到 20000 字之间")
    write_atomic(SPEC_PATH, text + "\n")
    return {"ok": True, "chars": len(text)}


@router.post("/api/design-spec/extract")
async def extract_design_tokens(file: UploadFile = File(...)):
    """从一份现成页面里读出它定义的 CSS 变量，交给用户确认后再写进规范。"""
    raw = (await file.read())[:4_000_000].decode("utf-8", errors="replace")
    found = await run_in_threadpool(token_values, raw)   # 解析几 MB 的页面别卡住其他请求（包括正在推进度的那条）
    tokens = {name: value.strip()[:40] for name, value in found.items() if len(name) <= 40}
    if not tokens:
        raise HTTPException(400, "这份文件里没有找到 :root 上的 CSS 变量定义")
    return {"tokens": dict(sorted(tokens.items())), "count": len(tokens)}


@router.get("/api/components")
def list_components():
    return {"components": components.listing(), "skills": skills.listing()}


@router.delete("/api/skills/{name}")
def remove_skill(name: str):
    return {"ok": skills.remove(name)}


@router.post("/api/components")
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


@router.delete("/api/components/{name}")
def remove_component(name: str):
    try:
        components.delete(name)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@router.get("/api/styles")
def list_styles():
    """新建原型、设计规范里选风格用：软件自带的 + 自己导入的"""
    return {"builtin": skills.builtin_listing(), "mine": skills.listing()}


@router.get("/api/styles/{kind}/{name}/preview.png")
def style_preview(kind: str, name: str):
    path = skills.preview_path(kind, name) if kind in {"builtin", "mine"} else None
    if not path:
        raise HTTPException(404, "没有预览图")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "max-age=3600"})
