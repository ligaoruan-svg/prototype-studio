"""页面外壳里的统一数据层 Store：业务数据只放一份，按钮改它，改完当前页自动重画。"""
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.patcher import shell_add, verify_source   # noqa: E402
from backend.shell_store import STORE_JS, ensure   # noqa: E402
from backend.agent_context import shell_api   # noqa: E402

STYLE = (ROOT / 'prompts/styles/业务中台/assets/页面外壳.html').read_text(encoding='utf-8')


class 统一数据层(unittest.TestCase):
    def test_内置风格的外壳都带着(self):
        for shell in (ROOT / 'prompts/styles').glob('*/assets/页面外壳.html'):
            text = shell.read_text(encoding='utf-8')
            self.assertEqual(text.count('const Store='), 1, shell)
            self.assertTrue(verify_source(text)['ok'], shell)

    def test_别的外壳加页面时补上_只补一次(self):
        old = STYLE.replace(STORE_JS.strip(), '')
        self.assertNotIn('const Store=', old)
        out = shell_add(old, script="Store.define('工单',[{status:'待派单'}]);")
        self.assertEqual(out.count('const Store='), 1)
        self.assertLess(out.index('const Store='), out.index("Store.define('工单',[{status:'待派单'}])"))    # 先有 Store 再用
        self.assertEqual(shell_add(out, script='x=1;').count('const Store='), 1)
        self.assertEqual(ensure('<html>不是外壳</html>'), '<html>不是外壳</html>')

    def test_交给AI的外壳说明里有写法(self):
        self.assertTrue(any('Store.flow' in s for s in shell_api(STYLE)['store']))

    @unittest.skipIf(shutil.which('node') is None, '没装 node')
    def test_状态流转和自动重画(self):
        script = STORE_JS + r"""
let renders = 0; const toasts = [];
globalThis.Router = {render: () => renders++}; globalThis.UI = {Toast: m => toasts.push(m)};
globalThis.document = {getElementById: () => ({})};
Store.define('工单', [{status: '待派单'}, {status: '处理中'}]);
Store.define('工单', [{status: '不该覆盖'}]);
Store.flow('工单', {派单: ['待派单', '处理中'], 完工: ['处理中', '已完成']});
const out = {};
out.can = [Store.can('工单', '工单-1', '派单'), Store.can('工单', '工单-2', '派单')];
out.move = Store.move('工单', '工单-1', '派单', {处理人: '张三'});
out.bad = Store.move('工单', '工单-1', '派单');
out.status = Store.get('工单', '工单-1').status;
out.who = Store.get('工单', '工单-1').处理人;
out.logs = Store.get('工单', '工单-1').logs.length;
out.count = Store.count('工单', r => r.status === '处理中');
out.added = Store.add('工单', {status: '待派单'}).id;
out.size = Store.all('工单').length;
setTimeout(() => { out.renders = renders; out.toasts = toasts; console.log(JSON.stringify(out)); }, 20);
"""
        res = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=20)
        out = json.loads(res.stdout.strip())
        self.assertEqual(out['can'], [True, False])
        self.assertTrue(out['move'])
        self.assertFalse(out['bad'])                                   # 已经是处理中：不能再派单
        self.assertEqual((out['status'], out['who'], out['logs']), ('处理中', '张三', 1))
        self.assertEqual(out['count'], 2)
        self.assertEqual((out['added'], out['size']), ('工单-3', 3))     # 编号接着往下排；define 第二次不覆盖
        self.assertEqual(out['renders'], 1)                            # 连着改几处只重画一次
        self.assertIn('现在是「处理中」，不能派单', out['toasts'])


if __name__ == '__main__':
    unittest.main()
