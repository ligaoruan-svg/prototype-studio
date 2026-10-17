"""原型自动检查：打开一页 HTML，把每个菜单页的按钮挨个点一遍，记下报错、没反应的按钮、弹窗开关、增删改和筛选是否真的生效，再截两种宽度的图。

用法：python3 check.py <page.html> <输出目录>
"""
import asyncio, json, re, sys
from pathlib import Path
from playwright.async_api import async_playwright

DIALOG = '[role=dialog], .modal, .drawer-panel, dialog[open]'
PLACEHOLDER = re.compile(r'示例\d|测试数据|xxx|XXX|lorem|Lorem|占位|TODO|待补充')

JS_STATE = r'''() => {
  const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && +cs.opacity > 0.05 };
  const dialogs = [...document.querySelectorAll('%s')].filter(vis);
  // 有分页时看「共 N 条」，没有就数表格里看得见的行
  const visRows = [...document.querySelectorAll('table tbody tr')].filter(el => vis(el) && !el.closest('%s')).length;
  const all = [...document.body.innerText.matchAll(/共\s*(\d+)\s*(条|项|个|台)/g)]; const m = all.length ? all[all.length - 1][1] : null;   // 分页条一般在最后
  const rows = m ? +m : visRows;
  const toast = [...document.querySelectorAll('.toast, [role=status], [class*=toast]')].filter(el => vis(el) && el.textContent.trim()).map(el => el.textContent.trim()).join(' | ');
  return { dialogs: dialogs.length, dialogText: dialogs.map(d => d.innerText.slice(0, 80)).join(' | '), rows, toast, hash: location.hash, html: document.body.innerHTML.length, sig: document.body.innerText.length + ':' + document.querySelectorAll('*').length };
}''' % (DIALOG, DIALOG)

JS_TARGETS = r'''() => {
  const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' };
  const inDialog = el => !!el.closest('%s');
  const nav = el => !!el.closest('nav, .sidebar, aside');
  const els = [...document.querySelectorAll('button, a[href], [onclick], [data-act], .lnk, [role=button], [role=tab]')]
    .filter(el => vis(el) && !inDialog(el) && !nav(el) && !el.disabled);
  return els.map((el, i) => { el.dataset.chk = 'c' + i; return { id: 'c' + i, text: (el.innerText || el.getAttribute('aria-label') || el.title || '').trim().slice(0, 30), tag: el.tagName.toLowerCase() } });
}''' % DIALOG


async def state(pg):
    return await pg.evaluate(JS_STATE)


async def close_dialog(pg):
    for _ in range(3):
        s = await state(pg)
        if not s['dialogs']:
            return True
        await pg.keyboard.press('Escape'); await pg.wait_for_timeout(200)
        if not (await state(pg))['dialogs']:
            return True
        btn = pg.locator(f'{DIALOG} >> button').filter(has_text=re.compile('取消|关闭|知道了|返回'))
        if await btn.count():
            await btn.first.click(timeout=1000); await pg.wait_for_timeout(200); continue
        x = pg.locator(f'{DIALOG} >> [aria-label=关闭], {DIALOG} >> .icon-btn')
        if await x.count():
            await x.first.click(timeout=1000); await pg.wait_for_timeout(200)
    return not (await state(pg))['dialogs']


async def fill_dialog(pg):
    """把弹窗里的空输入框填上像样的值，下拉选第一个非空项。"""
    return await pg.evaluate(r'''() => {
      const d = [...document.querySelectorAll('%s')].pop(); if (!d) return 0; let n = 0;
      d.querySelectorAll('input, textarea, select').forEach((el, i) => {
        if (el.disabled || el.readOnly) return;
        if (el.tagName === 'SELECT') { const o = [...el.options].find(o => o.value && !/请选择|全部/.test(o.text)); if (o && !el.value) { el.value = o.value; n++ } }
        else if (el.type === 'checkbox' || el.type === 'radio') { }
        else if (!el.value) { el.value = el.type === 'number' ? '12' : el.type === 'date' ? '2026-10-20' : el.type === 'datetime-local' ? '2026-10-20T09:00' : el.type === 'time' ? '09:00' : '自动检查' + (i + 1); n++ }
        el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }));
      }); return n }''' % DIALOG)


