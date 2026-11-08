<script setup>
import { computed, ref } from 'vue'
import { Check, Undo2, ChevronDown, AlertCircle, BookmarkCheck, MessageCircle, Sparkles, Lightbulb } from 'lucide-vue-next'
import { brief, iconOf } from '../../lib/toolIcons.js'
import { prose } from '../../lib/prose.js'
import SpecCard from './SpecCard.vue'
import PlanCard from './PlanCard.vue'
import DiffLines from './DiffLines.vue'
// applied：这张卡上已经照着改好（并保存）的建议的 instruction，由对话记录推出来，刷新后也对
const props = defineProps({ result: Object, canUndo: Boolean, locked: Boolean, checking: Boolean, selftest: Object, applied: { type: Array, default: () => [] }, specState: { type: String, default: 'open' }, planState: { type: String, default: 'open' }, planConfirmed: Object })
const emit = defineEmits(['undo', 'choose', 'apply', 'discuss', 'custom', 'rephrase', 'forget', 'draw-spec', 'revise-spec', 'draw-plan', 'revise-plan'])
const report = computed(() => props.result?.report)
const discussion = computed(() => props.result?.discussion)
// A question is already rendered by its own block; everything else needs a headline.
const headline = computed(() => report.value?.summary || discussion.value?.answer || (props.result?.clarification ? '' : props.result?.content || ''))
// 这次新记住的约定：明明白白摆在回复下面，记错了当场点「不用记」
const remembered = computed(() => report.value?.remembered || discussion.value?.remembered || props.result?.clarification?.remembered || props.result?.remembered || [])
const forgotten = ref(new Set())
function forget(item) { forgotten.value = new Set([...forgotten.value, item.id]); emit('forget', item.id) }
// 讨论给出的几条改法：一行一条，勾选要做的，一次交给 AI；说明默认收起，要看再点开
const suggestions = computed(() => discussion.value?.suggestions || [])
// 默认只勾推荐的那条（参照 Claude：推荐的排第一、先替你选好）；以前没有推荐标记的旧消息照旧全选
const defaultPick = () => suggestions.value.some(s => 'recommended' in s) ? new Set(suggestions.value.flatMap((s, i) => s.recommended ? [i] : [])) : null
const picked = ref(defaultPick())   // null = 全选
const opened = ref(new Set())
// 已经改好的建议：打勾、不能再选；全改好了就不再挂「按这个改」
const isDone = i => props.applied.includes(suggestions.value[i]?.instruction)
const allDone = computed(() => suggestions.value.length > 0 && suggestions.value.every((_, i) => isDone(i)))
const isPicked = i => !isDone(i) && (!picked.value || picked.value.has(i))
const chosen = computed(() => suggestions.value.filter((_, i) => isPicked(i)))
function togglePick(i) { const next = new Set(picked.value ?? suggestions.value.map((_, k) => k)); next.has(i) ? next.delete(i) : next.add(i); picked.value = next }
function toggleOpen(i) { const next = new Set(opened.value); next.has(i) ? next.delete(i) : next.add(i); opened.value = next }
const applyLabel = computed(() => {
  const n = chosen.value.length, all = suggestions.value.filter((_, i) => !isDone(i)).length
  if (all === 1 && suggestions.value.length === 1) return '按这个改'
  if (!n) return '先勾选'
  return n === 1 ? '改这 1 条' : n === all ? `全部改（${n}）` : `改这 ${n} 条`
})
function applyChosen() { if (chosen.value.length) emit('apply', { suggestions: chosen.value, discussion: discussion.value }) }
// 底下一个按钮：写了自己的想法就是「发送」，没写就是照勾的改
function primaryAction() { other.value.trim() ? sendOther() : applyChosen() }
// 改动明细默认收起：一行「已保存 · 改了 N 处 +x −y」，点开看
const showDiff = ref(false)
// 「其他」：都不想要，直接写自己的想法
const other = ref('')
function sendOther() { const text = other.value.trim(); if (!text || props.locked) return; other.value = ''; emit('custom', { text, discussion: discussion.value }) }
// 回复上面一行「做了 N 步 · 用时」（参照 Claude 收起的工具调用）：点开看当时边做边说的话和每一步拿到了什么
const showTrail = ref(false)
// 思考过程默认露三行，点「展开全部」看完整的
const openThink = ref(new Set())
// 收起时并成一行截断（以前用 CSS 截三行，开头有空行时上下各露半行字）
const CLIP = 90
const flat = t => String(t || '').replace(/\s+/g, ' ').trim()
const clip = t => { const x = flat(t); return x.length > CLIP ? x.slice(0, CLIP) + '…' : x }
function toggleThink(i) { const next = new Set(openThink.value); next.has(i) ? next.delete(i) : next.add(i); openThink.value = next }
const trail = computed(() => props.result?.trail || [])
const toolSteps = computed(() => trail.value.filter(r => r.note == null && r.think == null).length)
const took = computed(() => { const t = props.result?.took || 0; return t >= 60 ? ['用时 {0} 分 {1} 秒', [Math.floor(t / 60), t % 60]] : t ? ['用时 {0} 秒', [t]] : null })
const statuses = { completed: '已完成', partial: '部分完成', unprocessed: '未处理' }
</script>
<template>
  <div class="result-card">
    <div v-if="trail.length" class="trail" :class="{ open: showTrail }">
      <button type="button" class="trail-head" :aria-expanded="showTrail" @click="showTrail = !showTrail">{{ toolSteps ? $t('做了 {0} 步', [toolSteps]) : $t('思考过程') }}<small v-if="took">{{ $t(...took) }}</small><ChevronDown :size="12" /></button>
      <ol v-if="showTrail"><li v-for="(r, i) in trail" :key="i" :class="{ note: r.note != null, think: r.think != null, error: r.error }"><template v-if="r.note != null || r.think != null"><Lightbulb v-if="r.think != null" :size="13" /><div class="think-body"><p v-if="openThink.has(i)" class="full">{{ (r.think ?? r.note).trim() }}</p><p v-else>{{ clip(r.think ?? r.note) }}</p><button v-if="flat(r.think ?? r.note).length > CLIP" type="button" class="text-button think-more" @click="toggleThink(i)">{{ openThink.has(i) ? $t('收起') : $t('展开全部') }}</button></div></template><template v-else><component :is="r.error ? AlertCircle : iconOf(r)" :size="13" /><div class="trail-tool"><button v-if="r.diff" type="button" class="trail-row" :aria-expanded="openThink.has(i)" @click="toggleThink(i)">{{ $t(r.label) }}<em class="diffstat"><i class="add">+{{ r.diff.additions }}</i><i class="del">−{{ r.diff.deletions }}</i></em><ChevronDown :size="11" /></button><span v-else>{{ $t(r.label) }}<em v-if="brief(r)">{{ brief(r) }}</em></span><DiffLines v-if="r.diff && openThink.has(i)" :diff="r.diff" /></div></template></li></ol>
    </div>
    <div v-if="headline" class="result-summary prose" v-html="prose($t(headline))"></div>
    <SpecCard v-if="result.spec" :spec="result.spec" :state="specState" :locked="locked" @draw="$emit('draw-spec', $event)" @revise="$emit('revise-spec', $event)" />
    <PlanCard v-if="result.plan" :plan="result.plan" :state="planState" :confirmed="planConfirmed" :locked="locked" @draw="$emit('draw-plan', $event)" @revise="$emit('revise-plan', $event)" />
    <div v-if="result.clarification" class="clarification chat-card"><div class="chat-card-head"><MessageCircle :size="13" /><span>{{ $t('需要你定一下') }}</span></div><p class="clarify-q">{{ result.clarification.question }}</p><div class="clarify-options"><button v-for="option in result.clarification.options" :key="option" type="button" class="choice-row" :disabled="locked" @click="$emit('choose', { option, clarification: result.clarification })">{{ option }}</button></div></div>
    <div v-if="suggestions.length" class="suggest-box">
      <div class="suggest-head"><Sparkles :size="13" /><span>{{ $t('可以这样改') }}</span><small v-if="suggestions.length > 1">{{ $t('可以多选') }}</small></div>
      <ul class="suggest-list">
        <li v-for="(s, i) in suggestions" :key="i" :class="{ off: !isPicked(i) && !isDone(i), done: isDone(i) }">
          <label class="suggest-row"><Check v-if="isDone(i)" :size="15" class="suggest-check" /><input v-else-if="suggestions.length > 1" type="checkbox" :checked="isPicked(i)" :disabled="locked" @change="togglePick(i)"><span class="suggest-text"><span class="suggest-title">{{ $t(s.label) }}<em v-if="isDone(i)" class="done-tag">{{ $t('已改好') }}</em><em v-else-if="s.recommended && suggestions.length > 1">{{ $t('推荐') }}</em></span><small v-if="s.summary">{{ s.summary }}</small></span></label>
          <button type="button" class="suggest-icon" :class="{ open: opened.has(i) }" :aria-label="opened.has(i) ? $t('收起说明') : $t('看具体怎么改')" :title="opened.has(i) ? $t('收起说明') : $t('看具体怎么改')" @click="toggleOpen(i)"><ChevronDown :size="14" /></button>
          <button type="button" class="suggest-icon" :aria-label="$t('继续聊这条')" :title="$t('继续聊这条')" :disabled="locked" @click="$emit('discuss', s)"><MessageCircle :size="13" /></button>
          <p v-if="opened.has(i)" class="suggest-detail"><b>{{ $t('交给 AI 的具体做法') }}</b>{{ s.instruction }}</p>
        </li>
      </ul>
      <p v-if="allDone" class="suggest-done"><Check :size="13" />{{ $t('已经按这些建议改好了，要再调整直接在下面说') }}</p>
      <div v-else class="suggest-foot"><input v-model="other" class="suggest-other" maxlength="500" :disabled="locked" :placeholder="$t('或者说说你的想法…')" :aria-label="$t('其他想法')" @keydown.enter.prevent="sendOther">
        <button v-if="!allDone" class="primary suggest-apply" :disabled="locked || (!other.trim() && !chosen.length)" @click="primaryAction">{{ other.trim() ? $t('发送') : $t(applyLabel) }}</button></div>
    </div>
    <ol v-if="report?.annotations?.length" class="opinion-results"><li v-for="item in report.annotations" :key="item.id" :class="item.status"><span>{{ $t(item.number) }}</span><div><b>{{ item.note || item.name }}</b><small>{{ $t(statuses[item.status]) }}{{ item.reason ? $t('：') + item.reason : '' }}</small></div></li></ol>
    <div v-for="item in remembered" :key="item.id" class="remembered" :class="{ gone: forgotten.has(item.id) }"><BookmarkCheck :size="13" /><span v-if="!forgotten.has(item.id)">{{ $t('记住了：{0}', [item.text]) }}<small>{{ item.scope === 'global' ? $t('记在你的习惯里，以后所有项目都照这个来') : $t('以后这个项目的所有页面都照这个来') }}</small></span><span v-else>{{ $t('已忘掉：{0}', [item.text]) }}</span><button v-if="!forgotten.has(item.id)" type="button" class="text-button" :disabled="locked" @click="forget(item)">{{ $t('不用记') }}</button></div>
    <p v-for="assumption in report?.assumptions || []" :key="assumption" class="result-assumption">{{ $t('需要确认：{0}', [assumption]) }}</p>
    <p v-if="report?.out_of_scope" class="scope-note"><AlertCircle :size="12" />{{ $t('还改到了你圈定范围之外的 {0} 行（{1}{2}）。已经保存，请检查这些地方，不对就撤销这次修改', [$t(report.out_of_scope.lines), report.out_of_scope.places.join($t('、')), report.out_of_scope.more ? $t(' 等') : '']) }}</p>
    <div v-if="report?.retry_hint" class="retry-hint"><span>{{ $t('换种说法试试') }}</span><button class="outline" :disabled="locked" @click="$emit('rephrase', report.retry_hint)">{{ $t(report.retry_hint) }}</button></div>
    <div v-if="result.changed" class="change-row"><button type="button" class="change-chip" :disabled="!result.diff?.hunks?.length" :aria-expanded="showDiff" :title="$t('查看改动')" @click="showDiff = !showDiff"><span class="change-icon"><Check :size="11" /></span><span>{{ $t('{0} · 改了 {1} 处', [checking ? $t('检查中') : $t('已保存'), result.change_count || result.diff?.hunks?.length || 1]) }}</span><em v-if="result.diff"><i class="add">+{{ $t(result.diff.additions) }}</i><i class="del">−{{ $t(result.diff.deletions) }}</i></em><ChevronDown v-if="result.diff?.hunks?.length" :size="13" class="fold" :class="{ open: showDiff }" /></button><button v-if="!checking" class="text-button undo-mini" :disabled="locked || !canUndo" :title="canUndo ? $t('撤销这次修改') : $t('先撤销后续修改，才能撤销这一项')" @click="$emit('undo', result.change_id)"><Undo2 :size="13" />{{ $t('撤销') }}</button></div>
    <div v-if="selftest && !selftest.skipped" class="selftest" :class="{ ok: !selftest.issues.length }"><b>{{ !selftest.issues.length ? $t('自检通过：{0} 个页面、{1} 个按钮都点过，没发现问题', [$t(selftest.routes), $t(selftest.clicked)]) : selftest.final ? $t('自检还剩 {0} 个问题，需要你看一下', [$t(selftest.issues.length)]) : $t('自检发现 {0} 个问题，已自动交回去修', [$t(selftest.issues.length)]) }}</b><ul v-if="selftest.issues.length"><li v-for="it in selftest.issues" :key="it.text"><em>{{ $t(it.kind) }}</em>{{ it.text }}</li></ul><p v-if="selftest.accept">{{ selftest.accept }}</p></div>
    <div v-if="result.changed && showDiff && result.diff" class="result-actions"><div class="diff-view"><div v-for="(hunk, i) in result.diff.hunks" :key="i" class="diff-hunk"><small>{{ $t('原 {0} 行 / 新 {1} 行', [$t(hunk.old_start), $t(hunk.new_start)]) }}</small><pre><span v-for="(line, j) in hunk.lines" :key="j" :class="line.kind">{{ line.kind === 'added' ? '+' : line.kind === 'removed' ? '−' : ' ' }} {{ line.text }}{{ '\n' }}</span></pre></div><p v-if="result.diff.truncated" class="field-hint">{{ $t('改动较多，这里只展示前面一部分。') }}</p></div></div>
    <p v-for="target in (result.targets || []).filter(t => t.deleted)" :key="target.selector" class="deleted-note"><AlertCircle :size="12" />{{ $t('已删除{0}', [target.name || $t('选中元素')]) }}</p>
  </div>
