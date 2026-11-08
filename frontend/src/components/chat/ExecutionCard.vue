<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Check, AlertCircle, LoaderCircle, ChevronDown, Lightbulb } from 'lucide-vue-next'
import { brief, iconOf } from '../../lib/toolIcons.js'
import { prose } from '../../lib/prose.js'
import ResultCard from './ResultCard.vue'
import DiffLines from './DiffLines.vue'
const props = defineProps({ run: Object, locked: Boolean })
defineEmits(['retry', 'settings', 'select', 'repair', 'dismiss', 'fill', 'stop', 'point'])
const now = ref(Date.now()); let timer
onMounted(() => { timer = setInterval(() => now.value = Date.now(), 1000) })
onUnmounted(() => clearInterval(timer))
const elapsed = computed(() => Math.max(0, Math.floor(((props.run.finished || now.value) - props.run.started) / 1000)))
const clock = computed(() => `${String(Math.floor(elapsed.value / 60)).padStart(2, '0')}:${String(elapsed.value % 60).padStart(2, '0')}`)
// 出错时下一步怎么办，说成一句人话（参照 Claude：说清发生了什么、保留了什么、点哪个按钮）
const HINTS = { model_account: '', validation: '改出来的页面没通过检查，页面还是上一版；可以让 AI 照着报错修一遍。',
  patch_target: '要改的那个元素找不到了（页面可能已经变了）：在页面上重新点一下要改的地方再发。',
  tool_rejected: '没指位置时 AI 只能在代码里猜：在页面上点一下要改的地方（点了没反应的，切到交互把它点一遍），再发送。', stalled: '没指位置时 AI 只能在代码里猜：在页面上点一下要改的地方，再发送。',
  output_limit: '一次要改的太多：把要求放回输入框，删成一小步再发。', invalid_arguments: '一次要改的太多：把要求放回输入框，删成一小步再发。', iterations: '一次要做的太多，轮次用完了：把剩下的拆成一小步再发。',
  stopped: '已经改好的部分会保留并检查，不想要可以撤销。', busy: '模型服务这会儿忙，已经自动重试过几次；稍等一下再重试。' }
