"""画笔评论的缩略图：存成单独的图片文件，不塞进 project.json；删评论、删页面时一起删。"""
import base64
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import storage   # noqa: E402

JPEG = 'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xff' + b'x' * 2000).decode()


class 评论缩略图(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = storage.DATA_ROOT
        storage.DATA_ROOT = Path(self.tmp.name)
        self.pid = storage.create_project('t')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text('<html><head></head><body></body></html>', encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']

    def tearDown(self):
        storage.DATA_ROOT = self.old
        self.tmp.cleanup()

    def test_存成文件_不进项目文件(self):
        a = storage.add_annotation(self.pid, self.page, {'selector': 'body', 'note': '这块改成卡片', 'shot': JPEG})
        self.assertTrue(a['shot'])
        self.assertTrue(storage.shot_path(self.pid, a['id']).is_file())
        self.assertNotIn('base64', (storage.project_dir(self.pid) / 'project.json').read_text('utf-8'))

    def test_不是图片的不收(self):
        a = storage.add_annotation(self.pid, self.page, {'selector': 'body', 'note': 'x', 'shot': 'data:text/html;base64,PHA+'})
        self.assertNotIn('shot', a)
        with self.assertRaises(ValueError):
            storage.shot_path(self.pid, '../../etc')

    def test_删评论和删页面时一起删(self):
        a = storage.add_annotation(self.pid, self.page, {'selector': 'body', 'note': 'x', 'shot': JPEG})
        storage.delete_annotation(self.pid, a['id'])
        self.assertFalse(storage.shot_path(self.pid, a['id']).exists())
        b = storage.add_annotation(self.pid, self.page, {'selector': 'body', 'note': 'y', 'shot': JPEG})
        storage.trash_item(self.pid, self.page)
        storage.purge_item(self.pid, self.page)
        self.assertFalse(storage.shot_path(self.pid, b['id']).exists())


if __name__ == '__main__':
    unittest.main()
