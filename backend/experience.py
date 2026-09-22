"""Presentation metadata shared by streaming, results and version history."""
import bisect
import difflib
import json
import re
from bs4 import BeautifulSoup
from .patcher import locate, PatchError, SourceIndex

REGION_NAMES = {'tokens':'配色与尺寸', 'base':'基础样式', 'components':'公共组件', 'layout':'布局', 'script':'交互逻辑', 'markup-main':'主要内容', 'markup-header':'页头', 'markup-list':'列表区', 'section-main':'主要内容样式', 'section-header':'页头样式', 'manual-styles':'局部样式'}
TAG_NAMES = {'button':'按钮', 'a':'链接', 'input':'输入框', 'textarea':'输入框', 'select':'选择框', 'h1':'标题', 'h2':'标题', 'h3':'标题', 'p':'文字', 'table':'表格', 'th':'表头', 'td':'单元格', 'img':'图片'}


def element_name(target):
    text = str(target.get('text', '')).strip().replace('\n', ' ')[:24]
    kind = TAG_NAMES.get(target.get('tag', ''), '区域')
    return f'「{text}」{kind}' if text else kind


def tool_label(name, args):
    return {
        'inspect_page': '读取页面结构', 'search_source': f'查找「{str(args.get("query", ""))[:24]}」',
        'read_source_slice': '读取相关代码', 'read_region': f'读取{REGION_NAMES.get(args.get("name"), "选定区域")}',
        'apply_operations': f'应用 {len(args.get("operations", []))} 处修改', 'verify_page': '检查修改结果',
        'report_result': '整理修改结果', 'ask_user': '确认你的想法', 'answer_user': '整理分析和建议',
        'update_plan': '整理修改计划', 'read_component': '取用现成组件', 'read_skill': '查阅 skill', 'read_skill_file': '查规范细则', 'search_skill_file': '找现成组件', 'remember': '记住这条约定', 'forget': '忘掉那条约定',
    }.get(name, '处理修改')


def compact_messages(messages, budget=60000):
    def size(content):
        if isinstance(content, str): return len(content)
        return sum(len(x.get('text', '')) for x in content or [] if isinstance(x, dict))
    total = sum(size(m.get('content')) for m in messages)
    tools = [m for m in messages if m.get('role') == 'tool']
    for message in tools[:-3]:
        if total <= budget: break
        content = message.get('content', '')
        if not isinstance(content, str) or len(content) < 250: continue
        try:
            obj = json.loads(content)
            summary = {'context_compacted': True, 'ok': obj.get('ok', True), 'summary': '较早的读取结果已收起；需要原文时重新读取对应区域。'}
            if obj.get('error'): summary['error'] = str(obj['error'])[:200]
        except (ValueError, AttributeError):
            summary = {'context_compacted': True, 'summary':'较早工具结果已收起，需要时重新读取。'}
        message['content'] = json.dumps(summary, ensure_ascii=False)
        total -= len(content) - len(message['content'])
    # A single legacy/escaped result can itself exceed the entire budget.
    # Retain a bounded excerpt rather than letting the newest three bypass it.
    for message in tools:
        if total <= budget: break
        content = message.get('content', '')
        if not isinstance(content, str) or len(content) <= 8000: continue
        message['content'] = json.dumps({'context_compacted':True,'excerpt':content[:4000],
                                        'summary':'结果过长，仅保留片段；请按具体区域重新读取。'},ensure_ascii=False)
        total -= len(content) - len(message['content'])
    return messages