// 报错本身已经说了怎么办的（模型账户那句）不再重复一遍
const errorHint = computed(() => { const code = props.run.error?.code; return code in HINTS ? HINTS[code] : props.run.error ? '可能是网络或模型服务抖了一下，重试一般就好。' : '' })
const busy = computed(() => ['running', 'checking'].includes(props.run.status))
// 每一步的结果默认折叠。全摊开是 14 行灰字糊成一片，真正要看的（它在想什么）反而被埋了。
// 想看某一步到底拿到什么，点那一行展开。
const opened = ref(new Set())
function toggle(id) { opened.value.has(id) ? opened.value.delete(id) : opened.value.add(id); opened.value = new Set(opened.value) }
const discussing = computed(() => props.run.intent === 'discuss')
// 参照 Claude：AI 边做边说的话（旁白）照常铺开；读代码、查找这些工具步骤收成「N 步」，只露正在跑的那一步
// 工具一步一行（像 Claude 显示工具调用）：图标说明干的是哪类事，后面一小截灰字是它拿到了什么，点开看全；
// 步数多了只露最近 3 步，前面的收在标题右边的「N 步」里
const showSteps = ref(false)
// 交回答、汇报这几步是收尾的手续，不算「在做事」，不列出来（回看里也不存）
const CLERICAL = new Set(['answer_user', 'report_result', 'ask_user'])
const tools = computed(() => props.run.steps.filter(s => !['note', 'live', 'think', 'aside'].includes(s.kind) && !CLERICAL.has(s.tool)))
const toolCount = computed(() => tools.value.length)
const recent = computed(() => new Set(tools.value.slice(-3).map(s => s.id)))
// 有计划时标题旁边一直写着做到第几步（卡片长了计划列表翻上去也看得到）
const planNow = computed(() => { const p = props.run.plan || [], i = p.findIndex(x => x.status === 'active'); return busy.value && i >= 0 ? { at: i + 1, title: p[i].title } : null })
// 报错只露第一句（后面那些是写给 AI 的「下一次只放一条 replace_source_text…」），点开看全
const errShort = e => { const t = String(e || ''); const cut = t.search(/[。\n]/); return cut > 0 && cut < t.length - 1 ? t.slice(0, Math.min(cut, 80)) + '…' : t.slice(0, 120) }
// 思考：还在想的露最后两句，想完了「想了 N 秒」
const thinkingNow = step => !step.ended && busy.value
const thinkTail = step => { const lines = String(step.text || '').trim().split(/\n+/); return lines.slice(-2).join(' ').slice(-120) }
const thinkLabel = step => thinkingNow(step) ? ['思考中…'] : ['想了 {0} 秒', [Math.max(1, Math.round(((step.ended || props.run.finished || now.value) - step.started) / 1000))]]
const shown = step => !CLERICAL.has(step.tool) && (['note', 'live', 'think', 'aside'].includes(step.kind) || showSteps.value || recent.value.has(step.id) || step.state === 'running' || step.state === 'error')
// 以前不管干什么都写"修改中"：问一句"这里美观吗"也是修改中，还在读代码也是修改中。
// 标题按当下实际在做的事说话——讨论就说在看，动过文件才叫修改。
const heading = computed(() => {
  if (props.run.status === 'stopped') return '已停止'
  if (props.run.status === 'checking') return '检查中'
  if (!busy.value) return discussing.value ? '这次回复未完成' : '这次修改未完成'
  if (props.run.intent === 'architecture') {   // 架构模式分几步：标题跟着后台报的进度走
    const label = props.run.label || ''
    return /梳理业务/.test(label) ? '正在梳理业务' : /页面清单/.test(label) && !/展开/.test(label) ? '正在定页面清单' : /展开页面树/.test(label) ? '正在画架构' : /自动检查/.test(label) ? '正在检查架构'
      : /改页面树/.test(label) ? '正在改架构' : '正在看架构'
  }
  if (discussing.value) return props.run.steps.length ? '正在看这个页面' : '思考中'
  return props.run.editing ? '修改中' : '正在读页面'
})
</script>
<template>
  <section class="execution-card" :class="{ failed: run.status === 'failed' }" :aria-label="discussing ? $t('本次回复进度') : $t('本次修改进度')">
    <header><LoaderCircle v-if="busy" :size="14" class="spin" /><AlertCircle v-else :size="14" /><strong>{{ $t(heading) }}</strong><span v-if="planNow" class="plan-now" :title="planNow.title">{{ planNow.at }}/{{ run.plan.length }} · {{ planNow.title }}</span><span class="grow"></span><button v-if="toolCount > 3" type="button" class="steps-toggle" :aria-expanded="showSteps" @click="showSteps = !showSteps">{{ $t('{0} 步', [toolCount]) }}<ChevronDown :size="12" :class="{ open: showSteps }" /></button><time>{{ $t(clock) }}</time></header>
    <div v-if="run.brief" class="plan-brief"><b>{{ $t('业务梳理') }}</b><p>{{ run.brief }}</p></div>
    <ol v-if="run.plan?.length" class="plan-list" :aria-label="discussing ? $t('分析步骤') : $t('修改计划')"><li v-for="(step, i) in run.plan" :key="i" :class="step.status"><Check v-if="step.status === 'done'" :size="12" /><LoaderCircle v-else-if="step.status === 'active'" :size="12" class="spin" /><i v-else></i>{{ step.title }}</li></ol>

    <ol v-if="run.intent === 'architecture' && run.steps.some(x => x.kind === 'think')" class="think-first"><template v-for="step in run.steps.filter(x => x.kind === 'think')" :key="step.id"><li v-if="step.kind === 'think'" class="think" :class="{ running: thinkingNow(step) }"><LoaderCircle v-if="thinkingNow(step)" :size="13" class="spin" /><Lightbulb v-else :size="13" />
      <div><button type="button" class="step-head" :aria-expanded="opened.has(step.id)" @click="toggle(step.id)">{{ $t(...thinkLabel(step)) }}<ChevronDown :size="12" :class="{ open: opened.has(step.id) }" /></button><small v-if="opened.has(step.id)" class="think-text">{{ step.text.trim() }}</small><small v-else-if="thinkingNow(step) && thinkTail(step)" class="think-text tail">{{ thinkTail(step) }}</small></div></li>
      <li v-else v-show="shown(step)" :class="[step.kind === 'note' ? 'note' : step.state, step.kind === 'live' ? 'live' : step.kind === 'note' ? '' : 'tool', { foldable: step.kind !== 'note' && step.detail }]">
      <template v-if="step.kind !== 'note'"><LoaderCircle v-if="step.state === 'running'" :size="13" class="spin" /><AlertCircle v-else-if="step.state === 'error'" :size="13" /><Check v-else-if="step.kind === 'live'" :size="13" /><component :is="iconOf(step)" v-else :size="13" class="tool-icon" /></template>
      <div><button v-if="step.kind !== 'note' && (step.detail || step.diff)" type="button" class="step-head" :aria-expanded="opened.has(step.id)" @click="toggle(step.id)">{{ $t(step.label) }}<em v-if="step.diff" class="diffstat"><i class="add">+{{ step.diff.additions }}</i><i class="del">−{{ step.diff.deletions }}</i></em><em v-else-if="!opened.has(step.id) && brief(step)" class="step-brief">{{ brief(step) }}</em><ChevronDown :size="12" :class="{ open: opened.has(step.id) }" /></button><div v-else-if="step.kind === 'note'" class="prose note-text" v-html="prose(step.label)"></div><span v-else>{{ $t(step.label) }}</span><small v-if="step.error" class="step-error" :class="{ full: opened.has(step.id + ':e') }" @click="toggle(step.id + ':e')">{{ opened.has(step.id + ':e') ? $t(step.error) : errShort(step.error) }}<em v-if="busy && step.state === 'error'">{{ $t('AI 会接着修') }}</em></small><DiffLines v-else-if="step.diff && opened.has(step.id)" :diff="step.diff" /><small v-else-if="step.detail && opened.has(step.id)" class="step-detail">{{ $t(step.detail) }}</small></div></li></template></ol>
    <div v-if="run.intent === 'architecture' && run.streamText && !run.result" class="stream-text lead"><div class="prose" v-html="prose(run.streamText)"></div><span v-if="!run.steps.some(s => s.kind === 'live')" class="caret"></span></div>
    <ol aria-live="polite"><template v-for="step in run.intent === 'architecture' ? run.steps.filter(x => x.kind !== 'think') : run.steps" :key="step.id"><li v-if="step.kind === 'aside'" class="aside"><div><p>{{ step.label }}</p><small>{{ $t(step.state === 'taken' ? '已交给 AI，接着按这个做' : step.state === 'queued' ? '这一轮插不进去，跑完接着发' : '下一步交给 AI') }}</small></div></li><li v-else-if="step.kind === 'think'" class="think" :class="{ running: thinkingNow(step) }"><LoaderCircle v-if="thinkingNow(step)" :size="13" class="spin" /><Lightbulb v-else :size="13" />
      <div><button type="button" class="step-head" :aria-expanded="opened.has(step.id)" @click="toggle(step.id)">{{ $t(...thinkLabel(step)) }}<ChevronDown :size="12" :class="{ open: opened.has(step.id) }" /></button><small v-if="opened.has(step.id)" class="think-text">{{ step.text.trim() }}</small><small v-else-if="thinkingNow(step) && thinkTail(step)" class="think-text tail">{{ thinkTail(step) }}</small></div></li>
      <li v-else v-show="shown(step)" :class="[step.kind === 'note' ? 'note' : step.state, step.kind === 'live' ? 'live' : step.kind === 'note' ? '' : 'tool', { foldable: step.kind !== 'note' && step.detail }]">
      <template v-if="step.kind !== 'note'"><LoaderCircle v-if="step.state === 'running'" :size="13" class="spin" /><AlertCircle v-else-if="step.state === 'error'" :size="13" /><Check v-else-if="step.kind === 'live'" :size="13" /><component :is="iconOf(step)" v-else :size="13" class="tool-icon" /></template>
      <div><button v-if="step.kind !== 'note' && (step.detail || step.diff)" type="button" class="step-head" :aria-expanded="opened.has(step.id)" @click="toggle(step.id)">{{ $t(step.label) }}<em v-if="step.diff" class="diffstat"><i class="add">+{{ step.diff.additions }}</i><i class="del">−{{ step.diff.deletions }}</i></em><em v-else-if="!opened.has(step.id) && brief(step)" class="step-brief">{{ brief(step) }}</em><ChevronDown :size="12" :class="{ open: opened.has(step.id) }" /></button><div v-else-if="step.kind === 'note'" class="prose note-text" v-html="prose(step.label)"></div><span v-else>{{ $t(step.label) }}</span><small v-if="step.error" class="step-error" :class="{ full: opened.has(step.id + ':e') }" @click="toggle(step.id + ':e')">{{ opened.has(step.id + ':e') ? $t(step.error) : errShort(step.error) }}<em v-if="busy && step.state === 'error'">{{ $t('AI 会接着修') }}</em></small><DiffLines v-else-if="step.diff && opened.has(step.id)" :diff="step.diff" /><small v-else-if="step.detail && opened.has(step.id)" class="step-detail">{{ $t(step.detail) }}</small></div></li></template></ol>
    <p v-if="run.intent !== 'architecture' && run.streamText && !run.result" class="stream-text">{{ run.streamText }}<span class="caret"></span></p>
    <p v-else-if="busy && !run.steps.some(s => s.state === 'running' || (s.kind === 'think' && !s.ended))" class="model-wait">{{ $t(run.label || '理解需求中') }}</p>
    <ResultCard v-if="run.status === 'checking' && run.result" :result="run.result" checking />
    <div v-if="run.error" class="run-error" role="alert">
      <div class="run-error-head"><AlertCircle :size="14" /><b>{{ $t(run.error.message) }}</b></div>
      <p v-if="errorHint" class="run-error-hint">{{ $t(errorHint) }}</p>
      <details v-if="run.error.detail && run.error.detail !== run.error.message"><summary>{{ $t('查看详情') }}</summary><p>{{ $t(run.error.detail) }}</p></details>
      <div class="run-error-actions">
        <button v-if="run.error.code === 'model_account'" class="primary" @click="$emit('settings')">{{ $t('打开设置') }}</button>
        <button v-else-if="run.error.code === 'validation'" class="primary" :disabled="locked" @click="$emit('repair')">{{ $t('让 AI 修复') }}</button>
        <button v-else-if="run.error.code === 'patch_target'" class="primary" :disabled="locked" @click="$emit('select')">{{ $t('重新点选后重试') }}</button>
        <button v-else-if="['tool_rejected','stalled'].includes(run.error.code)" class="primary" :disabled="locked" @click="$emit('point')">{{ $t('指给它看') }}</button>
        <button v-else-if="['output_limit','invalid_arguments','iterations'].includes(run.error.code)" class="primary" :disabled="locked" @click="$emit('fill')">{{ $t('拆小一点再发') }}</button>
        <button v-else-if="run.error.code !== 'stopped'" class="primary" :disabled="locked" @click="$emit('retry')">{{ $t('重试') }}</button>
        <button class="quiet" @click="$emit('dismiss')">{{ run.error.code === 'validation' ? $t('放弃') : $t('关闭') }}</button>
      </div>
    </div>
  </section>
