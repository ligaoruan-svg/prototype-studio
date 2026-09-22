#!/bin/bash
# 双击这个文件即可启动原型工坊。首次运行会自动建虚拟环境并安装依赖。
# 关闭这个终端窗口即停止服务。
cd "$(dirname "$0")" || exit 1
PORT=5173
URL="http://127.0.0.1:$PORT"

if curl -s --max-time 1 "$URL/api/health" >/dev/null 2>&1; then
  echo "原型工坊已经在运行，直接打开浏览器。"
  open "$URL"
  exit 0
fi

if [ ! -d .venv ]; then
  echo "首次运行：正在创建虚拟环境，需要一两分钟…"
  python3 -m venv .venv || { echo "创建失败。请确认已安装 Python 3.10 以上版本。"; read -r -p "按回车关闭"; exit 1; }
fi

# shellcheck disable=SC1091
source .venv/bin/activate || { echo "虚拟环境损坏。删掉 .venv 文件夹后重试。"; read -r -p "按回车关闭"; exit 1; }

echo "正在检查依赖…"
if ! pip install -q -e . ; then
  echo "依赖安装失败。检查网络后重试。"
  read -r -p "按回车关闭"
  exit 1
fi

echo ""
echo "启动中，浏览器会自动打开：$URL"
echo "关闭这个窗口即停止服务。"
echo ""
( sleep 2; open "$URL" ) &
exec python3 -m uvicorn backend.server:app --host 127.0.0.1 --port "$PORT"
