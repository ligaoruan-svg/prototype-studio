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
            self.assertEqual(text.count('const ListPage='), 1, shell)
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
out.names = Store.names(); out.flow = Object.keys(Store.flow('工单'));
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
        self.assertEqual((out['names'], out['flow']), (['工单'], ['派单', '完工']))   # 验收要读：有哪些数据、流转里有哪些动作


if __name__ == '__main__':
    unittest.main()


class 按梳理验收(unittest.TestCase):
    def test_副本里能跑验收_交给AI的话里有验收要的写法(self):
        from backend.bridge import build_bridge
        from backend.architecture import brief
        from backend.arch_spec import normalize
        bridge = build_bridge('p', 'x')
        self.assertIn("m.type==='PA_ACCEPT'", bridge)
        self.assertIn('Store.can(n,row.id,c.action)', bridge)                 # 状态变了按钮还在也算没过
        text = brief({'name': 't', 'nodes': [], 'spec': normalize({'status': 'confirmed', 'objects': [{'name': '工单'}]})})
        self.assertIn('状态和动作的名字跟梳理一字不差', text)


try:
    from playwright.sync_api import sync_playwright
except ImportError:   # 安装包和用户电脑上一般没有，跳过
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, '没装 playwright')
class 列表页模板(unittest.TestCase):
    """写配置就出一整页：页签带数、必填拦下、流转改 Store、按钮跟着消失、新增、详情里有流转记录"""
    def test_一页配置跑通(self):
        import tempfile
        old = STYLE.replace(STORE_JS.strip(), '').replace('const ListPage=', 'const 旧模板=')
        page = shell_add(old, nav="{key:'w',label:'工单',items:[{key:'orders',label:'工单管理'}]}",
                         pages="""orders(){return ListPage('orders',{title:'工单管理',data:'工单',tabs:['待派单','处理中'],
  columns:[{key:'no',label:'编号'},{key:'status',label:'状态',tag:true}],
  actions:[{label:'查看',detail:true},{label:'派单',flow:'派单',form:[{key:'who',label:'维修工',type:'select',options:['张三'],required:true}]}],
  toolbar:[{label:'新增',add:true,defaults:{status:'待派单'},form:[{key:'no',label:'编号',required:true}]}]})}""",
                         script="Store.define('工单',[{no:'GD-1',status:'待派单'},{no:'GD-2',status:'处理中'}]);Store.flow('工单',{派单:['待派单','处理中']});")
        self.assertEqual(page.count('const ListPage='), 1)          # 老外壳加页面时补上
        with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8') as f:
            f.write(page)
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
            pg.goto(Path(f.name).as_uri() + '#orders'); pg.wait_for_timeout(300)
            self.assertEqual(pg.locator('.lp-tab').all_inner_texts(), ['待派单1', '处理中1'])
            pg.click('.lp-ops button:has-text("派单")'); pg.click('#modalConfirm')
            self.assertIn('请填写维修工', pg.inner_text('#toastHost'))           # 必填拦下
            pg.select_option('#activeModal select', '张三'); pg.click('#modalConfirm'); pg.wait_for_timeout(100)
            self.assertEqual(pg.evaluate("Store.all('工单').map(r=>r.status+r.who)"), ['处理中张三', '处理中undefined'])
            self.assertEqual(pg.locator('.lp-ops button:has-text("派单")').count(), 0)   # 状态变了按钮跟着没
            pg.click('.lp-tab:has-text("处理中")'); pg.locator('.lp-ops button:has-text("查看")').first.click()
            self.assertIn('派单', pg.inner_text('.lp-logs'))                        # 详情里有流转记录
            pg.keyboard.press('Escape'); pg.click('.page-actions button:has-text("新增")')
            pg.fill('#activeModal [data-lpf="no"]', 'GD-3'); pg.click('#modalConfirm'); pg.wait_for_timeout(100)
            self.assertEqual(pg.evaluate("Store.all('工单')[0].no+Store.all('工单')[0].status"), 'GD-3待派单')
            self.assertEqual(errs, [])
            b.close()
