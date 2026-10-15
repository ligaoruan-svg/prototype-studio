"""存过的模型一点就能切：地址、模型、密钥一起换；接口返回永远不带密钥。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import config   # noqa: E402


class 切换模型(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.CONFIG_FILE
        config.CONFIG_FILE = Path(self.tmp.name) / "config.json"

    def tearDown(self):
        config.CONFIG_FILE = self.old
        self.tmp.cleanup()

    def save(self, **kw):
        base = {"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "api_key": "sk-a", "supports_vision": True,
                "max_tokens": 16000, "stream": True, "context_budget": 200000, "max_rounds": 24}
        return config.save({**base, **kw})

    def test_保存过的都能切回来_密钥跟着走(self):
        self.save()
        out = self.save(model="deepseek-v4-pro", supports_vision=False)
        self.assertEqual([p["model"] for p in out["profiles"]], ["deepseek-flash", "deepseek-v4-pro"])
        flash = next(p for p in out["profiles"] if p["model"] == "deepseek-flash")
        out = config.switch(flash["id"])
        self.assertEqual(out["model"], "deepseek-flash")
        self.assertTrue(out["supports_vision"])
        self.assertEqual(config.load()["api_key"], "sk-a")
        self.assertNotIn("sk-a", json.dumps(out))

    def test_换服务商各用各的密钥(self):
        self.save()
        self.save(base_url="https://api.other.com/v1", model="other-vl", api_key="sk-b")
        flash = next(p for p in config.public()["profiles"] if p["model"] == "deepseek-flash")
        config.switch(flash["id"])
        self.assertEqual((config.load()["base_url"], config.load()["api_key"]), ("https://api.deepseek.com", "sk-a"))

    def test_正在用的不能删_别的能删(self):
        self.save()
        out = self.save(model="deepseek-v4-pro")
        active = next(p for p in out["profiles"] if p["active"])
        other = next(p for p in out["profiles"] if not p["active"])
        with self.assertRaises(ValueError):
            config.forget_profile(active["id"])
        self.assertEqual(len(config.forget_profile(other["id"])["profiles"]), 1)

    def test_老配置没有清单_当前这套算一个(self):
        config.CONFIG_FILE.write_text(json.dumps({"model": "deepseek-flash", "api_key": "k"}), "utf-8")
        profiles = config.public()["profiles"]
        self.assertEqual(len(profiles), 1)
        self.assertTrue(profiles[0]["active"])


if __name__ == "__main__":
    unittest.main()
