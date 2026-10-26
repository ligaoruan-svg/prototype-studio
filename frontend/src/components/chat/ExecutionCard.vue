<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Check, AlertCircle, LoaderCircle, ChevronDown } from 'lucide-vue-next'
import ResultCard from './ResultCard.vue'
const props = defineProps({ run: Object, locked: Boolean })
defineEmits(['retry', 'settings', 'select', 'repair', 'dismiss', 'fill', 'stop', 'point'])
const now = ref(Date.now()); let timer
onMounted(() => { timer = setInterval(() => now.value = Date.now(), 1000) })
onUnmounted(() => clearInterval(timer))
const elapsed = computed(() => Math.max(0, Math.floor(((props.run.finished || now.value) - props.run.started) / 1000)))
const clock = computed(() => `${String(Math.floor(elapsed.value / 60)).padStart(2, '0')}:${String(elapsed.value % 60).padStart(2, '0')}`)
const busy = computed(() => ['running', 'checking'].includes(props.run.status))
// 每一步的结果默认折叠。全摊开是 14 行灰字糊成一片，真正要看的（它在想什么）反而被埋了。
// 想看某一步到底拿到什么，点那一行展开。
const opened = ref(new Set())
function toggle(id) { opened.value.has(id) ? opened.value.delete(id) : opened.value.add(id); opened.value = new Set(opened.value) }
const discussing = computed(() => props.run.intent === 'discuss')
// 参照 Claude：AI 边做边说的话（旁白）照常铺开；读代码、查找这些工具步骤收成「N 步」，只露正在跑的那一步
const showSteps = ref(false)
const toolCount = computed(() => props.run.steps.filter(s => s.kind !== 'note').length)
// 以前不管干什么都写"修改中"：问一句"这里美观吗"也是修改中，还在读代码也是修改中。
// 标题按当下实际在做的事说话——讨论就说在看，动过文件才叫修改。
const heading = computed(() => {
  if (props.run.status === 'stopped') return '已停止'
  if (props.run.status === 'checking') return '检查中'
  if (!busy.value) return discussing.value ? '这次回复未完成' : '这次修改未完成'
  if (discussing.value) return props.run.steps.length ? '正在看这个页面' : '思考中'
  return props.run.editing ? '修改中' : '正在读页面'
})
</script>
<template>
  <section class="execution-card" :class="{ failed: run.status === 'failed' }" :aria-label="discussing ? $t('本次回复进度') : $t('本次修改进度')">
    <header><LoaderCircle v-if="busy" :size="14" class="spin" /><AlertCircle v-else :size="14" /><strong>{{ $t(heading) }}</strong><span class="grow"></span><button v-if="toolCount" type="button" class="steps-toggle" :aria-expanded="showSteps" @click="showSteps = !showSteps">{{ $t('{0} 步', [toolCount]) }}<ChevronDown :size="12" :class="{ open: showSteps }" /></button><time>{{ $t(clock) }}</time></header>
    <div v-if="run.brief" class="plan-brief"><b>{{ $t('业务梳理') }}</b><p>{{ run.brief }}</p></div>
    <ol v-if="run.plan?.length" class="plan-list" :aria-label="discussing ? $t('分析步骤') : $t('修改计划')"><li v-for="(step, i) in run.plan" :key="i" :class="step.status"><Check v-if="step.status === 'done'" :size="12" /><LoaderCircle v-else-if="step.status === 'active'" :size="12" class="spin" /><i v-else></i>{{ step.title }}</li></ol>
    <ol aria-live="polite"><li v-for="step in run.steps" v-show="step.kind === 'note' || showSteps || step.state === 'running' || step.state === 'error'" :key="step.id" :class="[step.kind === 'note' ? 'note' : step.state, { foldable: step.kind !== 'note' && step.detail }]"><template v-if="step.kind !== 'note'"><Check v-if="step.state === 'done'" :size="13" /><AlertCircle v-else-if="step.state === 'error'" :size="13" /><LoaderCircle v-else :size="13" class="spin" /></template><div><button v-if="step.kind !== 'note' && step.detail" type="button" class="step-head" :aria-expanded="opened.has(step.id)" @click="toggle(step.id)">{{ $t(step.label) }}<ChevronDown :size="12" :class="{ open: opened.has(step.id) }" /></button><span v-else>{{ $t(step.label) }}</span><small v-if="step.error">{{ $t(step.error) }}</small><small v-else-if="step.detail && opened.has(step.id)" class="step-detail">{{ $t(step.detail) }}</small></div></li></ol>
    <p v-if="run.streamText && !run.result" class="stream-text">{{ run.streamText }}<span class="caret"></span></p>
    <p v-else-if="busy && !run.steps.some(s => s.state === 'running')" class="model-wait">{{ $t(run.label || '理解需求中') }}</p>
    <ResultCard v-if="run.status === 'checking' && run.result" :result="run.result" checking />
    <div v-if="run.error" class="run-error"><p>{{ $t(run.error.message) }}</p><details v-if="run.error.detail && run.error.detail !== run.error.message"><summary>{{ $t('查看详情') }}</summary><p>{{ $t(run.error.detail) }}</p></details><div class="run-error-actions"><button v-if="run.error.code === 'model_account'" class="outline" @click="$emit('settings')">{{ $t('打开设置') }}</button><button v-else-if="run.error.code === 'validation'" class="outline" :disabled="locked" @click="$emit('repair')">{{ $t('让 AI 修复') }}</button><button v-else-if="run.error.code === 'patch_target'" class="outline" :disabled="locked" @click="$emit('select')">{{ $t('重新点选后重试') }}</button><button v-else-if="['tool_rejected','stalled'].includes(run.error.code)" class="outline" :disabled="locked" :title="$t('没指位置时 AI 只能在源码里猜：在页面上点一下要改的地方（点了没反应的，切到交互把它点一遍），再发送')" @click="$emit('point')">{{ $t('指给它看') }}</button><button v-else-if="['output_limit','invalid_arguments','iterations'].includes(run.error.code)" class="outline" :disabled="locked" :title="$t('一次要改的太多：把要求放回输入框，删成一小步再发')" @click="$emit('fill')">{{ $t('拆小一点再发') }}</button><button v-else class="outline" :disabled="locked" @click="$emit('retry')">{{ $t('重试') }}</button><button class="quiet" @click="$emit('dismiss')">{{ run.error.code === 'validation' ? $t('放弃') : $t('关闭') }}</button></div></div>
  </section>
