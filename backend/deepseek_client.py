from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .errors import WorkError


class DeepSeekError(WorkError):
    def __init__(self, message, code=''):
        super().__init__(code, message)


class StreamUnsupported(DeepSeekError):
    """端点不接受 stream + tools —— 可以退回一次性请求重试。"""


def _curl_request(api_key: str, payload: dict[str, Any], api_url: str) -> dict[str, Any]:
    curl = shutil.which("curl")
    if not curl:
        raise DeepSeekError("系统未找到 curl")
    with tempfile.TemporaryDirectory(prefix="prototype-agent-") as td:
        payload_path = Path(td) / "payload.json"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
        config = (
            f'url = "{api_url}"\n'
            'request = "POST"\n'
            f'header = "Authorization: Bearer {api_key}"\n'
            'header = "Content-Type: application/json"\n'
            f'data-binary = "@{payload_path}"\n'
            'connect-timeout = 30\n'
            'max-time = 180\n'
        )
        try:
            result = subprocess.run(
            [curl, "--silent", "--show-error", "--fail-with-body", "--http1.1", "--config", "-"],
            input=config,
            text=True,
            capture_output=True,
            timeout=200,
            )
        except subprocess.TimeoutExpired as exc:
            raise DeepSeekError('模型请求超时', 'network') from exc
        if result.returncode != 0:
            detail = ((result.stderr or "") + " " + (result.stdout or "")).strip() or "curl 调用失败"
            raise DeepSeekError(detail[:2000])
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise DeepSeekError("模型返回了无法解析的 JSON", 'invalid_arguments') from exc