async def confirm_dialog(pg):
    btn = pg.locator(f'{DIALOG} >> button').filter(has_text=re.compile('确定|确认|保存|提交|删除|新增|创建|完成'))
    if await btn.count():
        await btn.last.click(timeout=1500); await pg.wait_for_timeout(500); return True
    return False


async def routes(pg):
    return await pg.evaluate(r'''() => [...new Set([...document.querySelectorAll('nav a[href^="#"], .sidebar a[href^="#"], aside a[href^="#"]')].map(a => a.getAttribute('href')).filter(h => h.length > 1))]''')


async def check_route(pg, route, out, report, errors):
    if route:
        await pg.evaluate(f'location.hash = {json.dumps(route)}'); await pg.wait_for_timeout(500)
    base = await state(pg)
    name = route or '(首页)'
    r = {'route': name, 'rows': base['rows'], 'clicked': 0, 'dead': [], 'dialogs_ok': 0, 'dialogs_stuck': [], 'crud': {}, 'filter': None}
    text = await pg.evaluate('document.body.innerText')
    r['placeholder_words'] = sorted(set(PLACEHOLDER.findall(text)))
    seen = set()
    total = len(await pg.evaluate(JS_TARGETS))
    for idx in range(min(total, 60)):
        if route and (await pg.evaluate('location.hash')) != route:
            await pg.evaluate(f'location.hash = {json.dumps(route)}'); await pg.wait_for_timeout(400)
        # 每次都重新找一遍：点完可能整页重画，旧的标记就没了
        targets = await pg.evaluate(JS_TARGETS)
        if idx >= len(targets):
            break
        t = targets[idx]
        key = t['text'] or t['id']
        # 表格里同一种行操作只点一次，不然几十次一样的
        if key in seen and re.search('详情|编辑|删除|查看|^\\d+$', key):
            continue
        seen.add(key)
        loc = pg.locator(f'[data-chk="{t["id"]}"]')
        if not await loc.count():
            continue
        before = await state(pg)
        n_err = len(errors)
        try:
            await loc.first.click(timeout=1500)
        except Exception:
            continue
        await pg.wait_for_timeout(450)
        after = await state(pg)
        r['clicked'] += 1
        changed = after['sig'] != before['sig'] or after['hash'] != before['hash'] or after['dialogs'] != before['dialogs'] or after['toast'] != before['toast']
        if len(errors) > n_err:
            r.setdefault('click_errors', []).append(f'{key}: {errors[-1][:120]}')
        if not changed:
            r['dead'].append(key)
        if after['dialogs'] > before['dialogs']:
            label = key
            # 增删改：新增/编辑填表确认，删除点确认，看行数或提示
            if re.match(r'\W*(新增|添加|新建|创建|分配|登记|录入)', label) and 'add' not in r['crud']:
                await fill_dialog(pg); await confirm_dialog(pg); s2 = await state(pg)
                r['crud']['add'] = {'rows_before': before['rows'], 'rows_after': s2['rows'], 'toast': s2['toast'], 'closed': not s2['dialogs'],
                                    'ok': (s2['rows'] > before['rows'] or bool(s2['toast'])) and not s2['dialogs']}
            elif re.search('删除|移除', label) and 'delete' not in r['crud']:
                await confirm_dialog(pg); s2 = await state(pg)
                r['crud']['delete'] = {'rows_before': before['rows'], 'rows_after': s2['rows'], 'toast': s2['toast'], 'ok': s2['rows'] < before['rows'] and not s2['dialogs']}
            elif re.match(r'\W*(编辑|修改|调整)', label) and 'edit' not in r['crud']:
                filled = await pg.evaluate(r'''() => { const d=[...document.querySelectorAll('%s')].pop(); return d ? [...d.querySelectorAll('input,select,textarea')].filter(e=>e.value).length : 0 }''' % DIALOG)
                await fill_dialog(pg); await confirm_dialog(pg); s2 = await state(pg)
                r['crud']['edit'] = {'prefilled_fields': filled, 'toast': s2['toast'], 'ok': filled > 0 and not s2['dialogs']}
            if await close_dialog(pg):
                r['dialogs_ok'] += 1
            else:
                r['dialogs_stuck'].append(label)
            await pg.screenshot(path=str(out / f'dialog_{len(report)}_{r["dialogs_ok"]}.png')) if False else None
    # 筛选：挨个下拉试一遍（选最后一项再点查询），行数变了就算筛选生效
    n_sel = await pg.locator('select:visible').count()
    for k in range(min(n_sel, 4)):
        sel = pg.locator('select:visible').nth(k)
        before = (await state(pg))['rows']
        opts = await sel.evaluate('s => [...s.options].map(o => o.value || o.text)')
        if len(opts) < 2:
            continue
        await sel.select_option(index=len(opts) - 1)
        q = pg.locator('button:visible').filter(has_text=re.compile('查询|搜索|筛选'))
        if await q.count():
            await q.first.click(timeout=1500)
        await pg.wait_for_timeout(400)
        after = (await state(pg))['rows']
        r['filter'] = {'select_index': k, 'rows_before': before, 'rows_after': after, 'ok': after != before}
        if after != before:
            break
    report.append(r)


