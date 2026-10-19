"""给每套内置风格截一张预览图（prompts/styles/<名字>/preview.png），选风格的卡片上用。

外壳填一页同样的示例内容（模拟 AI 的 shell_add）再截图，几套放在一起比的是「样子」而不是内容。
改了风格（scripts/生成内置风格.py）之后跑一遍：python3 scripts/生成风格预览图.py
要装 playwright 和 Chromium，只在开发时用，软件运行时不需要。
"""
import io
import re
import sys
import tempfile
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
W, H = 480, 300   # 卡片上显示约 240×150，按两倍存，高分屏也清楚
HOME_NAV = "{key:'biz',label:'业务模块',items:[{key:'home',label:'首页'}]}"
HOME_PAGE = "home(){return pageShell('首页','',`${Card({title:'内容',body:'在这里写这一页的内容'})}`)}"


def shell_add(source, nav="", pages="", bind="", script=""):
    nav_at, pages_at, bind_at = "const NAV=[/*PA:NAV*/", "const Pages={/*PA:PAGES*/", "function bindPage(page){/*PA:BIND*/"
    assert all(m in source for m in (nav_at, pages_at, bind_at))
    clean = lambda t: str(t or "").strip().rstrip(",")
    if nav:
        source = source.replace(nav_at + "\n  " + HOME_NAV + "\n", nav_at + "\n", 1)
        source = source.replace(nav_at, nav_at + "\n  " + clean(nav) + ",", 1)
    if pages:
        source = source.replace(pages_at + "\n  " + HOME_PAGE + "\n", pages_at + "\n", 1)
        source = source.replace(pages_at, pages_at + "\n  " + clean(pages) + ",", 1)
    if bind:
        source = source.replace(bind_at, bind_at + "\n  " + bind.strip() + "\n", 1)
    if script:
        at = source.find("// ===== 业务页面：")
        source = source[:at] + script.strip() + "\n" + source[at:]
    return source


