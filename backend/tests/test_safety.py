"""本机服务的安全关：别的网站借 DNS 重绑定冒充本机、压缩包路径穿越、GBK 网页乱码。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.safety import host_name, to_utf8, zip_member_ok   # noqa: E402


class 安全关(unittest.TestCase):
    def test_只认本机地址(self):
        local = {"127.0.0.1", "localhost", "::1", "testserver"}
        for ok in ("127.0.0.1:5173", "localhost:5173", "[::1]:5173", "LOCALHOST"):
            self.assertIn(host_name(ok), local, ok)
        for bad in ("evil.com:5173", "127.0.0.1.evil.com", "evil.com", ""):
            self.assertNotIn(host_name(bad), local, bad)

    def test_压缩包条目(self):
        self.assertTrue(zip_member_ok("pages/a.html"))
        for bad in ("../x.html", "..\\..\\x.html", "a\\b.html", "C:/x.html", "/etc/x", "__MACOSX/._a.html", ".git/config"):
            self.assertFalse(zip_member_ok(bad), bad)

    def test_GBK网页转成UTF8(self):
        raw = '<html><head><meta charset="gbk"></head><body>碳配额</body></html>'.encode("gbk")
        out = to_utf8(raw).decode("utf-8")
        self.assertIn("碳配额", out)
        self.assertIn('charset="utf-8"', out)
        same = "<p>已经是 UTF-8</p>".encode("utf-8")
        self.assertIs(to_utf8(same), same)


if __name__ == "__main__":
    unittest.main()