async def main(path, outdir):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    html = Path(path).resolve()
    async with async_playwright() as p:
        b = await p.chromium.launch()
        summary = {'file': str(html), 'widths': {}}
        for width in (1440, 1280):
            pg = await b.new_page(viewport={'width': width, 'height': 900})
            errors = []
            pg.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)[:200]))
            pg.on('console', lambda m: m.type == 'error' and errors.append('console: ' + m.text[:200]))
            pg.on('dialog', lambda d: asyncio.ensure_future(d.dismiss()))
            await pg.goto(html.as_uri()); await pg.wait_for_timeout(800)
            rs = await routes(pg) or ['']
            w = {'load_errors': list(errors), 'routes': rs, 'overflow': [], 'pages': []}
            for i, route in enumerate(rs):
                if route:
                    await pg.evaluate(f'location.hash = {json.dumps(route)}'); await pg.wait_for_timeout(500)
                over = await pg.evaluate(r'''() => { const W = document.documentElement.clientWidth; const bad = [];
                  if (document.documentElement.scrollWidth > W + 2) bad.push('页面横向滚动 ' + document.documentElement.scrollWidth + '>' + W);
                  document.querySelectorAll('body *').forEach(el => { const r = el.getBoundingClientRect(); if (r.width && r.right > W + 2 && !el.closest('.tw, [style*=overflow], table')) bad.push(el.tagName.toLowerCase() + '.' + (el.className || '').toString().split(' ')[0] + ' 右边超出 ' + Math.round(r.right - W) + 'px') });
                  return [...new Set(bad)].slice(0, 6) }''')
                if over:
                    w['overflow'].append({'route': route, 'issues': over})
                await pg.screenshot(path=str(out / f'w{width}_{i}.png'), full_page=True)
                if width == 1440:
                    await check_route(pg, route, out, w['pages'], errors)
            w['all_errors'] = errors
            summary['widths'][width] = w
            await pg.close()
        await b.close()
    (out / 'report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    w = summary['widths'][1440]
    print('页面', len(w['routes']), '个；加载报错', len(w['load_errors']), '；运行中报错', len(w['all_errors']))
    for pgr in w['pages']:
        print(f"- {pgr['route']}: 表格 {pgr['rows']} 行，点了 {pgr['clicked']} 个，没反应 {len(pgr['dead'])} {pgr['dead'][:6]}，弹窗关不掉 {pgr['dialogs_stuck']}，"
              f"增删改 {json.dumps({k: v['ok'] for k, v in pgr['crud'].items()}, ensure_ascii=False)}，筛选 {pgr['filter'] and pgr['filter']['ok']}，占位词 {pgr['placeholder_words']}")
    for width, ww in summary['widths'].items():
        if ww['overflow']:
            print(f'{width} 溢出：', ww['overflow'])
    if w['all_errors']:
        print('报错：', w['all_errors'][:5])

if __name__ == '__main__':
    asyncio.run(main(sys.argv[1], sys.argv[2]))