ADMIN = dict(
    nav="{key:'trade',label:'经营',items:[{key:'overview',label:'概览'},{key:'orders',label:'订单管理'},{key:'refund',label:'售后与退款'}]},{key:'goods',label:'商品',items:[{key:'list',label:'商品列表'},{key:'stock',label:'库存'}]}",
    script="""const orders=[['SO-20261018-0012','张三','无线降噪耳机 ×1','899.00','warning','待发货'],['SO-20261018-0011','李四','机械键盘 ×1','512.00','info','已发货'],['SO-20261018-0010','王五','保温杯 ×3','237.00','success','已完成'],['SO-20261017-0098','赵六','4K 显示器 ×1','2,399.00','danger','退款中'],['SO-20261017-0097','孙七','帆布包 ×1','129.00','warning','待发货']];""",
    pages="""orders(){return pageShell('订单管理','查看和处理全部订单',`<div class="metric-grid"><div class="metric"><div class="metric-label">今日订单</div><div class="metric-value">1,284</div><div class="metric-foot"><span class="up">+8.2%</span> 较昨日</div></div><div class="metric"><div class="metric-label">今日成交额</div><div class="metric-value">¥ 236,410</div><div class="metric-foot"><span class="up">+5.6%</span> 较昨日</div></div><div class="metric"><div class="metric-label">待发货</div><div class="metric-value">96</div><div class="metric-foot"><span class="down">超时 7 单</span></div></div><div class="metric"><div class="metric-label">退款申请</div><div class="metric-value">12</div><div class="metric-foot">处理中 4 单</div></div></div><section class="card"><div class="card-bd"><div class="filter">${ZeroUI.Field({label:'订单号 / 收货人',placeholder:'输入关键词'})}${ZeroUI.Field({label:'订单状态',type:'select',options:['全部','待发货','已发货']})}<div class="filter-actions">${ZeroUI.Button({label:'查询',kind:'primary',icon:SVG.search})}${ZeroUI.Button({label:'重置',icon:SVG.reset})}</div></div></div><div class="tw"><table class="data-table"><colgroup><col style="width:180px"><col style="width:100px"><col><col style="width:120px"><col style="width:100px"><col style="width:140px"></colgroup><thead><tr><th>订单号</th><th>收货人</th><th>商品</th><th>金额</th><th>状态</th><th>操作</th></tr></thead><tbody>${orders.map(o=>`<tr><td class="t1 code">${o[0]}</td><td>${o[1]}</td><td>${o[2]}</td><td class="num">¥ ${o[3]}</td><td>${ZeroUI.Tag({text:o[5],kind:o[4]})}</td><td class="op-col"><div class="ops"><button class="lnk">详情</button><button class="lnk">发货</button></div></td></tr>`).join('')}</tbody></table></div>${ZeroUI.Pager({total:1284,page:1,pageSize:10})}</section>`,`${ZeroUI.Button({label:'导出'})}${ZeroUI.Button({label:'新建订单',kind:'primary',icon:SVG.plus,id:'newOrder'})}`)}""",
    bind="if(page==='orders'){document.getElementById('newOrder').onclick=e=>ZeroUI.openModal(ZeroUI.Modal({title:'新建订单',body:`<div class=\"form-grid\">${ZeroUI.Field({label:'收货人',required:true})}${ZeroUI.Field({label:'手机号'})}${ZeroUI.Field({label:'备注',type:'textarea',full:true})}</div>`}),c=>{c();ZeroUI.Toast('已创建')},e.currentTarget)}",
)
SCREEN = dict(
    nav="{key:'board',label:'看板',items:[{key:'live',label:'订单实时'},{key:'goods',label:'商品分析'},{key:'users',label:'用户画像'}]}",
    pages="""live(){return pageShell('订单实时看板','今天 00:00 起的订单与成交',`<div class="metric-grid"><div class="metric"><div class="metric-label">今日订单</div><div class="metric-value">1,284</div><div class="metric-foot"><span class="up">较昨日 +8.2%</span></div></div><div class="metric"><div class="metric-label">今日成交额</div><div class="metric-value">¥ 236,410</div><div class="metric-foot"><span class="up">较昨日 +5.6%</span></div></div><div class="metric"><div class="metric-label">待发货</div><div class="metric-value">96</div><div class="metric-foot"><span class="down">超时 7 单</span></div></div><div class="metric"><div class="metric-label">客单价</div><div class="metric-value">¥ 184</div><div class="metric-foot">近 7 日均值 ¥ 176</div></div></div><div class="grid three">${Card({title:'近 7 日成交额',body:ZeroUI.Bars({items:[{label:'10-12',value:18.2},{label:'10-13',value:19.6},{label:'10-14',value:17.4},{label:'10-15',value:21.0},{label:'10-16',value:22.8},{label:'10-17',value:20.1},{label:'今天',value:23.6}],unit:'万',current:6})})}${Card({title:'品类占比',body:ZeroUI.Meter({items:[{label:'数码电器',value:42},{label:'家居日用',value:27},{label:'服饰箱包',value:18},{label:'食品饮料',value:13}]})})}${Card({title:'最新订单',body:`<div class="list">${[['张三','无线降噪耳机','¥ 899'],['李四','机械键盘','¥ 512'],['王五','保温杯 ×3','¥ 237'],['赵六','4K 显示器','¥ 2,399']].map(x=>ZeroUI.ListItem({title:x[0]+'　'+x[1],extra:`<b style="color:var(--primary)">${x[2]}</b>`})).join('')}</div>`})}</div>`)}""",
)
MIDDLE = dict(
    nav="{key:'work',label:'工作台',items:[{key:'desk',label:'我的工作台'}]},{key:'order',label:'订单中心',items:[{key:'orders',label:'订单列表'},{key:'refund',label:'售后审核'},{key:'invoice',label:'发票管理'}]},{key:'goods',label:'商品中心',items:[{key:'list',label:'商品列表'}]},{key:'stock',label:'库存',items:[{key:'s1',label:'库存总览'}]},{key:'settle',label:'结算',items:[{key:'x1',label:'对账单'}]}",
    script=ADMIN['script'],
    pages=ADMIN['pages'],
)
MOBILE = dict(
    nav="{key:'app',label:'App',items:[{key:'index',label:'首页',icon:'home'},{key:'cat',label:'分类',icon:'grid'},{key:'orders',label:'订单',icon:'list'},{key:'me',label:'我的',icon:'user'}]}",
    pages="""orders(){return pageShell('我的订单','',`<div class="grid">${[['SO-20261018-0012','无线降噪耳机','黑色 · ×1','¥ 899','warning','待发货'],['SO-20261018-0011','机械键盘','茶轴 · ×1','¥ 512','info','运输中'],['SO-20261018-0010','保温杯','米白 · ×3','¥ 237','success','已完成']].map(o=>`<section class="card"><div class="card-hd"><span class="code" style="color:var(--text-3);font-size:12px">${o[0]}</span>${ZeroUI.Tag({text:o[5],kind:o[4]})}</div><div class="card-bd"><div class="list-item" style="padding:0;border:0"><span style="width:56px;height:56px;border-radius:10px;background:var(--primary-weak);flex:none"></span><span class="li-main"><span class="li-title">${o[1]}</span><span class="li-desc">${o[2]}</span></span><b>${o[3]}</b></div><div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px">${ZeroUI.Button({label:'联系客服'})}${ZeroUI.Button({label:'确认收货',kind:'primary'})}</div></div></section>`).join('')}</div>`)}""",
)


def capture(browser, html: str, size: tuple[int, int], hash_: str) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "page.html"
        f.write_text(html, "utf-8")
        page = browser.new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f.as_uri() + hash_)
        page.wait_for_timeout(300)
        shot = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
        page.close()
    if errors:
        raise SystemExit(f"示例页面报错：{errors}")
    return shot


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for folder in sorted((REPO / "prompts/styles").iterdir()):
            text = (folder / "SKILL.md").read_text("utf-8")
            layout = re.search(r"^layout: (\w+)", text, re.M).group(1)
            shell = (folder / "assets/页面外壳.html").read_text("utf-8")
            demo = {"sidebar": ADMIN, "topbar": MIDDLE, "screen": SCREEN, "mobile": MOBILE}[layout]
            html = shell_add(shell, **demo)
            if layout == "mobile":
                # 手机：一屏截下来，放在这套风格的外圈底色上居中
                phone = capture(browser, html, (390, 844), "#orders")
                outer = re.search(r"--outer-bg:(#[0-9a-fA-F]{6})", shell)
                canvas = Image.new("RGB", (W * 2, H * 2), outer.group(1) if outer else "#e8e8ec")
                phone = phone.resize((int(390 * (H * 2 - 40) / 844), H * 2 - 40), Image.LANCZOS)
                canvas.paste(phone, ((W * 2 - phone.width) // 2, 40))
                img = canvas
            else:
                img = capture(browser, html, (1440, 900), "" if layout == "screen" else "#orders")
            img = img.resize((W, H), Image.LANCZOS)
            out = folder / "preview.png"
            img.quantize(colors=128, method=Image.Quantize.MEDIANCUT).save(out, optimize=True)
            print(f"{folder.name}: {out.stat().st_size // 1024} KB")
        browser.close()


if __name__ == "__main__":
    main()
