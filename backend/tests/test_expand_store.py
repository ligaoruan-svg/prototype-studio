"""展开快照落盘：一键展开全部页面要几分钟，重启服务、刷新浏览器都不能白跑。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage   # noqa: E402


class 展开快照(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = storage.DATA_ROOT
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project("测试")["id"]
        (storage.project_dir(self.pid) / "source" / "index.html").write_text("<html></html>", encoding="utf-8")
        self.page = storage.add_page(self.pid, "index.html")["id"]

    def tearDown(self):
        storage.DATA_ROOT = self.old
        self.tmp.cleanup()

    def test_每个页面单独存_读回来按路由分好(self):
        storage.save_expand_routes(self.pid, self.page, [{"hash": "#factor-list", "title": "环境影响因子库清单"}, {"hash": "#factor-manage", "title": "环境影响因子库管理"}])
        storage.save_expand_entry(self.pid, self.page, "#factor-list", "v12hash", {"nodes": [{"id": 1, "title": "设为当前版本"}]})
        storage.save_expand_entry(self.pid, self.page, "#factor-manage", "v12hash", {"nodes": []})
        data = storage.load_expand(self.pid, self.page)
        self.assertEqual([r["hash"] for r in data["routes"]], ["#factor-list", "#factor-manage"])
        self.assertEqual(data["entries"]["#factor-list"]["result"]["nodes"][0]["title"], "设为当前版本")
        self.assertEqual(data["entries"]["#factor-list"]["hash"], "v12hash")

    def test_同一路由再存一次是覆盖_不会越堆越多(self):
        for version in ("a", "b", "c"):
            storage.save_expand_entry(self.pid, self.page, "#overview", version, {"nodes": []})
        data = storage.load_expand(self.pid, self.page)
        self.assertEqual(list(data["entries"]), ["#overview"])
        self.assertEqual(data["entries"]["#overview"]["hash"], "c")

    def test_没展开过就是空的(self):
        self.assertEqual(storage.load_expand(self.pid, self.page), {"routes": [], "entries": {}})

    def test_页面编号不能拿来穿目录(self):
        with self.assertRaises(ValueError):
            storage.save_expand_entry(self.pid, "../../etc", "#x", "h", {})


if __name__ == "__main__":
    unittest.main()
