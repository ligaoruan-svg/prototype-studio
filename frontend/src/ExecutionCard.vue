<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Check, AlertCircle, LoaderCircle, ChevronDown } from 'lucide-vue-next'
import ResultCard from './ResultCard.vue'
const props = defineProps({ run: Object, locked: Boolean })
defineEmits(['retry', 'settings', 'select', 'repair', 'dismiss', 'fill'])
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
// 以前不管干什么都写"修改中"：问一句"这里美观吗"也是修改中，还在读代码也是修改中。
// 标题按当下实际在做的事说话——讨论就说在看，动过文件才叫修改。
const heading = computed(() => {
  if (props.run.status === 'checking') return '检查中'
  if (!busy.value) return discussing.value ? '这次回复未完成' : '这次修改未完成'
  if (discussing.value) return props.run.steps.length ? '正在看这个页面' : '思考中'
  return props.run.editing ? '修改中' : '正在看代码'
})
</script>
<template>
  <section class="execution-card" :class="{ failed: run.status === 'failed' }" :aria-label="discussing ? '本次回复进度' : '本次修改进度'">
    <header><LoaderCircle v-if="busy" :size="14" class="spin" /><AlertCircle v-else :size="14" /><strong>{{ heading }}</strong><time>{{ clock }}</time></header>
    <ol v-if="run.plan?.length" class="plan-list" :aria-label="discussing ? '分析步骤' : '修改计划'"><li v-for="(step, i) in run.plan" :key="i" :class="step.status"><Check v-if="step.status === 'done'" :size="12" /><LoaderCircle v-else-if="step.status === 'active'" :size="12" class="spin" /><i v-else></i>{{ step.title }}</li></ol>
    <ol aria-live="polite"><li v-for="step in run.steps" :key="step.id" :class="[step.kind === 'note' ? 'note' : step.state, { foldable: step.kind !== 'note' && step.detail }]"><template v-if="step.kind !== 'note'"><Check v-if="step.state === 'done'" :size="13" /><AlertCircle v-else-if="step.state === 'error'" :size="13" /><LoaderCircle v-else :size="13" class="spin" /></template><div><button v-if="step.kind !== 'note' && step.detail" type="button" class="step-head" :aria-expanded="opened.has(step.id)" @click="toggle(step.id)">{{ step.label }}<ChevronDown :size="12" :class="{ open: opened.has(step.id) }" /></button><span v-else>{{ step.label }}</span><small v-if="step.error">{{ step.error }}</small><small v-else-if="step.detail && opened.has(step.id)" class="step-detail">{{ step.detail }}</small></div></li></ol>
    <p v-if="run.streamText && !run.result" class="stream-text">{{ run.streamText }}<span class="caret"></span></p>
    <p v-else-if="busy && !run.steps.some(s => s.state === 'running')" class="model-wait">{{ run.label || '理解需求中' }}</p>
    <ResultCard v-if="run.status === 'checking' && run.result" :result="run.result" checking />
    <div v-if="run.error" class="run-error"><p>{{ run.error.message }}</p><details v-if="run.error.detail && run.error.detail !== run.error.message"><summary>查看详情</summary><p>{{ run.error.detail }}</p></details><div class="run-error-actions"><button v-if="run.error.code === 'model_account'" class="outline" @click="$emit('settings')">打开设置</button><button v-else-if="run.error.code === 'validation'" class="outline" :disabled="locked" @click="$emit('repair')">让 AI 修复</button><button v-else-if="run.error.code === 'patch_target'" class="outline" :disabled="locked" @click="$emit('select')">重新点选后重试</button><button v-else-if="['output_limit','invalid_arguments','iterations','tool_rejected','stalled'].includes(run.error.code)" class="outline" :disabled="locked" @click="$emit('fill')">缩小范围重试</button><button v-else class="outline" :disabled="locked" @click="$emit('retry')">重试</button><button class="quiet" @click="$emit('dismiss')">{{ run.error.code === 'validation' ? '放弃' : '关闭' }}</button></div></div>
  </section>
</template>
<style scoped>
.execution-card{border:1px solid var(--line);background:transparent;padding:12px 13px;border-radius:12px;margin:12px 0 18px;font-size:12px;line-height:1.65}.execution-card.failed{border-color:#e8cfc6;background:#fffcfb}.execution-card header{display:flex;gap:7px;align-items:center;color:var(--primary)}.execution-card.failed header{color:#a24b37}.execution-card strong{font-size:12px;font-weight:600}.execution-card time{margin-left:auto;color:var(--muted);font-variant-numeric:tabular-nums}
.execution-card ol{list-style:none;margin:11px 0 0;padding:0;display:flex;flex-direction:column;gap:7px}.execution-card li{display:flex;gap:7px;color:#706159}.execution-card li svg{margin-top:3px}.execution-card li small{display:block;font-size:11px;color:#a24b37;overflow-wrap:anywhere}
.execution-card li small.step-detail{color:var(--muted);margin-top:3px;line-height:1.7}
.step-head{display:flex;align-items:center;gap:4px;padding:0;min-height:0;background:none;border:0;color:inherit;font:inherit;text-align:left;cursor:pointer}
.step-head svg{color:#bcaea8;flex-shrink:0;transition:transform .15s}
.step-head svg.open{transform:rotate(180deg)}
.execution-card li.foldable:hover .step-head{color:var(--ink)}.execution-card li.error{color:#a24b37}.execution-card li.running{color:var(--primary)}
.execution-card li.note{color:var(--ink);padding-left:1px;line-height:1.75;margin:3px 0}.plan-list{list-style:none;margin:10px 0 0;padding:9px 10px;border:1px solid var(--line);border-radius:9px;display:flex;flex-direction:column;gap:6px}
.plan-list li{display:flex;align-items:center;gap:7px;color:var(--muted)}
.plan-list li>i{width:12px;height:12px;border:1.5px solid var(--line);border-radius:50%;flex-shrink:0}
.plan-list li.active{color:var(--ink);font-weight:500}
.plan-list li.done{color:var(--success);text-decoration:line-through;text-decoration-color:#4c7a5255}
.stream-text{margin-top:11px;font-size:13px;line-height:1.85;color:var(--ink);white-space:pre-wrap;overflow-wrap:anywhere}
.caret{display:inline-block;width:2px;height:1em;margin-left:2px;vertical-align:-2px;background:var(--primary);animation:blink 1.1s step-end infinite}
@keyframes blink{50%{opacity:0}}
@media (prefers-reduced-motion: reduce){.caret{animation:none}}
.model-wait{font-size:11px;color:var(--muted);margin-top:9px}.run-error{margin-top:10px;overflow-wrap:anywhere}.run-error details{font-size:11px;color:var(--muted);margin-top:6px}.run-error summary{cursor:pointer}.run-error-actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}.run-error-actions button{font-size:11px;padding:6px 8px;min-height:30px}
</style>