def diff_source(before, after):
    old, new = before.splitlines(), after.splitlines()
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    added = removed = shown = 0
    hunks = []
    for tag, a, b, c, d in matcher.get_opcodes():
        if tag in {'insert', 'replace'}: added += d - c
        if tag in {'delete', 'replace'}: removed += b - a
    for group in matcher.get_grouped_opcodes(2):
        lines = []
        for tag, a, b, c, d in group:
            if tag == 'equal':
                lines.extend({'kind':'context','text':old[i][:1600],'old_line':i+1,'new_line':c+i-a+1} for i in range(a,b))
            else:
                if tag in {'delete','replace'}: lines.extend({'kind':'removed','text':old[i][:1600],'old_line':i+1} for i in range(a,b))
                if tag in {'insert','replace'}: lines.extend({'kind':'added','text':new[i][:1600],'new_line':i+1} for i in range(c,d))
        keep = lines[:max(0,400-shown)]
        if keep: hunks.append({'old_start':group[0][1]+1,'new_start':group[0][3]+1,'lines':keep})
        shown += len(lines)
    return {'hunks':hunks,'additions':added,'deletions':removed,'truncated':shown>400}


def changed_targets(operations, before, after, fallback=()):
    result = []
    for op in operations:
        selector = op.get('selector')
        if selector:
            deleted = op.get('action') == 'remove'
            target = {'selector':selector,'deleted':deleted}
            try:
                node, _ = locate(before if deleted else after, selector)
                target.update(tag=node.name, text=node.get_text(' ', strip=True)[:120])
            except PatchError:
                pass
            target['name'] = element_name(target)
            result.append(target)
        if op.get('action') in {'insert_before','insert_after','set_html','replace_outer_html','replace_region','replace_source_text'}:
            fragment = BeautifulSoup(str(op.get('value') or op.get('new') or ''), 'html.parser')
            for node in fragment.select('[data-pid], [id]')[:12]:
                selector = '[data-pid=' + json.dumps(node['data-pid']) + ']' if node.get('data-pid') else '[id=' + json.dumps(node['id']) + ']'
                result.append({'selector':selector,'name':element_name({'tag':node.name,'text':node.get_text(' ',strip=True)}),'deleted':False})
    if not result:
        result = [{**t,'name':element_name(t),'deleted':False} for t in fallback if t.get('selector')]
    return list({r['selector']:r for r in result}.values())[:24]


def result_report(raw, annotations, changed):
    """宽容地整理汇报结果。

    以前一条不合格就把整份汇报打回，模型往往重犯同样的错，轮次白白烧光，
    连已经改好的东西一起丢掉。现在坏条目单独剔除并记下原因，好的照常采纳；
    「没改动却报已完成」这类不能放行的，降级成未处理而不是整份作废。
    """
    statuses = {'completed','partial','unprocessed'}
    entries = raw.get('annotations', [])
    if not isinstance(entries, list): entries = []
    by_id = {a['id']:a for a in annotations}
    results, dropped = {}, []
    for entry in entries:
        if not isinstance(entry, dict):
            dropped.append('结构无效的条目'); continue
        ident = entry.get('id')
        if ident not in by_id:
            dropped.append(f'不存在的意见编号 {ident}'); continue
        if ident in results:
            dropped.append(f'重复汇报 {ident}'); continue
        status = entry.get('status') if entry.get('status') in statuses else 'unprocessed'
        reason = str(entry.get('reason', '')).strip()
        if status == 'completed' and not changed:
            status, reason = 'unprocessed', reason or '系统未检测到实际改动'
        if status != 'completed' and not reason:
            reason = '模型没有说明原因'
        results[ident] = {'id': ident, 'status': status, 'reason': reason}
    output = []
    for i, annotation in enumerate(annotations):
        entry = results.get(annotation['id'], {'status':'unprocessed','reason':'模型未明确汇报此项，继续保留待处理'})
        output.append({'id':annotation['id'],'number':i+1,'name':element_name(annotation),'note':annotation.get('note',''),
                       'status':entry['status'],'reason':str(entry.get('reason',''))[:300]})
    # 换种说法只在没改成时才有意义，改成了还提就是噪音。
    hint = '' if changed else str(raw.get('retry_hint','')).strip()[:200]
    return {'summary': '\n'.join(str(raw.get('summary','')).strip().splitlines()[:3])[:300] or ('修改已准备好' if changed else '没有改动页面'),
            'annotations':output, 'assumptions':[str(a)[:200] for a in raw.get('assumptions',[])[:2]],
            'retry_hint':hint, 'dropped':dropped[:5]}


