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

    def test_清单外的旧展开结果会清掉(self):
        import os, time
        storage.save_expand_entry(self.pid, self.page, '#a', 's7:x', {'nodes': []})
        storage.save_expand_entry(self.pid, self.page, '#gone', 's7:x', {'nodes': []})
        storage.save_expand_entry(self.pid, self.page, '#fresh', 's7:x', {'nodes': []})
        root = storage.project_dir(self.pid) / 'expand' / self.page
        old = root / storage._route_file('#gone')
        os.utime(old, (time.time() - 2 * 86400,) * 2)
        storage.save_expand_routes(self.pid, self.page, [{'hash': '#a', 'title': 'A'}], 3)
        self.assertFalse(old.exists(), '菜单里没有了、一天没碰的删掉')
        self.assertTrue((root / storage._route_file('#a')).exists())
        self.assertTrue((root / storage._route_file('#fresh')).exists(), '刚写的先留着')

    def test_删掉的页面不再写展开结果(self):
        storage.trash_item(self.pid, self.page)
        with self.assertRaises(KeyError):
            storage.save_expand_entry(self.pid, self.page, '#a', 's7:x', {'nodes': []})


class 页面链接(unittest.TestCase):
    META = {'pages': [{'id': 'o', 'path': 'orders/index.html'}, {'id': 'u', 'path': 'users/index.html'},
                      {'id': 'l', 'path': 'users/list.html'}, {'id': 'x', 'path': 'old.html', 'deleted_at': '1'}]}

    def test_同名页面按完整路径找(self):
        self.assertEqual(storage.resolve_link(self.META, 'users/index.html'), 'u')
        self.assertEqual(storage.resolve_link(self.META, '../orders/index.html', 'u'), 'o')
        self.assertEqual(storage.resolve_link(self.META, 'index.html', 'o'), 'o', '相对当前页')
        self.assertIsNone(storage.resolve_link(self.META, 'other/index.html'), '同名的有两个，猜不准就不跳')
        self.assertEqual(storage.resolve_link(self.META, 'list.html#top'), 'l', '唯一同名可以按文件名')
        self.assertIsNone(storage.resolve_link(self.META, 'old.html'), '回收站里的不算')


if __name__ == '__main__':
    unittest.main()
