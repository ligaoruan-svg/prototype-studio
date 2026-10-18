<script setup>
import { computed, ref } from 'vue'
import { Check, Undo2, ChevronDown, AlertCircle, BookmarkCheck, MessageCircle, Sparkles } from 'lucide-vue-next'
const props = defineProps({ result: Object, canUndo: Boolean, locked: Boolean, checking: Boolean, selftest: Object })
const emit = defineEmits(['undo', 'choose', 'apply', 'discuss', 'custom', 'rephrase', 'forget'])
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
const isPicked = i => !picked.value || picked.value.has(i)
const chosen = computed(() => suggestions.value.filter((_, i) => isPicked(i)))
function togglePick(i) { const next = new Set(picked.value ?? suggestions.value.map((_, k) => k)); next.has(i) ? next.delete(i) : next.add(i); picked.value = next }
function toggleOpen(i) { const next = new Set(opened.value); next.has(i) ? next.delete(i) : next.add(i); opened.value = next }
const applyLabel = computed(() => {
  const n = chosen.value.length, all = suggestions.value.length
  if (all === 1) return '按这个改'
  if (!n) return '先勾选要改的'
  return n === all ? `全部修改（${n} 条）` : `修改选中的 ${n} 条`
})
function applyChosen() { if (chosen.value.length) emit('apply', { suggestions: chosen.value, discussion: discussion.value }) }
// 「其他」：都不想要，直接写自己的想法
const other = ref('')
function sendOther() { const text = other.value.trim(); if (!text || props.locked) return; other.value = ''; emit('custom', { text, discussion: discussion.value }) }
const statuses = { completed: '已完成', partial: '部分完成', unprocessed: '未处理' }
</script>
<template>
  <div class="result-card">
    <p v-if="headline" class="result-summary">{{ headline }}</p>
    <div v-if="result.clarification" class="clarification"><p>{{ result.clarification.question }}</p><button v-for="option in result.clarification.options" :key="option" class="outline" :disabled="locked" @click="$emit('choose', { option, clarification: result.clarification })">{{ option }}</button></div>
    <div v-if="suggestions.length" class="suggest-box">
      <div class="suggest-head"><Sparkles :size="13" /><span>可以这样改</span><small v-if="suggestions.length > 1">勾选要做的，一次交给 AI</small></div>
      <ul class="suggest-list">
        <li v-for="(s, i) in suggestions" :key="i" :class="{ off: !isPicked(i) }">
          <label class="suggest-row"><input v-if="suggestions.length > 1" type="checkbox" :checked="isPicked(i)" :disabled="locked" @change="togglePick(i)"><span class="suggest-text"><span class="suggest-title">{{ s.label }}<em v-if="s.recommended && suggestions.length > 1">推荐</em></span><small v-if="s.summary">{{ s.summary }}</small></span></label>
          <button type="button" class="suggest-icon" :class="{ open: opened.has(i) }" :aria-label="opened.has(i) ? '收起说明' : '看具体怎么改'" :title="opened.has(i) ? '收起说明' : '看具体怎么改'" @click="toggleOpen(i)"><ChevronDown :size="14" /></button>
          <button type="button" class="suggest-icon" aria-label="继续聊这条" title="继续聊这条" :disabled="locked" @click="$emit('discuss', s)"><MessageCircle :size="13" /></button>
          <p v-if="opened.has(i)" class="suggest-detail"><b>交给 AI 的具体做法</b>{{ s.instruction }}</p>
        </li>
      </ul>
      <div class="suggest-other"><input v-model="other" maxlength="500" :disabled="locked" placeholder="都不想要？直接说你的想法" aria-label="其他想法" @keydown.enter.prevent="sendOther"><button type="button" class="text-button" :disabled="locked || !other.trim()" @click="sendOther">发送</button></div>
      <button class="primary suggest-apply" :disabled="locked || !chosen.length" @click="applyChosen">{{ applyLabel }}</button>
    </div>
    <ol v-if="report?.annotations?.length" class="opinion-results"><li v-for="item in report.annotations" :key="item.id" :class="item.status"><span>{{ item.number }}</span><div><b>{{ item.note || item.name }}</b><small>{{ statuses[item.status] }}{{ item.reason ? '：' + item.reason : '' }}</small></div></li></ol>
    <div v-for="item in remembered" :key="item.id" class="remembered" :class="{ gone: forgotten.has(item.id) }"><BookmarkCheck :size="13" /><span v-if="!forgotten.has(item.id)">记住了：{{ item.text }}<small>{{ item.scope === 'global' ? '记在你的习惯里，以后所有项目都照这个来' : '以后这个项目的所有页面都照这个来' }}</small></span><span v-else>已忘掉：{{ item.text }}</span><button v-if="!forgotten.has(item.id)" type="button" class="text-button" :disabled="locked" @click="forget(item)">不用记</button></div>
    <p v-for="assumption in report?.assumptions || []" :key="assumption" class="result-assumption">需要确认：{{ assumption }}</p>
    <p v-if="report?.out_of_scope" class="scope-note"><AlertCircle :size="12" />还改到了你圈定范围之外的 {{ report.out_of_scope.lines }} 行（{{ report.out_of_scope.places.join('、') }}{{ report.out_of_scope.more ? ' 等' : '' }}）。已经保存，请检查这些地方，不对就撤销这次修改</p>
    <div v-if="report?.retry_hint" class="retry-hint"><span>换种说法试试</span><button class="outline" :disabled="locked" @click="$emit('rephrase', report.retry_hint)">{{ report.retry_hint }}</button></div>
    <div v-if="result.changed" class="change-summary"><Check :size="14" /><strong>{{ checking ? '检查中' : '已保存' }} · 改了 {{ result.change_count || result.diff?.hunks?.length || 1 }} 处</strong><span v-if="result.diff">+{{ result.diff.additions }} / −{{ result.diff.deletions }}</span></div>
    <div v-if="selftest && !selftest.skipped" class="selftest" :class="{ ok: !selftest.issues.length }"><b>{{ !selftest.issues.length ? `自检通过：${selftest.routes} 个页面、${selftest.clicked} 个按钮都点过，没发现问题` : selftest.final ? `自检还剩 ${selftest.issues.length} 个问题，需要你看一下` : `自检发现 ${selftest.issues.length} 个问题，已自动交回去修` }}</b><ul v-if="selftest.issues.length"><li v-for="it in selftest.issues" :key="it.text"><em>{{ it.kind }}</em>{{ it.text }}</li></ul></div>
    <div v-if="result.changed" class="result-actions"><details v-if="result.diff"><summary>查看改动<ChevronDown :size="13" /></summary><div class="diff-view"><div v-for="(hunk, i) in result.diff.hunks" :key="i" class="diff-hunk"><small>原 {{ hunk.old_start }} 行 / 新 {{ hunk.new_start }} 行</small><pre><span v-for="(line, j) in hunk.lines" :key="j" :class="line.kind">{{ line.kind === 'added' ? '+' : line.kind === 'removed' ? '−' : ' ' }} {{ line.text }}{{ '\n' }}</span></pre></div><p v-if="result.diff.truncated" class="field-hint">改动较多，这里只展示前面一部分。</p></div></details><button v-if="!checking" class="text-button" :disabled="locked || !canUndo" :title="canUndo ? '撤销这次修改' : '先撤销后续修改，才能撤销这一项'" @click="$emit('undo', result.change_id)"><Undo2 :size="13" />撤销这次修改</button></div>
    <p v-for="target in (result.targets || []).filter(t => t.deleted)" :key="target.selector" class="deleted-note"><AlertCircle :size="12" />已删除{{ target.name || '选中元素' }}</p>
  </div>
