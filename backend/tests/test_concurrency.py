"""同时改 project.json / 同时写同一个文件，不能互相盖掉。

后端的接口跑在线程池里：提交修改的同时记一条意见、两个展开结果同时落盘，都是日常会发生的。
"""
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, memory   # noqa: E402
from backend.atomicio import write_atomic   # noqa: E402


class 并发写(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = storage.DATA_ROOT
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project("并发")["id"]
        (storage.project_dir(self.pid) / "source" / "index.html").write_text("<html><body></body></html>", encoding="utf-8")
        self.page = storage.add_page(self.pid, "index.html")["id"]

    def tearDown(self):
        storage.DATA_ROOT = self.old
        self.tmp.cleanup()

    def test_同一个文件多个线程同时写不报错(self):
        target = Path(self.tmp.name) / "same.json"
        errors = []
        def worker(n):
            for i in range(20):
                try:
                    write_atomic(target, f"{n}-{i}" * 2000)
                except Exception as e:   # noqa: BLE001
                    errors.append(e)
        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertEqual(errors, [])
        text = target.read_text()
        self.assertEqual(text, text[:len(text) // 2000] * 2000)   # 读到的是某一次完整的写入

    def test_同时记意见和记忆一条都不丢(self):
        def notes(n):
            for i in range(15):
                storage.add_annotation(self.pid, self.page, {"selector": "body", "note": f"意见{n}-{i}"})
        def memos():
            for i in range(15):
                memory.add(self.pid, f"记住第{i}条")
        threads = [threading.Thread(target=notes, args=(n,)) for n in range(3)] + [threading.Thread(target=memos)]
        [t.start() for t in threads]; [t.join() for t in threads]
        meta = storage.load_meta(self.pid)
        self.assertEqual(len(storage.active_annotations(meta, self.page)), 45)
        self.assertEqual(len(meta.get("memory", [])), min(15, memory.MAX_ITEMS))


if __name__ == "__main__":
    unittest.main()
