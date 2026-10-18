"""原型工坊桌面版：在本机起服务，开一个原生窗口装界面——双击就用，不用开终端和浏览器。

- 打成 .app 后，项目、模型设置、记忆都放在 ~/Library/Application Support/原型工坊，
  .app 本身只读，升级时整个替换也不会丢东西
- 从源码直接跑（python3 desktop/app.py）用的还是项目目录里的 data/，方便调试
- 关掉窗口就退出，后台服务一起停
"""
from __future__ import annotations

import json
import logging
import os
import re
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

APP_NAME = '原型工坊'
FROZEN = getattr(sys, 'frozen', False)
SUPPORT = Path.home() / 'Library' / 'Application Support' / APP_NAME
if FROZEN:
    os.environ.setdefault('PROTOTYPE_STUDIO_HOME', str(SUPPORT))
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
HOME = Path(os.environ.get('PROTOTYPE_STUDIO_HOME') or Path(__file__).resolve().parents[1])

# 从「程序坞」打开的应用拿不到终端里的 PATH：node（脚本语法检查要用）多半装在这些地方
def _extend_path() -> None:
    extra = ['/opt/homebrew/bin', '/usr/local/bin', str(Path.home() / '.volta' / 'bin')]
    nvm = Path.home() / '.nvm' / 'versions' / 'node'
    if nvm.is_dir():
        extra += [str(p / 'bin') for p in sorted(nvm.iterdir(), reverse=True)]
    parts = os.environ.get('PATH', '/usr/bin:/bin:/usr/sbin:/sbin').split(':')
    os.environ['PATH'] = ':'.join(parts + [p for p in extra if p not in parts and Path(p).is_dir()])


# .app 没有终端可以打印：输出都记到日志里，出问题时看 ~/Library/Application Support/原型工坊/logs/app.log
def _setup_log() -> Path:
    folder = HOME / 'logs'
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / 'app.log'
    if log.exists() and log.stat().st_size > 2_000_000:
        log.replace(folder / 'app.log.1')
    if FROZEN:
        stream = open(log, 'a', buffering=1, encoding='utf-8')
        sys.stdout = sys.stderr = stream
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s',
                        handlers=[logging.StreamHandler(sys.stderr)])
    return log


# 端口固定在一小段里：界面的语言、收起的面板这些记在 WebView 里，按地址存，端口一变就忘了
PORTS = range(51730, 51740)


def _pick_port() -> int:
    for port in PORTS:
        with socket.socket() as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _start_server(port: int):
    import uvicorn
    from backend.server import app as api
    server = uvicorn.Server(uvicorn.Config(api, host='127.0.0.1', port=port, log_level='warning',
                                           access_log=False, log_config=None))
    thread = threading.Thread(target=server.run, name='server', daemon=True)
    thread.start()
    deadline = time.time() + 30
    while time.time() < deadline and thread.is_alive():
        if server.started:
            return server
        time.sleep(0.05)
    raise RuntimeError('本地服务没能启动' if thread.is_alive() else '本地服务启动失败')


def _filename(header: str, fallback: str) -> str:
    m = re.search(r"filename\*=UTF-8''([^;]+)", header or '', re.I)
    if m:
        return urllib.parse.unquote(m.group(1))
    m = re.search(r'filename="?([^";]+)"?', header or '', re.I)
    return m.group(1) if m else fallback


class Bridge:
    """界面里 window.pywebview.api 调到的几个原生能力：存文件要弹「存储为」对话框"""

    def __init__(self, port: int):
        self._port = port
        self._window = None   # 下划线开头：pywebview 不会把它当成界面能调的接口

    def _ask_path(self, name: str) -> Path | None:
        import webview
        mode = webview.FileDialog.SAVE if hasattr(webview, 'FileDialog') else webview.SAVE_DIALOG
        picked = self._window.create_file_dialog(mode, directory=str(Path.home() / 'Downloads'),
                                                save_filename=name)
        if not picked:
            return None
        return Path(picked[0] if isinstance(picked, (list, tuple)) else picked)

    def save_text(self, name: str, text: str) -> bool:
        path = self._ask_path(name)
        if not path:
            return False
        path.write_text(text, 'utf-8')
        return True

    def download(self, url: str) -> bool:
        if not url.startswith('/'):
            raise ValueError('只能下载本机服务里的文件')
        with urllib.request.urlopen(f'http://127.0.0.1:{self._port}{url}', timeout=120) as response:
            data = response.read()
            name = _filename(response.headers.get('Content-Disposition', ''), url.rstrip('/').rsplit('/', 1)[-1])
        path = self._ask_path(name)
        if not path:
            return False
        path.write_bytes(data)
        return True


def _error_page(message: str, log: Path) -> str:
    return (f"<html><body style='font:14px -apple-system,sans-serif;padding:48px;color:#141413;background:#faf9f5'>"
            f"<h2>{APP_NAME}没能启动</h2><p>{message}</p>"
            f"<p style='color:#6f6e69'>详细原因记在：{log}</p></body></html>")


def main() -> None:
    _extend_path()
    log = _setup_log()
    import webview
    webview.settings['ALLOW_DOWNLOADS'] = True
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
    port = _pick_port()
    bridge = Bridge(port)
    try:
        server = _start_server(port)
    except Exception as exc:   # 服务起不来也要开窗口说清楚，不能双击了没反应
        logging.exception('server failed')
        webview.create_window(APP_NAME, html=_error_page(str(exc), log), width=640, height=360)
        webview.start()
        return
    logging.info('serving on 127.0.0.1:%s, home=%s', port, HOME)
    bridge._window = webview.create_window(APP_NAME, f'http://127.0.0.1:{port}/', js_api=bridge,
                                          width=1440, height=900, min_size=(1080, 680),
                                          background_color='#FAF9F5', text_select=True)
    webview.start(private_mode=False, storage_path=str(HOME / 'webview'))
    server.should_exit = True


if __name__ == '__main__':
    main()
