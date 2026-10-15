"""回收站彻底删除：只删回收站里的，删项目连带删掉它的副本、版本和展开结果；删页面不碰别的页面。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage   # noqa: E402


class 彻底删除(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = storage.DATA_ROOT
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project("测试")["id"]
        src = storage.project_dir(self.pid) / "source"
        (src / "a.html").write_text("<html>a</html>", encoding="utf-8")
        (src / "b.html").write_text("<html>b</html>", encoding="utf-8")
        self.a = storage.add_page(self.pid, "a.html")["id"]
        self.b = storage.add_page(self.pid, "b.html")["id"]
        storage.save_expand_entry(self.pid, self.a, "#x", "h", {"nodes": []})

    def tearDown(self):
        storage.DATA_ROOT = self.old
        self.tmp.cleanup()

    def test_不在回收站的不能彻底删除(self):
        with self.assertRaises(ValueError):
            storage.purge_item(self.pid)
        with self.assertRaises(ValueError):
            storage.purge_item(self.pid, self.a)

    def test_删页面只删它自己(self):
        storage.trash_item(self.pid, self.a)
        storage.purge_item(self.pid, self.a)
        pdir = storage.project_dir(self.pid)
        meta = storage.load_meta(self.pid)
        self.assertEqual([p["id"] for p in meta["pages"]], [self.b])
        self.assertFalse((pdir / "source" / "a.html").exists())
        self.assertTrue((pdir / "source" / "b.html").exists())
        self.assertFalse((pdir / "expand" / self.a).exists())
        self.assertFalse((pdir / "versions" / self.a).exists())
        self.assertEqual(storage.list_trash(), [])

    def test_删项目整个目录没了_清空回收站(self):
        other = storage.create_project("留着")["id"]
        storage.trash_item(self.pid)
        self.assertEqual(storage.purge_all(), 1)
        self.assertFalse(storage.project_dir(self.pid).exists())
        self.assertTrue(storage.project_dir(other).exists())
        self.assertEqual(storage.list_trash(), [])


if __name__ == "__main__":
    unittest.main()
