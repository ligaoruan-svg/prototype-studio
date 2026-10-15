"""改得多了，project.json 和历史文件不能无限长。"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend import storage, transactions   # noqa: E402


class 存储瘦身(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_root, self.old_keep = storage.DATA_ROOT, storage.KEEP_VERSIONS
        storage.DATA_ROOT = Path(self.tmp.name)
        storage.KEEP_VERSIONS = 5
        self.pid = storage.create_project('t')['id']
        (storage.project_dir(self.pid) / 'source' / 'index.html').write_text('<html><head></head><body><p>a</p></body></html>', encoding='utf-8')
        self.page = storage.add_page(self.pid, 'index.html')['id']

    def tearDown(self):
        storage.DATA_ROOT, storage.KEEP_VERSIONS = self.old_root, self.old_keep
        self.tmp.cleanup()

    def edit(self, k):
        before = storage.read_page(self.pid, self.page)
        after = before.replace('</body>', ''.join(f'<p>{k}-{i} {"x" * 900}</p>\n' for i in range(150)) + '</body>')
        staged = transactions.stage(self.pid, self.page, before, after, f'第 {k} 次', 'agent', message='改好了')
        transactions.commit(staged['pending_id'], [], True)

    def test_历史版本和对话里的改动都有上限(self):
        for k in range(12):
            self.edit(k)
        page = storage.get_page(storage.load_meta(self.pid), self.page)
        self.assertEqual(len(page['versions']), 6, '第一版 + 最近 5 版')
        self.assertEqual(page['versions'][0]['version'], 1)
        files = list((storage.project_dir(self.pid) / 'versions' / self.page).glob('*.html'))
        self.assertEqual(len(files), 6)
        chat = storage.load_meta(self.pid)['chat']
        lines = [sum(len(h['lines']) for h in m['diff']['hunks']) for m in chat if m.get('diff')]
        self.assertTrue(lines and max(lines) <= storage.CHAT_DIFF_LINES)
        self.assertTrue(all(m['diff']['truncated'] for m in chat if m.get('diff')))
        self.assertLess((storage.project_dir(self.pid) / 'project.json').stat().st_size, 400_000)

    def test_掉出撤销栈的改前副本会删(self):
        old = transactions.prune_before_files
        for k in range(3):
            self.edit(k)
        page = storage.get_page(storage.load_meta(self.pid), self.page)
        page['undo_stack'] = page['undo_stack'][-1:]
        transactions.prune_before_files(self.pid, self.page, page)
        left = list((storage.project_dir(self.pid) / 'changes' / self.page).glob('*-before.html'))
        self.assertEqual(len(left), 1)
        self.assertIs(old, transactions.prune_before_files)

    def test_彻底删除页面连改前副本一起删(self):
        self.edit(0)
        storage.trash_item(self.pid, self.page)
        storage.purge_item(self.pid, self.page)
        self.assertFalse((storage.project_dir(self.pid) / 'changes' / self.page).exists())


if __name__ == '__main__':
    unittest.main()
