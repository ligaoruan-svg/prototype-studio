"""导出的文件名：项目名-页面名-v版本，不再是 index.html / p_xxx.zip"""
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage   # noqa: E402

try:
    from fastapi.testclient import TestClient
    from backend.server import app
except Exception:   # 没装 fastapi 的环境跳过
    TestClient = None


@unittest.skipIf(TestClient is None, "没装 fastapi")
class 导出文件名(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = storage.DATA_ROOT
        storage.DATA_ROOT = Path(self.tmp.name)
        self.c = TestClient(app)
        self.pid = storage.create_project('物业管理/后台')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text('<html><body>x</body></html>', encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html', '费用账单')['id']

    def tearDown(self):
        storage.DATA_ROOT = self.old
        self.tmp.cleanup()

    def name(self, response):
        header = response.headers['content-disposition']
        return unquote(header.split("filename*=UTF-8''")[1])

    def test_单页(self):
        r = self.c.get(f'/api/projects/{self.pid}/pages/{self.page}/download')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.name(r), '物业管理_后台-费用账单-v1.html')

    def test_整个项目(self):
        r = self.c.get(f'/api/projects/{self.pid}/export')
        self.assertEqual(self.name(r), '物业管理_后台.zip')
        self.assertIn('filename="', r.headers['content-disposition'])


if __name__ == '__main__':
    unittest.main()