def _urllib_request(api_key: str, payload: dict[str, Any], api_url: str) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=data,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Connection": "close"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise DeepSeekError(f"DeepSeek HTTP {exc.code}: {body[:1600]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DeepSeekError(f"模型网络错误: {exc}", 'network') from exc
    except json.JSONDecodeError as exc:
        raise DeepSeekError('模型响应不是有效 JSON', 'invalid_arguments') from exc


# ---- 流式：把 OpenAI 风格的增量分片折回成一份完整响应 ----
# 本轮的结论文字是 report_result / answer_user 的工具参数，不是 content，
# 所以要边收边从未闭合的 JSON 里把这个字段抠出来，才能做到逐字显示。
VISIBLE_FIELD = re.compile(r'"(?:summary|answer|question)"\s*:\s*"')
ESCAPES = {'n': '\n', 't': '\t', 'r': '\r', '"': '"', '\\': '\\', '/': '/', 'b': '', 'f': ''}


def visible_text(arguments: str) -> str:
    """从尚未写完的工具参数里取出已经成形的那段人类可读文字。"""
    match = VISIBLE_FIELD.search(arguments)
    if not match:
        return ''
    out, i = [], match.end()
    while i < len(arguments):
        ch = arguments[i]
        if ch == '\\':
            nxt = arguments[i + 1:i + 2]
            if not nxt:
                break
            if nxt == 'u':
                point = arguments[i + 2:i + 6]
                if len(point) < 4:
                    break
                try:
                    out.append(chr(int(point, 16)))
                except ValueError:
                    break
                i += 6
                continue
            out.append(ESCAPES.get(nxt, nxt))
            i += 2
            continue
        if ch == '"':
            break
        out.append(ch)
        i += 1
    return ''.join(out)


def _iter_events(lines, seen_events=None):
    for raw in lines:
        line = raw.strip()
        if not line.startswith('data:'):
            continue
        data = line[5:].strip()
        if data == '[DONE]':
            return
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        if seen_events is not None:
            seen_events.append(1)
        yield event


def _assemble(events, on_delta):
    """折叠分片；同时把新增的可见文字回调出去。"""
    content, calls, finish, usage, shown = [], {}, None, {}, {}
    for event in events:
        if event.get('usage'):
            usage = event['usage']
        for choice in event.get('choices') or []:
            finish = choice.get('finish_reason') or finish
            delta = choice.get('delta') or {}
            if delta.get('content'):
                content.append(delta['content'])
                # 模型在调工具之前说的话——它为什么要查这个。
                # 和下面工具参数里的最终结论不是一回事，分开发。
                on_delta(delta['content'], 'note')
            for call in delta.get('tool_calls') or []:
                index = call.get('index', 0)
                slot = calls.setdefault(index, {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                if call.get('id'):
                    slot['id'] = call['id']
                function = call.get('function') or {}
                if function.get('name'):
                    slot['function']['name'] = function['name']
                if function.get('arguments'):
                    slot['function']['arguments'] += function['arguments']
                    text = visible_text(slot['function']['arguments'])
                    if len(text) > shown.get(index, 0):
                        on_delta(text[shown.get(index, 0):], 'result')
                        shown[index] = len(text)
    message = {'role': 'assistant', 'content': ''.join(content)}
    if calls:
        message['tool_calls'] = [calls[key] for key in sorted(calls)]
    return {'choices': [{'finish_reason': finish, 'message': message}], 'usage': usage}


def _looks_like_stream_refusal(detail: str) -> bool:
    return bool(re.search(r'stream|sse|server[- ]sent', detail or '', re.I))


def _fallback_response(body: str):
    """端点忽略了 stream、直接返回了完整 JSON —— 直接用，不必再请求一次。"""
    try:
        data = json.loads(body.strip())
    except (json.JSONDecodeError, AttributeError):
        raise StreamUnsupported('端点没有返回流式数据', 'network')
    if not data.get('choices'):
        raise StreamUnsupported('端点没有返回流式数据', 'network')
    return data


def _curl_stream(api_key, payload, api_url, on_delta, should_stop=None):
    curl = shutil.which("curl")
    with tempfile.TemporaryDirectory(prefix="prototype-agent-") as td:
        payload_path = Path(td) / "payload.json"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
        config = (
            f'url = "{api_url}"\n'
            'request = "POST"\n'
            f'header = "Authorization: Bearer {api_key}"\n'
            'header = "Content-Type: application/json"\n'
            f'data-binary = "@{payload_path}"\n'
            'connect-timeout = 30\n'
            'max-time = 600\n'
        )
        process = subprocess.Popen(
            [curl, "--silent", "--show-error", "--fail-with-body", "--http1.1", "--no-buffer", "--config", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        process.stdin.write(config)
        process.stdin.close()
        seen = []

        def lines():
            for line in process.stdout:
                # 用户点了停止：直接掐断这次请求，不等模型把这一轮说完
                if should_stop and should_stop():
                    process.kill()
                    raise DeepSeekError('已停止', 'stopped')
                seen.append(line)
                yield line

        events = []
        result = _assemble(_iter_events(lines(), events), on_delta)
        process.wait(timeout=30)
        body = ''.join(seen)
        if process.returncode != 0:
            detail = ((process.stderr.read() or '') + ' ' + body).strip() or 'curl 调用失败'
            raise (StreamUnsupported if _looks_like_stream_refusal(detail) else DeepSeekError)(detail[:2000])
        if not events:
            return _fallback_response(body)
        if not result['choices'][0]['finish_reason'] and not result['choices'][0]['message'].get('tool_calls'):
            raise DeepSeekError('模型流式响应中断，本次未做修改', 'network')
        return result


def _urllib_stream(api_key, payload, api_url, on_delta):
    request = urllib.request.Request(
        api_url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            events, seen = [], []

            def lines():
                for raw in response:
                    text = raw.decode('utf-8', 'replace')
                    seen.append(text)
                    yield text

            result = _assemble(_iter_events(lines(), events), on_delta)
            return result if events else _fallback_response(''.join(seen))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:1600]
        error = StreamUnsupported if _looks_like_stream_refusal(detail) else DeepSeekError
        raise error(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DeepSeekError(f"模型网络错误: {exc}", 'network') from exc


# ---- 自动重试：模型服务忙（限流、5xx）、网络抖一下、流式中途断了，等一会儿再来，不直接判失败 ----
# 密钥、余额、请求本身有问题（4xx、上下文太长）重试也没用，立刻报出来。
RETRY_DELAYS = (2, 5, 12)
_RETRYABLE = re.compile(r'\b(408|409|425|429|500|502|503|504|520|522|524|529)\b|rate.?limit|too many requests|overload|busy|server error|bad gateway|'
                        r'service unavailable|gateway time|timed? ?out|timeout|connection (reset|refused|closed)|reset by peer|'
                        r'could not resolve|temporar|empty reply|EOF|流式响应中断|超时|网络错误', re.I)
_FATAL = re.compile(r'\b(400|401|402|403|404|413|422)\b|insufficient|balance|余额|api.?key|unauthori|context length|maximum context|too long', re.I)


def retryable(exc: Exception) -> bool:
    text = str(exc)
    if getattr(exc, 'code', '') == 'stopped' or _FATAL.search(text):
        return False
    return getattr(exc, 'code', '') == 'network' or bool(_RETRYABLE.search(text))


def chat(api_key: str, model: str, messages: list[dict], tools: list[dict] | None = None, base_url: str = "https://api.deepseek.com",
         max_tokens: int = 16000, on_delta=None, on_retry=None, should_stop=None) -> dict[str, Any]:
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            return _chat_once(api_key, model, messages, tools, base_url, max_tokens, on_delta, should_stop)
        except DeepSeekError as exc:
            if not retryable(exc):
                raise
            if attempt >= len(RETRY_DELAYS):
                raise DeepSeekError(f'模型服务暂时不可用，已自动重试 {attempt} 次仍未成功：{str(exc)[:300]}', 'busy') from exc
            wait = RETRY_DELAYS[attempt]
            if on_retry:
                on_retry(attempt + 1, wait, exc)
            end = time.time() + wait
            while time.time() < end:
                if should_stop and should_stop():
                    raise DeepSeekError('已停止', 'stopped')
                time.sleep(0.2)


def _chat_once(api_key, model, messages, tools, base_url, max_tokens, on_delta, should_stop) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model or "deepseek-flash",
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    api_url = base_url.rstrip("/")
    if not api_url.endswith("/chat/completions"):
        api_url += "/chat/completions"
    if on_delta:
        streamed = dict(payload, stream=True, stream_options={"include_usage": True})
        try:
            if shutil.which("curl"):
                return _curl_stream(api_key, streamed, api_url, on_delta, should_stop)
            return _urllib_stream(api_key, streamed, api_url, on_delta)
        except StreamUnsupported:
            # 接口不接受 stream + tools：本轮退回一次性返回，不逐字显示，但不失败。
            pass
    if shutil.which("curl"):
        return _curl_request(api_key, payload, api_url)
    return _urllib_request(api_key, payload, api_url)