</template>
<style scoped>
.remembered{display:flex;align-items:flex-start;gap:7px;margin-top:10px;padding:8px 10px;border:1px solid #e6d8c6;border-radius:9px;background:#fbf7f0;font-size:12px;color:var(--ink)}
.remembered svg{flex-shrink:0;margin-top:3px;color:var(--primary)}
.remembered span{flex:1;min-width:0;overflow-wrap:anywhere}.remembered small{display:block;font-size:11px;color:var(--muted)}
.remembered button{flex-shrink:0;font-size:11.5px}.remembered.gone{opacity:.6}
.selftest{margin-top:10px;padding:8px 10px;border:1px solid #ecd9b8;border-radius:9px;background:#fdf8ee;font-size:12px}.selftest.ok{border-color:#cfe3d2;background:#f3f9f4}.selftest b{font-weight:500}.selftest ul{margin:6px 0 0;padding-left:0;list-style:none;display:grid;gap:4px}.selftest li{color:var(--muted);font-size:11.5px;line-height:1.6}.selftest em{font-style:normal;font-size:10px;padding:1px 6px;margin-right:6px;border-radius:8px;background:#f3e6cc;color:#8a5a12}
/* 回复正文直接流在背景上；只有 diff、建议这类块才有自己的容器。 */
.result-card{font-size:12px;line-height:1.7}
.result-summary{font-size:13px;line-height:1.85;color:var(--ink);white-space:pre-wrap;overflow-wrap:anywhere}
.change-summary{display:flex;align-items:center;gap:6px;color:var(--success);font-size:11px;margin-top:10px}.change-summary strong{font-weight:500}.change-summary>span{margin-left:auto;color:var(--muted);font-variant-numeric:tabular-nums}
.result-actions{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-top:9px;flex-wrap:wrap}.result-actions>details{min-width:0;width:100%}.result-actions summary{list-style:none;display:flex;gap:5px;align-items:center;color:var(--muted);cursor:pointer;font-size:12px}.result-actions summary::-webkit-details-marker{display:none}
.diff-view{overflow:auto;max-height:320px;margin-top:9px;border:1px solid var(--line);border-radius:5px;background:#fbfafa}.diff-hunk small{display:block;padding:5px 8px;background:#f1eeed;color:var(--muted);font-size:10px}.diff-hunk pre{font:11px/1.7 ui-monospace,SFMono-Regular,monospace;margin:0;min-width:100%;width:max-content}.diff-hunk pre span{display:block;padding:0 8px;white-space:pre}.diff-hunk .added{background:#e3efe1;color:#2f6b3d}.diff-hunk .removed{background:#f7e4e0;color:#9c4034}.diff-hunk .context{color:#837a76}
.opinion-results{list-style:none;padding:0;display:flex;flex-direction:column;gap:9px;margin:12px 0}.opinion-results li{display:flex;gap:7px}.opinion-results li>span{border-radius:50%;background:var(--quiet);font-size:10px;width:18px;height:18px;text-align:center;flex-shrink:0}.opinion-results b{font-weight:500}.opinion-results small{display:block;color:var(--muted);font-size:11px}.opinion-results .completed small{color:var(--success)}.opinion-results .partial small,.opinion-results .unprocessed small{color:#906323}
.suggest-box{margin-top:12px;border:1px solid var(--line);border-radius:10px;background:#fff;padding:10px 10px 12px}
.suggest-head{display:flex;align-items:center;gap:6px;padding:0 2px 6px;font-size:12px;font-weight:600;color:var(--ink)}.suggest-head svg{color:var(--primary)}.suggest-head small{margin-left:auto;font-weight:400;font-size:11px;color:var(--muted)}
.suggest-list{list-style:none;margin:0;padding:0}
.suggest-list li{display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:2px;padding:3px 0;border-top:1px solid #f0ede4}.suggest-list li:first-child{border-top:none}
.suggest-row{display:flex;align-items:center;gap:8px;min-width:0;padding:5px 2px;cursor:pointer;font-size:12.5px;font-weight:500;color:var(--ink)}
.suggest-row input{width:15px;height:15px;margin:0;flex-shrink:0;accent-color:var(--primary);cursor:pointer}
.suggest-row{align-items:flex-start}.suggest-row input{margin-top:3px}
.suggest-text{display:flex;flex-direction:column;min-width:0}
.suggest-title{display:flex;align-items:center;gap:6px;overflow:hidden;white-space:nowrap}
.suggest-title em{flex-shrink:0;font-style:normal;font-size:10px;font-weight:500;line-height:1;padding:3px 6px;border-radius:9px;background:var(--primary-soft);color:var(--primary)}
.suggest-text small{font-size:11.5px;font-weight:400;line-height:1.6;color:var(--muted);margin-top:1px}
.suggest-detail b{display:block;font-size:10.5px;font-weight:600;color:var(--muted);margin-bottom:2px}
.suggest-other{display:flex;align-items:center;gap:6px;margin-top:6px;padding:0 4px 0 10px;border:1px dashed #e2ddd0;border-radius:8px}
.suggest-other input{flex:1;min-width:0;height:32px;border:none;outline:none;background:none;font-size:12px;color:var(--ink)}
.suggest-other:focus-within{border-style:solid;border-color:var(--primary)}
.suggest-other button{font-size:11.5px;flex-shrink:0}
.suggest-list li.off .suggest-row{color:var(--muted)}
.suggest-icon{width:26px;height:26px;display:grid;place-items:center;border-radius:7px;color:var(--subtle)}.suggest-icon:hover:not(:disabled){background:var(--quiet);color:var(--ink)}
.suggest-icon svg{transition:transform .15s}.suggest-icon.open svg{transform:rotate(180deg)}
.suggest-detail{grid-column:1/-1;margin:0 0 6px;padding:7px 9px;border-radius:7px;background:var(--quiet);font-size:11.5px;line-height:1.7;color:#5f5a52}
.suggest-apply{width:100%;margin-top:8px}
.retry-hint{margin-top:11px}.retry-hint>span{display:block;font-size:11px;color:var(--muted);margin-bottom:6px}.retry-hint button{width:100%;text-align:left;white-space:normal;line-height:1.6;font-size:12px;padding:8px 10px}
.result-assumption,.deleted-note{margin-top:8px;font-size:11px;color:var(--muted)}
.scope-note{display:flex;align-items:flex-start;gap:5px;margin-top:8px;font-size:11px;line-height:1.6;color:#906323}.scope-note svg{flex-shrink:0;margin-top:3px}.deleted-note{display:flex;align-items:center;gap:5px}.clarification button{margin:8px 6px 0 0;white-space:normal;text-align:left;line-height:1.5}
</style>
