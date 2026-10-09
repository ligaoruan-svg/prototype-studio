"""直接选中就改，和先记下再改，交给 AI 的定位信息要一样完整。

原型里常有好几个同名的「保存」「下一步」。界面上写着「新增用户 › 保存」，
模型却只拿到一个选择器，就可能改到别的弹窗或别的业务页面去。
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, agent   # noqa: E402

CONTEXT = {"in_modal": "新增用户", "in_subpage": "用户详情", "modal_trail": "用户管理 › 新增用户", "view_route": "#users"}


class Stop(Exception):
    pass


class 定位上下文(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = storage.DATA_ROOT
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project("定位")["id"]
        (storage.project_dir(self.pid) / "source" / "index.html").write_text(
            "<html><head></head><body><div id='modal'><button>保存</button></div></body></html>", encoding="utf-8")
        self.page = storage.add_page(self.pid, "index.html")["id"]
        self.sent = None
        def fake_chat(api_key, model, messages, tools, **kw):
            self.sent = messages
            raise Stop()
        self.old_chat, agent.chat = agent.chat, fake_chat

    def tearDown(self):
        agent.chat = self.old_chat
        storage.DATA_ROOT = self.old
        self.tmp.cleanup()

    def kickoff(self, **kw):
        with self.assertRaises(Stop):
            agent.run_agent(self.pid, self.page, "把保存改成确认新增", "k", "m", intent="edit", **kw)
        return next(m["content"] for m in self.sent if m["role"] == "user")

    def test_直接选中带上所在页面和弹窗(self):
        text = self.kickoff(selection={"selector": "#modal > button", "text": "保存", "tag": "button", **CONTEXT})
        for key, value in CONTEXT.items():
            self.assertIn(f"{key}={value!r}", text.split("定位目标：")[1])

    def test_多选的每个元素都带上下文(self):
        targets = [{"selector": "#modal > button", "text": "保存", "tag": "button"}, {"selector": "#modal", "text": "", "tag": "div"}]
        text = self.kickoff(selection={"selector": "#modal", "targets": targets, **CONTEXT})
        located = text.split("定位目标：")[1].split("页面骨架")[0]
        self.assertEqual(located.count("in_modal='新增用户'"), 2)

    def test_先记下的意见同样保留(self):
        storage.add_annotation(self.pid, self.page, {"selector": "#modal > button", "note": "改名", **CONTEXT})
        text = self.kickoff()
        located = text.split("定位目标：")[1]
        self.assertIn("view_route='#users'", located)


if __name__ == "__main__":
    unittest.main()
