"""绑定多个模型：可以绑好几家服务商，一点就切；同一家换模型不用再贴密钥；接口返回永远不带密钥。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import config   # noqa: E402

BASE = {"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "api_key": "sk-a", "supports_vision": True,
        "max_tokens": 16000, "stream": True, "context_budget": 200000, "max_rounds": 24}


class 绑定多个模型(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = config.CONFIG_FILE
        config.CONFIG_FILE = Path(self.tmp.name) / "config.json"
        config.save(BASE)

    def tearDown(self):
        config.CONFIG_FILE = self.old
        self.tmp.cleanup()

    def add(self, **kw):
        return config.save_profile({**BASE, "api_key": "", **kw})

    def test_同一家加个模型不用再贴密钥_切过去密钥跟着走(self):
        out = self.add(model="deepseek-v4-pro", supports_vision=False, name="深度思考")
        self.assertEqual([p["model"] for p in out["profiles"]], ["deepseek-flash", "deepseek-v4-pro"])
        pro = next(p for p in out["profiles"] if p["model"] == "deepseek-v4-pro")
        self.assertFalse(pro["active"], "新增不等于马上用")
        self.assertEqual(pro["name"], "深度思考")
        out = config.switch(pro["id"])
        self.assertEqual((out["model"], out["supports_vision"]), ("deepseek-v4-pro", False))
        self.assertEqual(config.load()["api_key"], "sk-a")
        self.assertNotIn("sk-a", json.dumps(out))

    def test_别家必须填自己的密钥_各用各的(self):
        with self.assertRaises(ValueError):
            self.add(base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", model="qwen-vl")
        out = self.add(base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", model="qwen-vl", api_key="sk-b")
        qwen = next(p for p in out["profiles"] if p["model"] == "qwen-vl")
        config.switch(qwen["id"])
        self.assertEqual(config.load()["api_key"], "sk-b")
        flash = next(p for p in config.public()["profiles"] if p["model"] == "deepseek-flash")
        config.switch(flash["id"])
        self.assertEqual(config.load()["api_key"], "sk-a")

    def test_改正在用的那套_顶层跟着变(self):
        active = next(p for p in config.public()["profiles"] if p["active"])
        out = config.save_profile({**BASE, "api_key": "", "max_tokens": 8192}, active["id"])
        self.assertEqual(out["max_tokens"], 8192)
        self.assertEqual(len(out["profiles"]), 1, "改不是新增")

    def test_重复绑定_和删正在用的都拦下(self):
        with self.assertRaises(ValueError):
            self.add()
        out = self.add(model="deepseek-v4-pro")
        active = next(p for p in out["profiles"] if p["active"])
        other = next(p for p in out["profiles"] if not p["active"])
        with self.assertRaises(ValueError):
            config.forget_profile(active["id"])
        self.assertEqual(len(config.forget_profile(other["id"])["profiles"]), 1)

    def test_测试连接用指定那套的密钥(self):
        out = self.add(base_url="https://api.moonshot.cn/v1", model="kimi-x", api_key="sk-k")
        kimi = next(p for p in out["profiles"] if p["model"] == "kimi-x")
        s = config.profile_settings(kimi["id"])
        self.assertEqual((s["base_url"], s["api_key"]), ("https://api.moonshot.cn/v1", "sk-k"))
        self.assertEqual(config.load()["api_key"], "sk-a", "测试别的那套不会改到正在用的")

    def test_老配置没有清单_当前这套算一个(self):
        config.CONFIG_FILE.write_text(json.dumps({"model": "deepseek-flash", "api_key": "k"}), "utf-8")
        profiles = config.public()["profiles"]
        self.assertEqual(len(profiles), 1)
        self.assertTrue(profiles[0]["active"])
        self.assertEqual(profiles[0]["id"], config.public()["profiles"][0]["id"], "没存过 id 的，每次算出来一样")


if __name__ == "__main__":
    unittest.main()
