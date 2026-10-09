<script setup>
import { computed } from 'vue'
import { Check, Undo2, ChevronDown, AlertCircle } from 'lucide-vue-next'
const props = defineProps({ result: Object, canUndo: Boolean, locked: Boolean, checking: Boolean })
defineEmits(['undo', 'choose', 'apply', 'discuss', 'rephrase'])
const report = computed(() => props.result?.report)
const discussion = computed(() => props.result?.discussion)
// A question is already rendered by its own block; everything else needs a headline.
const headline = computed(() => report.value?.summary || discussion.value?.answer || (props.result?.clarification ? '' : props.result?.content || ''))
const statuses = { completed: '已完成', partial: '部分完成', unprocessed: '未处理' }
</script>
<template>
  <div class="result-card">
    <p v-if="headline" class="result-summary">{{ headline }}</p>
    <div v-if="result.clarification" class="clarification"><p>{{ result.clarification.question }}</p><button v-for="option in result.clarification.options" :key="option" class="outline" :disabled="locked" @click="$emit('choose', { option, clarification: result.clarification })">{{ option }}</button></div>
    <ol v-if="discussion?.suggestions?.length" class="suggestion-list"><li v-for="(suggestion, i) in discussion.suggestions" :key="i"><b>{{ suggestion.label }}</b><small>{{ suggestion.instruction }}</small><div class="suggestion-actions"><button class="outline" :disabled="locked" @click="$emit('apply', { suggestion, discussion })">按此建议修改</button><button class="text-button" :disabled="locked" @click="$emit('discuss', suggestion)">继续聊这条</button></div></li></ol>
    <ol v-if="report?.annotations?.length" class="opinion-results"><li v-for="item in report.annotations" :key="item.id" :class="item.status"><span>{{ item.number }}</span><div><b>{{ item.note || item.name }}</b><small>{{ statuses[item.status] }}{{ item.reason ? '：' + item.reason : '' }}</small></div></li></ol>
    <p v-for="assumption in report?.assumptions || []" :key="assumption" class="result-assumption">需要确认：{{ assumption }}</p>
    <p v-if="report?.out_of_scope" class="scope-note"><AlertCircle :size="12" />还改到了你圈定范围之外的 {{ report.out_of_scope.lines }} 行（{{ report.out_of_scope.places.join('、') }}{{ report.out_of_scope.more ? ' 等' : '' }}）。已经保存，请检查这些地方，不对就撤销这次修改</p>
    <div v-if="report?.retry_hint" class="retry-hint"><span>换种说法试试</span><button class="outline" :disabled="locked" @click="$emit('rephrase', report.retry_hint)">{{ report.retry_hint }}</button></div>
    <div v-if="result.changed" class="change-summary"><Check :size="14" /><strong>{{ checking ? '检查中' : '已保存' }} · 改了 {{ result.change_count || result.diff?.hunks?.length || 1 }} 处</strong><span v-if="result.diff">+{{ result.diff.additions }} / −{{ result.diff.deletions }}</span></div>
    <div v-if="result.changed" class="result-actions"><details v-if="result.diff"><summary>查看改动<ChevronDown :size="13" /></summary><div class="diff-view"><div v-for="(hunk, i) in result.diff.hunks" :key="i" class="diff-hunk"><small>原 {{ hunk.old_start }} 行 / 新 {{ hunk.new_start }} 行</small><pre><span v-for="(line, j) in hunk.lines" :key="j" :class="line.kind">{{ line.kind === 'added' ? '+' : line.kind === 'removed' ? '−' : ' ' }} {{ line.text }}{{ '\n' }}</span></pre></div><p v-if="result.diff.truncated" class="field-hint">改动较多，这里展示前 400 行。</p></div></details><button v-if="!checking" class="text-button" :disabled="locked || !canUndo" :title="canUndo ? '撤销这次修改' : '先撤销后续修改，才能撤销这一项'" @click="$emit('undo', result.change_id)"><Undo2 :size="13" />撤销这次修改</button></div>
    <p v-for="target in (result.targets || []).filter(t => t.deleted)" :key="target.selector" class="deleted-note"><AlertCircle :size="12" />已删除{{ target.name || '选中元素' }}</p>
  </div>
</template>
<style scoped>
/* 回复正文直接流在背景上；只有 diff、建议这类块才有自己的容器。 */
.result-card{font-size:12px;line-height:1.7}
.result-summary{font-size:13px;line-height:1.85;color:var(--ink);white-space:pre-wrap;overflow-wrap:anywhere}
.change-summary{display:flex;align-items:center;gap:6px;color:var(--success);font-size:11px;margin-top:10px}.change-summary strong{font-weight:500}.change-summary>span{margin-left:auto;color:var(--muted);font-variant-numeric:tabular-nums}
.result-actions{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-top:9px;flex-wrap:wrap}.result-actions>details{min-width:0;width:100%}.result-actions summary{list-style:none;display:flex;gap:5px;align-items:center;color:var(--muted);cursor:pointer;font-size:12px}.result-actions summary::-webkit-details-marker{display:none}
.diff-view{overflow:auto;max-height:320px;margin-top:9px;border:1px solid var(--line);border-radius:5px;background:#fbfafa}.diff-hunk small{display:block;padding:5px 8px;background:#f1eeed;color:var(--muted);font-size:10px}.diff-hunk pre{font:11px/1.7 ui-monospace,SFMono-Regular,monospace;margin:0;min-width:100%;width:max-content}.diff-hunk pre span{display:block;padding:0 8px;white-space:pre}.diff-hunk .added{background:#e3efe1;color:#2f6b3d}.diff-hunk .removed{background:#f7e4e0;color:#9c4034}.diff-hunk .context{color:#837a76}
.opinion-results{list-style:none;padding:0;display:flex;flex-direction:column;gap:9px;margin:12px 0}.opinion-results li{display:flex;gap:7px}.opinion-results li>span{border-radius:50%;background:var(--quiet);font-size:10px;width:18px;height:18px;text-align:center;flex-shrink:0}.opinion-results b{font-weight:500}.opinion-results small{display:block;color:var(--muted);font-size:11px}.opinion-results .completed small{color:var(--success)}.opinion-results .partial small,.opinion-results .unprocessed small{color:#906323}
.suggestion-list{list-style:none;padding:0;margin:12px 0 0;display:flex;flex-direction:column;gap:10px}.suggestion-list li{border:1px solid var(--line);border-radius:6px;padding:9px 10px;background:#fbfafa}.suggestion-list b{display:block;font-weight:500}.suggestion-list small{display:block;color:var(--muted);font-size:11px;margin-top:3px}.suggestion-actions{display:flex;align-items:center;gap:10px;margin-top:8px;flex-wrap:wrap}.suggestion-actions button{font-size:11px;padding:5px 8px;min-height:28px}
.retry-hint{margin-top:11px}.retry-hint>span{display:block;font-size:11px;color:var(--muted);margin-bottom:6px}.retry-hint button{width:100%;text-align:left;white-space:normal;line-height:1.6;font-size:12px;padding:8px 10px}
.result-assumption,.deleted-note{margin-top:8px;font-size:11px;color:var(--muted)}
.scope-note{display:flex;align-items:flex-start;gap:5px;margin-top:8px;font-size:11px;line-height:1.6;color:#906323}.scope-note svg{flex-shrink:0;margin-top:3px}.deleted-note{display:flex;align-items:center;gap:5px}.clarification button{margin:8px 6px 0 0;white-space:normal;text-align:left;line-height:1.5}
</style>