# —— 改动范围检查 ————————————————————————————————————————
# 运行时检查只能发现"页面报错了没有"，发现不了"它顺手把别处也改了"。
# 用户圈中某个按钮、结果整个页头被重写，这种越界不报错、预览里也不显眼，
# 却是最让人恼火的一类问题。这里拿改动落点和用户圈定的范围对一对，
# 只做提示不拦截——往 <style> 里补一条规则是正常的，真要拦会天天误伤。

# 样式、脚本、head 是公共区：改选中元素的外观，本来就常要动这些地方。
SHARED_TAGS = {'style', 'script', 'head'}
# 新加的 <style>/<script> 整块在旧源码里并不存在，落点会算在 body 上，
# 但"给选中的按钮补一段脚本"是正当做法，单独放行。
SHARED_BLOCK = re.compile(r'<(script|style)\b.*?</\1\s*>', re.S | re.I)


def _only_shared_block(text):
    return bool(text.strip()) and not SHARED_BLOCK.sub('', text).strip()


def _tag_label(source, span):
    opening = source[span.start:span.open_end]
    ident = re.search(r'\sid\s*=\s*["\']([^"\']+)', opening)
    if ident:
        return f'{span.tag}#{ident.group(1)}'
    klass = re.search(r'\sclass\s*=\s*["\']([^"\'\s]+)', opening)
    if klass:
        return f'{span.tag}.{klass.group(1)}'
    return span.tag


def _line_span(index, span):
    """字节区间换成行号区间（闭区间，从 1 开始）。"""
    starts = index.lines
    lo = bisect.bisect_right(starts, span.start)
    hi = bisect.bisect_right(starts, max(span.start, span.end - 1))
    return lo, hi


def scope_report(before, after, annotations):
    """这次改动有没有超出用户圈定的范围。没有可判断的范围时返回 None。"""
    if not annotations or before == after:
        return None
    try:
        index = SourceIndex(before)
    except Exception:
        return None

    # strict：真正被改掉/删掉的旧行，必须落在选中元素之内。
    # loose：纯插入没有对应的旧行，写在元素紧邻处是正常的（insert_before/after），放宽一行。
    strict, loose, located = [], [], 0
    for annotation in annotations:
        for target in (annotation.get('targets') or [annotation]):
            selector = target.get('selector')
            if not selector:
                continue
            try:
                _, span = locate(before, selector)
            except (PatchError, Exception):
                continue
            located += 1
            lo, hi = _line_span(index, span)
            strict.append((lo, hi))
            loose.append((lo - 1, hi + 1))
    if not located:
        return None                      # 选中的元素在旧源码里找不到，无从判断

    for span in index.nodes.values():
        if span.tag in SHARED_TAGS and span.end > 0:
            zone = _line_span(index, span)
            strict.append(zone)
            loose.append(zone)

    old_lines, new_lines = before.splitlines(), after.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    stray = []
    for tag, a, b, c, d in matcher.get_opcodes():
        if tag == 'equal':
            continue
        if tag == 'insert':
            if _only_shared_block('\n'.join(new_lines[c:d])):
                continue
            if not any(lo <= a + 1 <= hi for lo, hi in loose):
                stray.append(a + 1)          # 插入点所在的旧行
            continue
        for line in range(a + 1, b + 1):     # 被改掉或删掉的旧行，逐行严格判定
            if not any(lo <= line <= hi for lo, hi in strict):
                stray.append(line)
    if not stray:
        return None

    places, seen = [], set()
    for line in stray:
        at = index.lines[line - 1]
        holder = None
        for span in index.nodes.values():
            if span.end > at >= span.start and (holder is None or span.start > holder.start):
                holder = span
        label = _tag_label(before, holder) if holder else '页面顶层'
        if label not in seen:
            seen.add(label)
            places.append(label)
    return {'lines': len(stray), 'places': places[:5], 'more': max(0, len(seen) - 5)}
