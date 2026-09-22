"""原子写：写到一半失败时，原文件必须一个字节都没动。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.atomicio import write_atomic, TMP_PREFIX   # noqa: E402

GOOD = json.dumps({"pages": list(range(200)), "memory": ["按钮用蓝色"]}, ensure_ascii=False)


class WriteAtomic(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "project.json"
        self.path.write_text(GOOD, "utf-8")
        self.addCleanup(self.dir.cleanup)

    def test_写入成功时内容正确(self):
        write_atomic(self.path, "新内容 new")
        self.assertEqual(self.path.read_text("utf-8"), "新内容 new")

    def test_写入中途抛错时原文件不变(self):
        class Boom(str):
            def encode(self, *a, **k):
                raise OSError("No space left on device")
        with self.assertRaises(OSError):
            write_atomic(self.path, Boom("x" * 1000))
        self.assertEqual(self.path.read_text("utf-8"), GOOD)
        self.assertTrue(json.loads(self.path.read_text("utf-8")))

    def test_失败后不留临时文件(self):
        class Boom(str):
            def encode(self, *a, **k):
                raise OSError("boom")
        with self.assertRaises(OSError):
            write_atomic(self.path, Boom("x"))
        self.assertEqual([p.name for p in Path(self.dir.name).iterdir()
                          if p.name.startswith(TMP_PREFIX)], [])

    def test_进程被杀时原文件完好(self):
        """旧的 open(path,'w') 写法会在这里留下半截文件；原子写不会。"""
        child = ROOT / "backend" / "tests" / "_slow_write.py"
        proc = subprocess.Popen([sys.executable, str(child), str(self.path)])
        time.sleep(1.2)          # 让它写完临时文件、停在 os.replace 之前
        proc.kill()
        proc.wait()
        self.assertEqual(self.path.read_text("utf-8"), GOOD,
                         "被杀之后原文件必须还是完整的旧版")

    def test_下次写入会清掉遗留的临时文件(self):
        orphan = self.path.parent / f"{TMP_PREFIX}{self.path.name}.999.tmp"
        orphan.write_text("垃圾")
        write_atomic(self.path, "新内容")
        self.assertFalse(orphan.exists())

    def test_沿用已存在文件的权限(self):
        os.chmod(self.path, 0o644)
        write_atomic(self.path, "内容")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o644)

    def test_新建文件默认只有本人可读写(self):
        fresh = Path(self.dir.name) / "config.json"
        write_atomic(fresh, "{}")
        self.assertEqual(fresh.stat().st_mode & 0o777, 0o600)

    def test_可以指定权限(self):
        key = Path(self.dir.name) / "key.json"
        write_atomic(key, "{}", mode=0o600)
        self.assertEqual(key.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()


class ConfigLimits(unittest.TestCase):
    """上限由用户按自己模型的真实能力设，代码里不再拍脑袋写死。"""

    def setUp(self):
        from backend import config
        self.config = config
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._file = config.CONFIG_FILE
        self.addCleanup(lambda: setattr(config, "CONFIG_FILE", self._file))
        config.CONFIG_FILE = Path(self.tmp.name) / "config.json"

    def save(self, **kw):
        base = {"base_url": "https://api.deepseek.com", "model": "m", "api_key": "sk-x"}
        return self.config.save({**base, **kw})

    def test_三个上限都存得下也读得回(self):
        got = self.save(max_tokens=64000, context_budget=800_000, max_rounds=40)
        self.assertEqual(got["max_tokens"], 64000)
        self.assertEqual(got["context_budget"], 800_000)
        self.assertEqual(got["max_rounds"], 40)

    def test_默认值比原来宽得多(self):
        got = self.save()
        self.assertGreaterEqual(got["max_tokens"], 32000, "原来默认 16000，写不完一个页面")
        self.assertGreaterEqual(got["context_budget"], 200_000,
                                "原来写死 60000，比一份组件库还小，读进来当场被折叠")

    def test_离谱的值会被挡下来(self):
        for bad in ({"max_tokens": 999_999}, {"context_budget": 100},
                    {"max_rounds": 500}, {"max_rounds": 0}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.save(**bad)

    def test_不填就沿用已保存的值(self):
        self.save(context_budget=500_000, max_rounds=30)
        got = self.save()
        self.assertEqual(got["context_budget"], 500_000, "改别的设置不该把上限重置回默认")
        self.assertEqual(got["max_rounds"], 30)
