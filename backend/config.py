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
CONFIG_FILE = Path(__file__).resolve().parents[1] / "data" / "config.json"
DEFAULT = {"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "api_key": "", "supports_vision": False,
           "max_tokens": 32000, "stream": True, "context_budget": 200_000, "max_rounds": 24}


def load():
    return {**DEFAULT, **(json.loads(CONFIG_FILE.read_text("utf-8")) if CONFIG_FILE.exists() else {})}


def public():
    data = load()
    return {"version": VERSION, "started_at": STARTED_AT,
            "base_url": data["base_url"], "model": data["model"], "has_key": bool(data["api_key"]),
            "supports_vision": data["supports_vision"], "max_tokens": data['max_tokens'], "stream": data['stream'],
            "context_budget": data['context_budget'], "max_rounds": data['max_rounds']}


def save(values):
    data = load()
    base = values.get("base_url", data["base_url"]).strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or any(c in base for c in '\n\r"'):
        raise ValueError("请填写有效的 HTTP(S) 接口地址")
    # 换了服务商却留空密钥，旧密钥会被原样发到新域名去——这是实打实的凭据泄露。
    if (urlparse(data["base_url"]).netloc and parsed.netloc != urlparse(data["base_url"]).netloc
            and data["api_key"] and not values.get("api_key")):
        raise ValueError("接口地址换成了另一个服务商，请同时填写该服务商的密钥。"
                         "留空会把原来的密钥发给新地址，已阻止。")
    data.update(base_url=base, model=values.get("model", data["model"]).strip())
    data["supports_vision"] = bool(values.get('supports_vision', data['supports_vision']))
    data['stream'] = bool(values.get('stream', data['stream']))
    limit = values.get('max_tokens', data['max_tokens'])
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1024 <= limit <= 131072:
        raise ValueError('单次输出上限应为 1024–131072 之间的整数')
    data['max_tokens'] = limit
    # 上下文预算：一轮对话最多留多少字符给模型，超了才折叠较早的读取结果。
    # 原来写死 60000，比一份组件库还小——读进来当场被折叠，等于白读。
    # 这个数只有你知道该填多少（看你模型的上下文窗口），所以放在设置里。
    budget = values.get('context_budget', data.get('context_budget', 200_000))
    if isinstance(budget, bool) or not isinstance(budget, int) or not 20_000 <= budget <= 2_000_000:
        raise ValueError('上下文预算应为 20000–2000000 之间的整数（按字符算）')
    data['context_budget'] = budget
    rounds = values.get('max_rounds', data.get('max_rounds', 24))
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not 4 <= rounds <= 60:
        raise ValueError('单次处理轮次上限应为 4–60 之间的整数')
    data['max_rounds'] = rounds
    if not data["model"]:
        raise ValueError("请填写模型名称")
    if values.get("api_key"):
        key = values["api_key"].strip()
        if any(c in key for c in '\r\n"'):
            raise ValueError("密钥格式无效")
        data["api_key"] = key
    write_atomic(CONFIG_FILE, json.dumps(data, ensure_ascii=False, indent=2), mode=0o600)
    return public()
