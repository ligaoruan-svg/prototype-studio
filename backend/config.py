"""Local model settings. Public responses never contain the API key."""
import json
from pathlib import Path
from urllib.parse import urlparse

from .atomicio import write_atomic

# Single source of truth for the version shown in the API, README and release name.
VERSION = "6.0"
# 进程启动时刻。界面上显示出来，就不用再靠猜"到底重启了没有"。
STARTED_AT = __import__("datetime").datetime.now().strftime("%H:%M:%S")
# 启动脚本拿它和磁盘上代码的改动时间比，判断正在跑的服务是不是已经过时。
STARTED_EPOCH = __import__("time").time()
from .paths import DATA_DIR
CONFIG_FILE = DATA_DIR / "config.json"
DEFAULT = {"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "api_key": "", "supports_vision": False,
           "max_tokens": 32000, "stream": True, "context_budget": 200_000, "max_rounds": 24}


def load():
    return {**DEFAULT, **(json.loads(CONFIG_FILE.read_text("utf-8")) if CONFIG_FILE.exists() else {})}


# ===== 绑定多个模型 =====
# 每个模型一套：显示名、接口地址、模型名、密钥、能不能看图、输出上限……可以绑定好几家服务商，
# 在输入框下面一点就切。正在用的那一套同时铺在配置的顶层字段上（老代码都读顶层，不用改）。
# 密钥只存在本机 data/config.json，接口返回时永远不带。
PROFILE_KEYS = ("base_url", "model", "api_key", "supports_vision", "max_tokens", "stream", "context_budget", "max_rounds")
MAX_PROFILES = 12


def _new_id() -> str:
    import uuid
    return "md" + uuid.uuid4().hex[:6]


def _same(p: dict, data: dict) -> bool:
    return p.get("base_url") == data.get("base_url") and p.get("model") == data.get("model")


def _profiles(data: dict) -> list[dict]:
    """老配置没有清单：把当前这一套当成唯一一个。没有 id 的补上（按地址 + 模型算，刷新后不变）。"""
    import hashlib
    items = [dict(p) for p in data.get("profiles", []) if p.get("model") and p.get("base_url")]
    # 全新安装（没绑过、也没填过密钥）列表是空的：不能把程序里的默认值当成「已经绑了一个模型」给人看
    if not any(_same(p, data) for p in items) and (items or data.get("api_key")):
        items.append({k: data[k] for k in PROFILE_KEYS})
    for p in items:
        p.setdefault("id", "md" + hashlib.sha1(f"{p['base_url']}|{p['model']}".encode("utf-8")).hexdigest()[:6])
        p.setdefault("name", "")
    return items


def _host(url: str) -> str:
    return urlparse(url or "").netloc


def _clean(values: dict, fallback: dict) -> dict:
    """校验一套模型配置；没填的项沿用 fallback（编辑时是原来那套，新增时是当前在用的那套）。"""
    base = str(values.get("base_url", fallback["base_url"]) or "").strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or any(c in base for c in '\n\r"'):
        raise ValueError("请填写有效的 HTTP(S) 接口地址")
    out = {"base_url": base, "model": str(values.get("model", fallback["model"]) or "").strip()}
    if not out["model"]:
        raise ValueError("请填写模型名称")
    out["supports_vision"] = bool(values.get("supports_vision", fallback.get("supports_vision", False)))
    out["stream"] = bool(values.get("stream", fallback.get("stream", True)))
    limit = values.get("max_tokens", fallback.get("max_tokens", 32000))
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1024 <= limit <= 131072:
        raise ValueError("单次输出上限应为 1024–131072 之间的整数")
    out["max_tokens"] = limit
    # 上下文预算：一轮对话最多留多少字符给模型，超了才折叠较早的读取结果（看你模型的上下文窗口填）
    budget = values.get("context_budget", fallback.get("context_budget", 200_000))
    if isinstance(budget, bool) or not isinstance(budget, int) or not 20_000 <= budget <= 2_000_000:
        raise ValueError("上下文预算应为 20000–2000000 之间的整数（按字符算）")
    out["context_budget"] = budget
    rounds = values.get("max_rounds", fallback.get("max_rounds", 24))
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 4 <= rounds <= 60:
        raise ValueError("单次处理轮次上限应为 4–60 之间的整数")
    out["max_rounds"] = rounds
    return out


def _write(data: dict) -> None:
    write_atomic(CONFIG_FILE, json.dumps(data, ensure_ascii=False, indent=2), mode=0o600)


def _activate(data: dict, profile: dict) -> None:
    data.update({k: profile[k] for k in PROFILE_KEYS if k in profile})


