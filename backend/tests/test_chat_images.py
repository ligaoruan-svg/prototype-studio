"""发消息时带的截图和点选位置跟着消息存下来：刷新、做完、重开项目都还在；对话框里留最近 200 条，截图全部留着。"""
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

    def test_留最近200条_截图全部留着(self):
        first = storage.save_chat_image(self.pid, PNG)
        storage.append_chat(self.pid, 'user', '第一条', {'image': first})
        for i in range(210):
            storage.append_chat(self.pid, 'assistant', f'回复 {i}')
        chat = storage.load_meta(self.pid)['chat']
        self.assertEqual(len(chat), 200)
        self.assertEqual(chat[-1]['content'], '回复 209')
        self.assertIsNotNone(storage.chat_image_path(self.pid, first))   # 消息挤出对话框了，截图还在
        log = (storage.project_dir(self.pid) / 'chat_log.jsonl').read_text('utf-8')
        self.assertIn(first, log)                                          # 全部历史里也记着


if __name__ == '__main__':
    unittest.main()
