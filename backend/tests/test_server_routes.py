"""接口拆到 routes/ 以后，整条路走一遍：每个领域挑几个接口真的发请求（要装 fastapi，装不了就跳过）。"""
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import skills, storage   # noqa: E402
try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from fastapi.testclient import TestClient
    from backend import server
except ImportError:
    server = None


@unittest.skipIf(server is None, "没装 fastapi")
class 接口走一遍(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = storage.DATA_ROOT, skills.ROOT
        storage.DATA_ROOT = Path(self.tmp.name) / "projects"
        storage.DATA_ROOT.mkdir()
        skills.ROOT = Path(self.tmp.name) / "skills"
        skills.ROOT.mkdir()
        self.c = TestClient(server.app)

    def tearDown(self):
        storage.DATA_ROOT, skills.ROOT = self.old
        self.tmp.cleanup()

    def test_各领域的接口都挂上了(self):
        self.assertEqual(self.c.get("/api/health").json()["ok"], True)                       # settings
        self.assertEqual(len(self.c.get("/api/styles").json()["builtin"]), 9)
        meta = self.c.post("/api/projects/new", json={"name": "订单", "style": "builtin:简洁后台"}).json()   # projects
        pid, page = meta["id"], meta["pages"][0]["id"]
        self.assertEqual(self.c.get(f"/api/projects/{pid}").json()["style"], "builtin:简洁后台")
        preview = self.c.get(f"/preview/{pid}/{page}")                                       # pages
        self.assertEqual(preview.status_code, 200)
        self.assertIn("sandbox", preview.headers["content-security-policy"])
        self.assertIn("prototype-agent", preview.text)   # 注入了预览桥接脚本
        self.assertTrue(self.c.get(f"/api/projects/{pid}/pages/{page}/source").json()["hash"])
        self.assertEqual(self.c.put(f"/api/projects/{pid}/style", json={"style": "builtin:数据大屏"}).json()["swapped"], 1)
        self.assertIn("memory", self.c.get(f"/api/projects/{pid}/memory").json())            # memory
        self.assertEqual(self.c.post(f"/api/projects/{pid}/agent/stop", json={"run_id": "x"}).json(), {"ok": False})   # agent_runs

    def test_安全检查和错误处理还在(self):
        self.assertEqual(self.c.post("/api/projects/new", json={"name": "x"}, headers={"origin": "http://evil.example"}).status_code, 403)
        self.assertEqual(self.c.get("/api/health", headers={"host": "evil.example"}).status_code, 400)
        self.assertEqual(self.c.get("/api/projects/p_0123456789").status_code, 404)
        self.assertEqual(self.c.get("/api/no-such-api").status_code, 404)   # 不会落到界面文件的兜底路由上
        self.assertEqual(self.c.post("/api/projects/new", json={"name": "x", "style": "builtin:没有"}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
