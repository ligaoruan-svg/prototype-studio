"""AI 修改：一次性 / 流式（边做边推进度）、停止"""
from __future__ import annotations

import json
import logging
import queue
import re
import threading
import uuid

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import config, transactions
from ..agent import run_agent
from ..errors import WorkError, error_payload
from ..patcher import PatchError
from .memory import synthesize_later

router = APIRouter()


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
    repair_pending: str = ''   # 运行检查没过的那一版：在它的基础上修报错，不从头再做
    lang: str = Field(default='zh', pattern='^[a-z]{2}(-[A-Za-z]{2,4})?$')   # 界面语言：用户这句话看不出语言时，AI 按它回复


@router.post("/api/projects/{project_id}/agent/chat")
def agent_chat(project_id: str, body: AgentIn, x_deepseek_key: str | None = Header(default=None)):
    settings, key = agent_settings(body, x_deepseek_key)
    try:
        return run_agent(project_id, body.page_id, body.message, key, body.model or settings['model'],
                         settings['base_url'], body.selection, body.runtime_feedback, body.reference, settings['max_tokens'],
                         settings.get('context_budget', 200_000), settings.get('max_rounds', 24),
                         intent=body.intent, include_annotations=body.include_annotations, scene=body.scene, lang=body.lang)
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


@router.post('/api/projects/{project_id}/agent/stop')
def agent_stop(project_id: str, body: StopIn):
    flag = RUNS.get(body.run_id)
    if flag:
        flag.set()
    return {'ok': bool(flag)}


@router.post('/api/projects/{project_id}/agent/stream')
def agent_stream(project_id: str, body: AgentIn):
    settings, key = agent_settings(body)
    events = queue.Queue()
    run_id = uuid.uuid4().hex[:12]
    stop = RUNS[run_id] = threading.Event()
    draft = transactions.failed_draft(body.repair_pending, project_id, body.page_id) if body.repair_pending else None
    def work():
        try:
            result = run_agent(project_id, body.page_id, body.message, key, body.model or settings['model'],
                               settings['base_url'], body.selection, body.runtime_feedback, body.reference,
                               settings['max_tokens'], settings.get('context_budget', 200_000),
                               settings.get('max_rounds', 24),
                               on_event=events.put, intent=body.intent, include_annotations=body.include_annotations, scene=body.scene,
                               stream=settings.get('stream', True), should_stop=stop.is_set,
                               start_source=(draft or {}).get('after'), lang=body.lang)
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