</template>
<style scoped>
.execution-card{margin:4px 0 22px;font-size:12.5px;line-height:1.65}
.execution-card header{display:flex;gap:7px;align-items:center;color:var(--muted)}.execution-card header>svg{color:var(--primary)}
.execution-card.failed header>svg{color:#a24b37}
.execution-card strong{font-size:12.5px;font-weight:500;color:var(--ink)}
.execution-card time{color:var(--subtle);font-size:11.5px;font-variant-numeric:tabular-nums}
.steps-toggle{gap:3px;padding:1px 6px 1px 8px;border-radius:8px;font-size:11.5px;color:var(--muted)}.steps-toggle:hover{background:var(--quiet);color:var(--ink)}
.steps-toggle svg{transition:transform .15s}.steps-toggle svg.open{transform:rotate(180deg)}
.execution-card .grow{flex:1}
.execution-card ol{list-style:none;margin:8px 0 0 6px;padding:0 0 0 13px;border-left:1.5px solid var(--line);display:flex;flex-direction:column;gap:6px}
.execution-card ol:empty{display:none}
.execution-card li{display:flex;gap:7px;color:var(--muted)}.execution-card li svg{margin-top:3px;flex-shrink:0}.execution-card li small{display:block;font-size:11.5px;color:#a24b37;overflow-wrap:anywhere}
.execution-card li small.step-detail{color:var(--muted);margin-top:3px;line-height:1.7}
.step-head{display:flex;align-items:center;gap:4px;padding:0;min-height:0;background:none;border:0;color:inherit;font:inherit;text-align:left;cursor:pointer}
.step-head svg{color:#bcaea8;flex-shrink:0;transition:transform .15s}
.step-head svg.open{transform:rotate(180deg)}
.execution-card li.foldable:hover .step-head{color:var(--ink)}.execution-card li.error{color:#a24b37}.execution-card li.running{color:var(--ink)}.execution-card li.running svg{color:var(--primary)}
.execution-card li>div{min-width:0;flex:1}.execution-card li.note{color:var(--ink);font-size:13px;line-height:1.75;margin:2px 0}
.plan-list{margin-top:10px!important}
.plan-brief{margin-top:10px;padding:8px 11px;border-radius:10px;background:var(--quiet);font-size:12px;line-height:1.7;color:#5f5a52}.plan-brief b{display:block;font-size:11.5px;color:var(--ink);margin-bottom:2px}.plan-brief p{margin:0;white-space:pre-wrap}
.plan-list li{display:flex;align-items:center;gap:7px;color:var(--muted)}
.plan-list li>i{width:12px;height:12px;border:1.5px solid #d6d1c4;border-radius:50%;flex-shrink:0}
.plan-list li.active{color:var(--ink);font-weight:500}
.plan-list li.done{color:var(--subtle);text-decoration:line-through;text-decoration-color:#a3a29c66}.plan-list li.done svg{color:var(--success)}
.stream-text{margin-top:10px;font-size:13.5px;line-height:1.8;color:var(--ink);white-space:pre-wrap;overflow-wrap:anywhere}
.caret{display:inline-block;width:7px;height:7px;margin-left:4px;border-radius:50%;vertical-align:1px;background:var(--primary);animation:blink 1.1s ease-in-out infinite}
@keyframes blink{50%{opacity:.25}}
@media (prefers-reduced-motion: reduce){.caret{animation:none}}
.model-wait{font-size:12px;color:var(--subtle);margin:6px 0 0 21px}
.run-error{margin-top:8px;padding:10px 12px;border-radius:12px;background:#fbf1ee;overflow-wrap:anywhere;color:#7d3526}.run-error details{font-size:11.5px;color:var(--muted);margin-top:6px}.run-error summary{cursor:pointer}.run-error-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}.run-error-actions button{font-size:12px;padding:5px 10px;min-height:30px;border-radius:9px}
</style>
