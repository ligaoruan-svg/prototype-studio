"""发消息时带的截图和点选位置跟着消息存下来：刷新、做完、重开项目都还在；消息被挤出最近 40 条时截图一起清掉。"""
import base64
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import storage   # noqa: E402

PNG = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'x' * 3000).decode()


class 对话里的截图(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = storage.DATA_ROOT
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('t')['id']

    def tearDown(self):
        storage.DATA_ROOT = self.old
        self.tmp.cleanup()

    def test_截图存成文件_消息里记着(self):
        image_id = storage.save_chat_image(self.pid, PNG)
        self.assertRegex(image_id, r'^img_[a-f0-9]{10}$')
        storage.append_chat(self.pid, 'user', '照这个改', {'image': image_id, 'target': '「提交」按钮'})
        msg = storage.load_meta(self.pid)['chat'][-1]
        self.assertEqual(msg['image'], image_id)
        self.assertEqual(msg['target'], '「提交」按钮')
        path = storage.chat_image_path(self.pid, image_id)
        self.assertTrue(path.is_file() and path.suffix == '.png')
        self.assertNotIn('base64', storage.meta_path(self.pid).read_text('utf-8'))   # 图片不塞进项目文件

    def test_不是图片或太大就不存(self):
        self.assertEqual(storage.save_chat_image(self.pid, 'data:text/html;base64,PGI+'), '')
        self.assertEqual(storage.save_chat_image(self.pid, 'data:image/png;base64,@@@'), '')
        big = 'data:image/png;base64,' + base64.b64encode(b'x' * (storage.CHAT_IMAGE_MAX + 1)).decode()
        self.assertEqual(storage.save_chat_image(self.pid, big), '')
        with self.assertRaises(ValueError):
            storage.chat_image_path(self.pid, '../config')

    def test_消息被挤掉_截图一起清掉(self):
        first = storage.save_chat_image(self.pid, PNG)
        storage.append_chat(self.pid, 'user', '第一条', {'image': first})
        for i in range(40):
            storage.append_chat(self.pid, 'assistant', f'回复 {i}')
        last = storage.save_chat_image(self.pid, PNG)
        storage.append_chat(self.pid, 'user', '最新', {'image': last})
        self.assertIsNone(storage.chat_image_path(self.pid, first))
        self.assertIsNotNone(storage.chat_image_path(self.pid, last))


if __name__ == '__main__':
    unittest.main()
