#!/bin/bash
# 双击这个文件即可启动原型工坊。首次运行会自动建虚拟环境并安装依赖。
# 关闭这个终端窗口即停止服务。
cd "$(dirname "$0")/.." || exit 1   # 脚本放在 scripts/ 里，干活要在项目根目录
PORT=5173
URL="http://127.0.0.1:$PORT"

# 磁盘上代码最后一次改动的时间。
code_mtime() {
  python3 - <<'PY' 2>/dev/null || echo 0
import os
newest = 0.0
for root in ("backend", "frontend/dist", "prompts"):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", "tests", ".git"}]
        for name in filenames:
            if name.endswith((".py", ".js", ".css", ".html", ".md")):
                try: newest = max(newest, os.path.getmtime(os.path.join(dirpath, name)))
                except OSError: pass
print(int(newest))
PY
}

health=$(curl -s --max-time 1 "$URL/api/health" 2>/dev/null)
if [ -n "$health" ]; then
  started=$(printf '%s' "$health" | python3 -c 'import sys,json;print(int(json.load(sys.stdin).get("started_epoch",0)))' 2>/dev/null || echo 0)
  newest=$(code_mtime)
  # 服务已经在跑，但代码比它新——这种时候直接打开浏览器，看到的还是旧版本，
  # 以前改了半天"还是一样"就是卡在这里。现在把它说出来，并且能就地重启。
  if [ "$started" -gt 0 ] && [ "$newest" -gt "$started" ]; then
    echo "正在运行的服务是旧的（代码在它启动之后又改过）。"
    read -r -p "重启服务用上新代码？[Y/n] " answer
    case "$answer" in
      [nN]*) echo "保持原样，打开浏览器。"; open "$URL"; exit 0 ;;
    esac
    echo "正在停掉旧服务…"
    lsof -ti "tcp:$PORT" | xargs kill 2>/dev/null
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      curl -s --max-time 1 "$URL/api/health" >/dev/null 2>&1 || break
      sleep 0.5
    done
  else
    echo "原型工坊已经在运行，直接打开浏览器。"
    open "$URL"
    exit 0
  fi
fi

if [ ! -d .venv ]; then
  echo "首次运行：正在创建虚拟环境，需要一两分钟…"
  python3 -m venv .venv || { echo "创建失败。请确认已安装 Python 3.10 以上版本。"; read -r -p "按回车关闭"; exit 1; }
fi

# shellcheck disable=SC1091
source .venv/bin/activate || { echo "虚拟环境损坏。删掉 .venv 文件夹后重试。"; read -r -p "按回车关闭"; exit 1; }

echo "正在检查依赖…"
# 以前每次启动都 pip install -e .：要先联网下 setuptools 打包本项目，网络或代理一抽风（SSL 报错）就启动不了。
# 现在：依赖装好了、pyproject.toml 没变，就不联网；要装也只装运行要用的几个包（都有现成的安装包，不用打包本项目）；
# 联网失败但之前装好的够用，照常启动。
STAMP=.venv/.deps-ok
want=$(shasum pyproject.toml 2>/dev/null | cut -d' ' -f1)
deps_ready() {
  python - <<'PY' >/dev/null 2>&1
import importlib.metadata as m
for name in ("fastapi", "uvicorn", "python-multipart", "beautifulsoup4"):
    m.version(name)
PY
}
if [ -n "$want" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$want" ] && deps_ready; then
  :
else
  python - > .venv/requirements-run.txt <<'PY'
import re
text = open("pyproject.toml", encoding="utf-8").read()
block = re.search(r"^dependencies\s*=\s*\[(.*?)^\]", text, re.S | re.M)   # 到行首的 ] 为止：uvicorn[standard] 里也有 ]
print("\n".join(re.findall(r'"([^"]+)"', block.group(1))) if block else "")
PY
  if pip install -q -r .venv/requirements-run.txt; then
    echo "$want" > "$STAMP"
  elif deps_ready; then
    echo "联网检查依赖没成功（多半是网络或代理），不过之前装好的够用，照常启动。"
  else
    echo "依赖安装失败。检查网络后重试；开着代理的话，试试换个节点或先关掉代理。"
    read -r -p "按回车关闭"
    exit 1
  fi
fi

echo ""
echo "启动中，浏览器会自动打开：$URL"
echo "关闭这个窗口即停止服务。"
echo ""
( sleep 2; open "$URL" ) &
exec python3 -m uvicorn backend.server:app --host 127.0.0.1 --port "$PORT"
