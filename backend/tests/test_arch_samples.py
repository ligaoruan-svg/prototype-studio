"""架构生成的回归样例：五个行业（物业报修、费用报销、招商租赁、设备巡检、电商售后）的梳理 + 页面清单，放在 arch_samples/。
改了页面清单展开（arch_plan）、自动检查（arch_ops）、程序生成页面和数据（arch_gen / arch_demo）、列表页模板（shell_list），
都要五个一起过：展开后自动检查 0 问题，程序生成的每一页打得开、有数据、不报错。规则要通用，不能只对一个行业。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend import arch_gen, arch_ops, arch_plan, arch_spec, architecture   # noqa: E402
from backend.patcher import shell_add   # noqa: E402

SAMPLES = sorted((Path(__file__).parent / "arch_samples").glob("*.json"))
SHELL = (ROOT / "prompts/styles/业务中台/assets/页面外壳.html").read_text(encoding="utf-8")


def build(path: Path) -> dict:
    """样例 → 照「按这个画架构」展开的整棵树"""
    raw = json.loads(path.read_text("utf-8"))
    spec = arch_spec.normalize(raw["spec"])
    plan, _ = arch_plan.settle(arch_plan.normalize(raw["plan"]), arch_plan.PLAN_HEAD)
    return architecture.normalize({"name": path.stem, "nodes": arch_plan.expand(plan, spec), "spec": spec})


class 五个行业展开(unittest.TestCase):
    def test_样例都在(self):
        self.assertGreaterEqual(len(SAMPLES), 5)

    def test_展开后自动检查没有问题(self):
        for path in SAMPLES:
            with self.subTest(path.stem):
                self.assertEqual(arch_ops.problems(build(path)), [])

    def test_列表类页面都由程序生成(self):
        for path in SAMPLES:
            with self.subTest(path.stem):
                arch = build(path)
                gen = arch_gen.generate(arch)
                kinds = {p["name"]: p["type"] for m in json.loads(path.read_text("utf-8"))["plan"]["modules"] for p in m["pages"]}
                # 看板、统计还留给 AI；管理列表、我的任务、基础配置都该程序直接出
                self.assertEqual(sorted(gen["left"]), sorted(n for n, k in kinds.items() if k in ("dashboard", "report")))


try:
    from playwright.sync_api import sync_playwright
except ImportError:   # 安装包和用户电脑上一般没有，跳过
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, '没装 playwright')
class 五个行业的原型跑起来(unittest.TestCase):
    """程序生成的页面放进外壳：每页打开有数据、没报错；物业报修走一遍「完工填报」带材料明细"""
    def open(self, p, path: Path):
        gen = arch_gen.generate(build(path))
        html = shell_add(SHELL, nav=gen["nav"], pages=gen["pages"], script=gen["script"])
        f = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
        f.write(html)
        f.close()
        page = p.chromium.launch().new_page()
        errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        page.goto(Path(f.name).as_uri())
        return gen, page, errs

    def test_每页打得开_有数据(self):
        with sync_playwright() as p:
            for path in SAMPLES:
                gen, page, errs = self.open(p, path)
                for name in gen["made"]:
                    with self.subTest(f"{path.stem} / {name}"):
                        page.evaluate(f"location.hash='#{gen['keys'][name]}'")
                        page.wait_for_timeout(80)
                        rows = page.locator("#content .data-table tbody tr")
                        self.assertGreater(rows.count(), 0)
                        self.assertNotIn("暂无数据", rows.first.inner_text())
                        self.assertNotIn("NaN", page.inner_text("#content"))
                        page.locator("#content .lp-ops button:has-text('查看')").first.click()
                        drawer = page.inner_text("#activeDrawer")
                        self.assertNotIn("NaN", drawer)
                        # 详情里的明细、历次记录（材料明细、跟进记录）：演示数据指回得上，第一条就有
                        for sub in page.locator("#activeDrawer .lp-h + .tw").all():
                            self.assertNotIn("暂无", sub.inner_text(), drawer)
                        page.keyboard.press("Escape")
                self.assertEqual(errs, [], path.stem)

    def test_完工填报带材料明细(self):
        with sync_playwright() as p:
            gen, page, errs = self.open(p, Path(__file__).parent / "arch_samples/物业报修.json")
            page.evaluate(f"location.hash='#{gen['keys']['我的任务']}'")
            page.wait_for_timeout(80)
            before = page.evaluate("Store.all('工单材料明细').length")
            page.locator("#content .lp-ops button:has-text('完工填报')").first.click()
            page.fill("#activeModal textarea, #activeModal [data-lpf='处理说明']", "更换水龙头阀芯")
            box = page.locator("#activeModal .lp-rows")
            box.locator("select").first.select_option(index=1)
            page.click("#modalConfirm")
            self.assertIn("工单材料明细第1行的数量", page.inner_text("#toastHost"))      # 明细逐行查必填
            box.locator("[data-lpr='数量']").first.fill("2")
            box.locator("[data-lpr='是否收费']").first.select_option(index=1)
            page.click("#modalConfirm")
            page.wait_for_timeout(100)
            self.assertEqual(page.evaluate("Store.all('工单材料明细').length"), before + 1)
            no = page.evaluate("Store.all('工单材料明细')[0]['所属工单']")
            self.assertEqual(page.evaluate(f"Store.all('报修工单').find(r=>r['工单编号']==={json.dumps(no)}).status"), "待确认")
            # 详情里看得到刚填的材料
            page.evaluate(f"location.hash='#{gen['keys']['工单管理']}'")
            page.wait_for_timeout(80)
            page.evaluate(f"document.querySelectorAll('#content .lp-tab').forEach(t=>t.textContent==='待确认'&&t.click())")
            page.wait_for_timeout(80)
            row = page.locator("#content .data-table tbody tr", has_text=no)
            row.locator("button:has-text('查看')").click()
            self.assertIn("工单材料明细", page.inner_text("#activeDrawer"))
            self.assertEqual(errs, [])