</template>
<style scoped>
.execution-card{margin:4px 0 22px;font-size:12.5px;line-height:1.65}
.execution-card header{position:sticky;top:-16px;z-index:3;display:flex;gap:7px;align-items:center;padding:6px 0;background:var(--shell);color:var(--muted)}
.plan-now{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0 7px;border-radius:var(--r-tag);background:var(--quiet);font-size:11.5px;color:var(--muted)}
.step-error{cursor:pointer}.step-error em{margin-left:6px;font-style:normal;color:var(--muted)}.execution-card header>svg{color:var(--primary)}
.execution-card.failed header>svg{color:#a24b37}
.execution-card strong{font-size:12.5px;font-weight:500;color:var(--ink)}
.execution-card time{color:var(--subtle);font-size:11.5px;font-variant-numeric:tabular-nums}
.steps-toggle{gap:3px;padding:1px 6px 1px 8px;border-radius:var(--r-tag);font-size:11.5px;color:var(--muted)}.steps-toggle:hover{background:var(--quiet);color:var(--ink)}
.steps-toggle svg{transition:transform .15s}.steps-toggle svg.open{transform:rotate(180deg)}
.execution-card .grow{flex:1}
.execution-card ol{list-style:none;margin:8px 0 0 6px;padding:0 0 0 13px;border-left:1.5px solid var(--line);display:flex;flex-direction:column;gap:6px}
.execution-card ol:empty{display:none}
.execution-card li{display:flex;gap:7px;color:var(--muted)}.execution-card li svg{margin-top:3px;flex-shrink:0}.execution-card li small{display:block;font-size:11.5px;color:#a24b37;overflow-wrap:anywhere}
.execution-card li.tool .tool-icon{color:var(--subtle)}.execution-card li.done.tool{color:var(--muted)}
.execution-card li.think{color:var(--muted)}.execution-card li.think svg{color:var(--subtle)}.execution-card li.think.running svg{color:var(--primary)}
.think-text{display:block;margin-top:3px;font-size:11.5px!important;line-height:1.7;color:var(--subtle)!important;white-space:pre-wrap;max-height:240px;overflow:auto}.think-text.tail{white-space:normal;max-height:none}
.diffstat{display:inline-flex;gap:4px;margin-left:6px;font-style:normal;font-size:11.5px;font-variant-numeric:tabular-nums}.diffstat .add{font-style:normal;color:#2f7d45}.diffstat .del{font-style:normal;color:#b0473a}
.execution-card li.aside{justify-content:flex-end;margin:4px 0}.execution-card li.aside>div{flex:none;max-width:88%;text-align:right}
.execution-card li.aside p{display:inline-block;margin:0;padding:6px 12px;border-radius:14px;background:var(--canvas);color:var(--ink);font-size:13px;text-align:left;white-space:pre-wrap}
.execution-card li.aside small{display:block;margin-top:2px;font-size:11px!important;color:var(--subtle)!important}
.step-brief{margin-left:6px;font-style:normal;font-size:11.5px;color:var(--subtle);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.execution-card li small.step-detail{color:var(--muted);margin-top:3px;line-height:1.7}
.step-head{display:flex;align-items:center;gap:4px;max-width:100%;min-width:0;padding:0;min-height:0;background:none;border:0;color:inherit;font:inherit;text-align:left;cursor:pointer}
.step-head svg{color:#bcaea8;flex-shrink:0;transition:transform .15s}
.step-head svg.open{transform:rotate(180deg)}
.execution-card li.foldable:hover .step-head{color:var(--ink)}.execution-card li.error{color:#a24b37}.execution-card li.running{color:var(--ink)}.execution-card li.running svg{color:var(--primary)}
.execution-card li>div{min-width:0;flex:1}.execution-card li.note{color:var(--ink);font-size:13px;line-height:1.75;margin:2px 0}
.plan-list{margin-top:10px!important}
.plan-brief{margin-top:10px;padding:8px 11px;border-radius:var(--r-item);background:var(--quiet);font-size:12px;line-height:1.7;color:#5f5a52}.plan-brief b{display:block;font-size:11.5px;color:var(--ink);margin-bottom:2px}.plan-brief p{margin:0;white-space:pre-wrap}
.plan-list li{display:flex;align-items:center;gap:7px;color:var(--muted)}
.plan-list li>i{width:12px;height:12px;border:1.5px solid #d6d1c4;border-radius:50%;flex-shrink:0}
.plan-list li.active{color:var(--ink);font-weight:500}
.plan-list li.done{color:var(--subtle);text-decoration:line-through;text-decoration-color:#a3a29c66}.plan-list li.done svg{color:var(--success)}
.note-text :deep(p),.note-text p{margin:0 0 6px}.stream-text.lead{margin:8px 0 2px;white-space:normal;font-size:14px;line-height:1.7}.stream-text{margin-top:10px;font-size:13.5px;line-height:1.8;color:var(--ink);white-space:pre-wrap;overflow-wrap:anywhere}
.caret{display:inline-block;width:7px;height:7px;margin-left:4px;border-radius:50%;vertical-align:1px;background:var(--primary);animation:blink 1.1s ease-in-out infinite}
@keyframes blink{50%{opacity:.25}}
@media (prefers-reduced-motion: reduce){.caret{animation:none}}
.model-wait{font-size:12px;color:var(--subtle);margin:6px 0 0 21px}
.run-error{margin-top:8px;padding:10px 12px 12px;border:1px solid #f0d9d2;border-radius:var(--r-card);background:#fdf5f2;overflow-wrap:anywhere;color:#7d3526}
.run-error-head{display:flex;align-items:flex-start;gap:7px;font-size:13px;line-height:1.6}.run-error-head svg{flex:none;margin-top:3px;color:#b0473a}.run-error-head b{font-weight:600}
.run-error-hint{margin:4px 0 0 21px;font-size:12px;line-height:1.7;color:#8a4a3c}
.run-error details{margin:6px 0 0 21px;font-size:11.5px;color:var(--muted)}.run-error summary{cursor:pointer}
.run-error-actions{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 0 21px}.run-error-actions button{font-size:12px;padding:5px 12px;min-height:30px;border-radius:var(--r-item)}
</style>
