"""桌面版外壳：存文件、下载、端口、数据目录。不用真的开窗口"""
import http.server
import importlib.util
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('desktop_app', ROOT / 'desktop' / 'app.py')
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


class DesktopTest(unittest.TestCase):
    def test_filename_from_header(self):
        self.assertEqual(desktop._filename("attachment; filename*=UTF-8''%E5%8E%9F%E5%9E%8B.zip", 'x'), '原型.zip')
        self.assertEqual(desktop._filename('attachment; filename="a b.html"', 'x'), 'a b.html')
        self.assertEqual(desktop._filename('', 'fallback.html'), 'fallback.html')

    def test_port_in_fixed_range(self):
        # 端口固定：界面记住的语言、面板状态按地址存，端口一变就丢了
        self.assertIn(desktop._pick_port(), desktop.PORTS)

    def test_download_and_save(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'<html>ok</html>'
                self.send_response(200)
                self.send_header('Content-Disposition', "attachment; filename*=UTF-8''%E9%A1%B5%E9%9D%A2.html")
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body)
            def log_message(self, *args): pass
        server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                bridge = desktop.Bridge(server.server_address[1])
                asked = []
                bridge._ask_path = lambda name: asked.append(name) or Path(tmp) / name
                self.assertTrue(bridge.download('/api/projects/p/export'))
                self.assertEqual(asked, ['页面.html'])
                self.assertEqual((Path(tmp) / '页面.html').read_bytes(), b'<html>ok</html>')
                self.assertTrue(bridge.save_text('图.html', '<p>图</p>'))
                self.assertEqual((Path(tmp) / '图.html').read_text('utf-8'), '<p>图</p>')
                bridge._ask_path = lambda name: None   # 对话框里点了取消
                self.assertFalse(bridge.save_text('x.html', 'x'))
                with self.assertRaises(ValueError):
                    bridge.download('http://example.com/x')
        finally:
            server.shutdown(); server.server_close()

    def test_bridge_exposes_only_methods(self):
        # pywebview 会把 js_api 的公开属性都交给界面：窗口对象之类必须藏起来
        public = [n for n in vars(desktop.Bridge(1)) if not n.startswith('_')]
        self.assertEqual(public, [])

    def test_user_data_goes_to_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = ('from backend import paths, config, storage, skills, components;'
                    'print(config.CONFIG_FILE.parent.parent, storage.DATA_ROOT.parent.parent, skills.ROOT.parents[1],'
                    ' components.ROOT.parents[1], paths.SPEC_FILE.exists(), paths.PROMPTS == paths.APP_ROOT / "prompts")')
            out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True,
                                 env={**os.environ, 'PROTOTYPE_STUDIO_HOME': tmp}, check=True).stdout.split()
            self.assertEqual({Path(x).resolve() for x in out[:4]}, {Path(tmp).resolve()})
            self.assertEqual(out[4:], ['True', 'True'])   # 自带的设计规范复制了一份过去


    def test_app_bundle_carries_nothing_personal(self):
        # 应用要能发给别人：项目、模型设置、自己装的 skill 和组件都不打进 .app
        for spec_name in ('prototype_studio.spec', 'prototype_studio_win.spec'):
            spec_text = (ROOT / 'desktop' / spec_name).read_text('utf-8')
            datas = spec_text[spec_text.index('datas = ['):spec_text.index('hidden =')]
            for personal in ("'data'", "'skills'", "'components'", "os.path.join(ROOT, 'prompts'), 'prompts'"):
                self.assertNotIn(personal, datas, spec_name)
        script = (ROOT / 'scripts' / '打包Mac应用.command').read_text('utf-8')
        self.assertIn('desktop/release_check.py "$APP"', script)
        self.assertIn("desktop/release_check.py', str(app)", (ROOT / 'desktop' / 'build_windows.py').read_text('utf-8'))
        self.assertNotIn('ditto data "$SUPPORT/data"', script)   # 模型设置不复制


    def test_release_check_finds_personal_stuff(self):
        spec2 = importlib.util.spec_from_file_location('release_check', ROOT / 'desktop' / 'release_check.py')
        rc = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(rc)
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / 'App'
            (app / 'prompts').mkdir(parents=True)
            (app / 'prompts' / 'agent-system.md').write_text('规则', 'utf-8')
            rc.own_keys = lambda: {b'sk-secret-123456'}
            self.assertIn('自带的风格', '\n'.join(rc.check(app)))   # 自带风格没打进去也要拦
            (app / 'prompts' / 'styles' / '简洁后台').mkdir(parents=True)
            (app / 'prompts' / 'styles' / '简洁后台' / 'SKILL.md').write_text('# 简洁后台', 'utf-8')
            self.assertEqual(rc.check(app), [])
            (app / 'prompts' / 'styles' / '简洁后台' / 'x.md').write_text('零碳园区', 'utf-8')
            self.assertIn('混进了你自己的 skill', '\n'.join(rc.check(app)))
            (app / 'prompts' / 'styles' / '简洁后台' / 'x.md').write_text('', 'utf-8')
            (app / 'lib.bin').write_bytes(b'xx sk-secret-123456 xx')
            (app / 'prompts' / 'skills').mkdir()
            (app / 'data' / 'projects').mkdir(parents=True)
            found = '\n'.join(rc.check(app))
            self.assertIn('API 密钥', found); self.assertIn('skills', found); self.assertIn('data', found)


if __name__ == '__main__':
    unittest.main()