def public():
    data = load()
    return {"version": VERSION, "started_at": STARTED_AT,
            "base_url": data["base_url"], "model": data["model"], "has_key": bool(data["api_key"]),
            "supports_vision": data["supports_vision"], "max_tokens": data['max_tokens'], "stream": data['stream'],
            "context_budget": data['context_budget'], "max_rounds": data['max_rounds'],
            "profiles": [{"id": p["id"], "name": p.get("name") or "", "model": p["model"], "base_url": p["base_url"],
                          "host": _host(p["base_url"]), "supports_vision": bool(p.get("supports_vision")),
                          "stream": bool(p.get("stream", True)), "max_tokens": p.get("max_tokens", 32000),
                          "context_budget": p.get("context_budget", 200_000), "max_rounds": p.get("max_rounds", 24),
                          "has_key": bool(p.get("api_key")), "active": _same(p, data)} for p in _profiles(data)]}


def save_profile(values: dict, profile_id: str = "", activate: bool = False):
    """新增或修改一个绑定的模型。

    密钥留空：改原来那套时沿用它自己的密钥；新增时如果已经绑过同一家服务商，借用那家的密钥
    （同一家换个模型不用再贴一次）。换到别家却没填密钥就拦下——不能把 A 家的密钥发给 B 家。
    """
    data = load()
    items = _profiles(data)
    prev = next((p for p in items if p["id"] == profile_id), None) if profile_id else None
    if profile_id and not prev:
        raise ValueError("没有这个模型，可能已经删掉了")
    current = next((p for p in items if _same(p, data)), items[0] if items else {k: data[k] for k in PROFILE_KEYS})
    entry = _clean(values, prev or current)
    key = str(values.get("api_key") or "").strip()
    if key:
        if any(c in key for c in '\r\n"'):
            raise ValueError("密钥格式无效")
    elif prev and _host(prev["base_url"]) == _host(entry["base_url"]) and prev.get("api_key"):
        key = prev["api_key"]
    else:
        same_host = next((p for p in items if _host(p["base_url"]) == _host(entry["base_url"]) and p.get("api_key")), None)
        if same_host:
            key = same_host["api_key"]
        else:
            raise ValueError(f"填一下 {_host(entry['base_url'])} 的 API 密钥。"
                             + ("接口地址换成了另一个服务商，留空会把原来的密钥发给新地址，已阻止。" if prev else ""))
    entry["api_key"] = key
    if any(p is not prev and _same(p, entry) for p in items):
        raise ValueError("这个模型已经绑定过了，在列表里直接用它就行")
    entry["id"] = prev["id"] if prev else _new_id()
    entry["name"] = str(values.get("name") or (prev or {}).get("name") or "").strip()[:30]
    was_active = bool(prev and _same(prev, data))
    items = [p for p in items if p is not prev] + [entry] if not prev else [entry if p is prev else p for p in items]
    if len(items) > MAX_PROFILES:
        raise ValueError(f"最多绑定 {MAX_PROFILES} 个模型，先删掉不用的")
    data["profiles"] = items
    if activate or was_active:
        _activate(data, entry)
    _write(data)
    return {**public(), "saved_id": entry["id"]}


def save(values):
    """老接口：改正在用的那一套。"""
    data = load()
    current = next((p for p in _profiles(data) if _same(p, data)), None)
    return save_profile(values, current["id"] if current else "", activate=True)


def profile_settings(profile_id: str = "") -> dict:
    """测试连接用：某一套的完整配置（含密钥，只在服务端用）。"""
    data = load()
    if not profile_id:
        return data
    p = next((p for p in _profiles(data) if p["id"] == profile_id), None)
    if not p:
        raise ValueError("没有这个模型")
    return {**data, **{k: p[k] for k in PROFILE_KEYS if k in p}}


def switch(profile_id: str):
    """切到绑定过的那一套：地址、模型、密钥、能力一起换，不用重填"""
    data = load()
    items = _profiles(data)
    p = next((p for p in items if p["id"] == profile_id), None)
    if not p:
        raise ValueError("没有这个模型，可能已经删掉了")
    data["profiles"] = items
    _activate(data, p)
    _write(data)
    return public()


def forget_profile(profile_id: str):
    data = load()
    items = _profiles(data)
    target = next((p for p in items if p["id"] == profile_id), None)
    if not target:
        raise ValueError("没有这个模型")
    if _same(target, data):
        raise ValueError("正在用的模型不能删，先切到别的")
    data["profiles"] = [p for p in items if p is not target]
    _write(data)
    return public()