</template>
<style scoped>
.trail{margin:0 0 8px;font-size:12px;color:var(--muted)}
.trail-head{display:inline-flex;align-items:center;gap:5px;padding:2px 8px 2px 0;border:0;background:none;color:var(--muted);font-size:12px;cursor:pointer}.trail-head:hover{color:var(--ink)}
.trail-head small{font-size:11.5px;color:var(--subtle)}.trail-head small::before{content:'·';margin-right:5px}
.trail-head svg{transition:transform .15s}.trail.open .trail-head svg{transform:rotate(180deg)}
.trail ol{list-style:none;margin:6px 0 10px 6px;padding:0 0 0 13px;border-left:1.5px solid var(--line);display:flex;flex-direction:column;gap:6px}
.trail li{display:flex;gap:7px;line-height:1.6}.trail li svg{flex:none;margin-top:3px;color:var(--subtle)}.trail li.note{color:var(--muted)}.trail li.error,.trail li.error svg{color:#a24b37}
.think-body{min-width:0;flex:1}.think-body p{margin:0;font-size:12px;line-height:1.7;overflow-wrap:anywhere}.trail li.think p{font-size:11.5px;color:var(--subtle)}
.think-body p.full{white-space:pre-wrap;max-height:360px;overflow:auto}.think-more{margin-top:2px;padding:0;font-size:11.5px}
.trail-tool{min-width:0;flex:1}.trail-row{display:inline-flex;align-items:center;gap:4px;padding:0;border:0;background:none;color:inherit;font:inherit;cursor:pointer}.trail-row:hover{color:var(--ink)}
.diffstat{display:inline-flex;gap:4px;margin-left:2px;font-style:normal!important;font-variant-numeric:tabular-nums}.diffstat i{font-style:normal}.diffstat .add{color:#2f7d45}.diffstat .del{color:#b0473a}
.trail li span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.trail li em{margin-left:6px;font-style:normal;color:var(--subtle)}
.remembered{display:flex;align-items:flex-start;gap:7px;margin-top:10px;padding:7px 10px;border-radius:var(--r-item);background:var(--quiet);font-size:12px;color:var(--ink)}
.remembered svg{flex-shrink:0;margin-top:3px;color:var(--primary)}
.remembered span{flex:1;min-width:0;overflow-wrap:anywhere}.remembered small{display:block;font-size:11px;color:var(--muted)}
.remembered button{flex-shrink:0;font-size:11.5px}.remembered.gone{opacity:.6}
.selftest{margin-top:8px;padding:7px 10px;border-radius:var(--r-item);background:#fbf4e6;font-size:12px}.selftest.ok{background:transparent;padding:0 2px;color:var(--success)}.selftest b{font-weight:500}.selftest ul{margin:6px 0 0;padding-left:0;list-style:none;display:grid;gap:4px}.selftest li{color:var(--muted);font-size:11.5px;line-height:1.6}.selftest p{margin:4px 0 0;font-size:11.5px;color:var(--muted)}.selftest em{font-style:normal;font-size:10px;padding:1px 6px;margin-right:6px;border-radius:var(--r-tag);background:#f3e6cc;color:#8a5a12}
/* 回复正文直接流在背景上；只有 diff、建议这类块才有自己的容器。 */
.result-card{font-size:12.5px;line-height:1.7}
.result-summary{overflow-wrap:anywhere}
.change-row{display:flex;align-items:center;gap:4px;margin-top:10px}
.change-chip{min-width:0;gap:7px;padding:5px 10px 5px 6px;border:1px solid var(--line);border-radius:var(--r-item);background:#fff;font-size:12px;color:var(--ink);font-weight:500}.change-chip:hover:not(:disabled){border-color:#d6d1c4;background:#fdfcf9}.change-chip:disabled{opacity:1;cursor:default}
.change-icon{display:grid;place-items:center;width:18px;height:18px;border-radius:var(--r-tag);background:#e6f1e7;color:var(--success)}
.change-chip em{font-style:normal;display:flex;gap:5px;font-size:11.5px;font-weight:400;font-variant-numeric:tabular-nums}.change-chip .add{font-style:normal;color:#2f7a45}.change-chip .del{font-style:normal;color:#b24a36}
.change-chip .fold{color:var(--subtle);transition:transform .15s}.change-chip .fold.open{transform:rotate(180deg)}
.undo-mini{gap:4px;padding:5px 8px;border-radius:var(--r-item);font-size:12px;color:var(--muted)}.undo-mini:hover:not(:disabled){background:var(--quiet);color:var(--ink)}
.result-actions{margin-top:6px}.result-actions>details{min-width:0;width:100%}.result-actions summary{list-style:none;display:flex;gap:5px;align-items:center;color:var(--muted);cursor:pointer;font-size:12px}.result-actions summary::-webkit-details-marker{display:none}
.diff-view{overflow:auto;max-height:320px;border:1px solid var(--line);border-radius:var(--r-item);background:#fff}.diff-hunk small{display:block;padding:5px 8px;background:#f1eeed;color:var(--muted);font-size:10px}.diff-hunk pre{font:11px/1.7 ui-monospace,SFMono-Regular,monospace;margin:0;min-width:100%;width:max-content}.diff-hunk pre span{display:block;padding:0 8px;white-space:pre}.diff-hunk .added{background:#e3efe1;color:#2f6b3d}.diff-hunk .removed{background:#f7e4e0;color:#9c4034}.diff-hunk .context{color:#837a76}
.opinion-results{list-style:none;padding:0;display:flex;flex-direction:column;gap:9px;margin:12px 0}.opinion-results li{display:flex;gap:7px}.opinion-results li>span{border-radius:50%;background:var(--quiet);font-size:10px;width:18px;height:18px;text-align:center;flex-shrink:0}.opinion-results b{font-weight:500}.opinion-results small{display:block;color:var(--muted);font-size:11px}.opinion-results .completed small{color:var(--success)}.opinion-results .partial small,.opinion-results .unprocessed small{color:#906323}
.suggest-box{margin-top:12px;border:1px solid var(--line);border-radius:var(--r-card);background:#fff;padding:8px 6px 6px;box-shadow:var(--chat-shadow)}
.clarify-q{margin:0 8px 8px;font-size:13px;font-weight:500;color:var(--ink);white-space:pre-wrap}.clarify-options{display:flex;flex-direction:column;gap:6px;margin:0 4px 4px}
.suggest-head{display:flex;align-items:center;gap:6px;padding:2px 8px 6px;font-size:12px;font-weight:600;color:var(--ink)}.suggest-head svg{color:var(--primary)}.suggest-head small{margin-left:auto;font-weight:400;font-size:11px;color:var(--muted)}
.suggest-list{list-style:none;margin:0;padding:0}
.suggest-list li{display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:0;padding:1px 4px 1px 2px;border-radius:var(--r-item)}.suggest-list li:hover{background:var(--quiet)}
.suggest-row{display:flex;align-items:center;gap:9px;min-width:0;padding:6px;cursor:pointer;font-size:12.5px;font-weight:500;color:var(--ink)}
.suggest-row input{width:15px;height:15px;margin:0;flex-shrink:0;accent-color:var(--primary);cursor:pointer}
.suggest-row{align-items:flex-start}.suggest-row input{margin-top:3px}
.suggest-text{display:flex;flex-direction:column;min-width:0}
.suggest-title{display:flex;align-items:center;gap:6px;overflow:hidden;white-space:nowrap}
.suggest-title em{flex-shrink:0;font-style:normal;font-size:10px;font-weight:500;line-height:1;padding:3px 6px;border-radius:var(--r-item);background:var(--primary-soft);color:var(--primary)}
.suggest-text small{font-size:11.5px;font-weight:400;line-height:1.6;color:var(--muted);margin-top:1px}
.suggest-detail b{display:block;font-size:10.5px;font-weight:600;color:var(--muted);margin-bottom:2px}
.suggest-foot{display:flex;align-items:center;gap:6px;margin-top:6px;padding:6px 2px 0;border-top:1px solid #f0ede4}
.suggest-other{flex:1;min-width:0;height:32px;padding:0 8px;border:none;border-radius:var(--r-item);outline:none;background:none;font-size:12.5px;color:var(--ink)}
.suggest-other:focus{background:var(--quiet)}
.suggest-list li.off .suggest-row{color:var(--muted)}
.suggest-icon{width:26px;height:26px;display:grid;place-items:center;border-radius:var(--r-tag);color:var(--subtle);opacity:0;transition:opacity .12s}.suggest-list li:hover .suggest-icon,.suggest-icon:focus-visible,.suggest-icon.open{opacity:1}.suggest-icon:hover:not(:disabled){background:#e9e6dc;color:var(--ink)}
@media (hover:none){.suggest-icon{opacity:1}}
.suggest-icon svg{transition:transform .15s}.suggest-icon.open svg{transform:rotate(180deg)}
.suggest-detail{grid-column:1/-1;margin:0 0 6px;padding:7px 9px;border-radius:var(--r-tag);background:var(--quiet);font-size:11.5px;line-height:1.7;color:#5f5a52}
.suggest-apply{flex:none;min-height:32px;padding:5px 12px;border-radius:var(--r-item);font-size:12.5px}
.suggest-check{flex:none;color:var(--ok, #1f8a4c);margin-top:2px}
li.done .suggest-title{color:var(--muted)}
em.done-tag{background:#e7f6ee !important;color:#1f8a4c !important}
.suggest-done{display:flex;align-items:center;gap:6px;margin:4px 0 2px;padding:6px 8px 0;border-top:1px solid #f0ede4;font-size:12px;color:#1f8a4c}
.retry-hint{margin-top:11px}.retry-hint>span{display:block;font-size:11px;color:var(--muted);margin-bottom:6px}.retry-hint button{width:100%;text-align:left;white-space:normal;line-height:1.6;font-size:12px;padding:8px 10px}
.result-assumption,.deleted-note{margin-top:8px;font-size:11px;color:var(--muted)}
.scope-note{display:flex;align-items:flex-start;gap:5px;margin-top:8px;font-size:11px;line-height:1.6;color:#906323}.scope-note svg{flex-shrink:0;margin-top:3px}.deleted-note{display:flex;align-items:center;gap:5px}.clarification{margin-top:10px}.clarification>p{font-size:13.5px;line-height:1.8;margin-bottom:4px}.clarification button{display:flex;width:100%;justify-content:flex-start;margin:6px 0 0;padding:9px 12px;border-radius:11px;white-space:normal;text-align:left;line-height:1.5;font-weight:400;font-size:12.5px}.clarification button:hover:not(:disabled){background:var(--quiet)}
</style>
