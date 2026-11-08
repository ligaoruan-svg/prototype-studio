<script setup>
// 页面清单卡：梳理确认后、展开整棵树之前看一眼——每个模块下有哪些页、给谁用、管哪个对象、什么类型。
// 可选的页（账号、日志这类）打钩，拿不准的地方单选（默认第一个，就是推荐的）；确认后程序按页面类型展开。
// 底下一行：写了字就是「发送修改」（改清单），没写就是「按这个画架构」
import { computed, ref } from 'vue'
import { Check, ChevronDown, LayoutList } from 'lucide-vue-next'

// confirmed：已经按它画了的，确认时勾了哪些、选了什么（从那条消息读回来）——刷新后照当时的样子显示
const props = defineProps({ plan: Object, state: { type: String, default: 'open' }, locked: Boolean, confirmed: Object })
const emit = defineEmits(['draw', 'revise'])
const done = computed(() => props.state !== 'open')
const TYPE = { list: '管理列表', tasks: '我的任务', dashboard: '看板', report: '统计', config: '基础配置' }
// 可选页：默认照 AI 推荐的勾
const picked = ref(new Set(props.confirmed?.picked || (props.plan?.modules || []).flatMap(m => m.pages).filter(p => p.optional && p.pick).map(p => p.name)))
function toggle(name) { const next = new Set(picked.value); next.has(name) ? next.delete(name) : next.add(name); picked.value = next }
const choices = ref((props.plan?.choices || []).map(q => Math.max(0, q.options.indexOf(props.confirmed?.answers?.[q.q]))))
// 画好以后收起来，只留「几个模块、几个页面」和当时的选择；展开时不再列没勾的可选页
const folded = ref(done.value)
const modules = computed(() => (props.plan?.modules || []).map(m => ({ ...m, pages: m.pages.filter(p => !done.value || !p.optional || picked.value.has(p.name)) })).filter(m => m.pages.length))
const count = computed(() => modules.value.reduce((n, m) => n + m.pages.length, 0))
const note = ref('')
const drawing = ref(false)
function primary() {
  if (props.locked || drawing.value) return
  const text = note.value.trim()
  if (text) { note.value = ''; emit('revise', text); return }
  drawing.value = true
  emit('draw', { picked: [...picked.value], answers: (props.plan?.choices || []).map((q, i) => `${q.q}：${q.options[choices.value[i]]}`) })
}
</script>

<template>
  <div class="plan-card" :class="{ done }">
    <component :is="done ? 'button' : 'div'" class="plan-head" :type="done ? 'button' : undefined" :aria-expanded="done ? !folded : undefined" @click="done && (folded = !folded)">
      <LayoutList :size="14" /><span>{{ $t('页面清单') }}</span><small class="plan-count">{{ $t('{0} 个模块 · {1} 个页面', [modules.length, count]) }}</small><ChevronDown v-if="done" :size="13" class="plan-fold" :class="{ up: !folded }" />
      <em v-if="state === 'drawn'"><Check :size="11" />{{ $t('已画好') }}</em><small v-else-if="state === 'replaced'" class="plan-state">{{ $t('已更新，看下面的新版') }}</small>
    </component>
    <section v-for="m in folded ? [] : modules" :key="m.name" class="plan-module">
      <h4>{{ m.name }}</h4>
      <ul>
        <li v-for="p in m.pages" :key="p.name" :class="{ off: p.optional && !picked.has(p.name) }">
          <label v-if="p.optional" class="plan-pick"><input type="checkbox" :checked="picked.has(p.name)" :disabled="done || locked" @change="toggle(p.name)"></label>
          <i v-else class="plan-dot"></i>
          <b>{{ p.name }}</b><span class="plan-type" :class="p.type">{{ $t(TYPE[p.type] || p.type) }}</span>
          <small>{{ [p.object, (p.who || []).join('、')].filter(Boolean).join(' · ') }}</small>
          <p v-if="p.metrics?.length" class="plan-metrics">{{ p.metrics.map(x => x.split('：')[0]).join('、') }}</p>
        </li>
      </ul>
    </section>
    <div v-if="!done && plan.choices?.length" class="plan-choices">
      <div v-for="(q, qi) in plan.choices" :key="q.q" class="plan-q">
        <p>{{ q.q }}</p>
        <div><button v-for="(o, oi) in q.options" :key="o" type="button" :class="{ on: choices[qi] === oi }" :aria-pressed="choices[qi] === oi" :disabled="locked" @click="choices[qi] = oi">{{ o }}<em v-if="oi === 0">{{ $t('推荐') }}</em></button></div>
      </div>
    </div>
    <ul v-else-if="state === 'drawn' && plan.choices?.length" class="plan-decided">
      <li v-for="(q, qi) in plan.choices" :key="q.q"><span>{{ q.q }}</span><b>{{ q.options[choices[qi]] }}</b></li>
    </ul>
    <div v-if="!done" class="plan-foot">
      <input v-model="note" class="plan-note" maxlength="600" :disabled="locked" :placeholder="$t('哪里要改？直接说')" :aria-label="$t('修改页面清单')" @keydown.enter.prevent="primary">
      <button class="primary plan-draw" :disabled="locked || drawing" :title="$t('确认后程序按页面类型展开')" @click="primary">{{ note.trim() ? $t('发送修改') : drawing ? $t('正在画架构…') : $t('按这个画架构') }}</button>
    </div>
  </div>
</template>

<style scoped>
.plan-card{margin-top:12px;border:1px solid var(--line);border-radius:14px;background:#fff;padding:8px 6px 6px;box-shadow:0 1px 2px #2b201a08;font-size:12.5px;line-height:1.6}
.plan-head{display:flex;align-items:center;gap:6px;padding:2px 8px 6px;font-size:12px;font-weight:600;color:var(--ink)}.plan-head>svg{color:var(--primary)}
button.plan-head{width:100%;border:0;background:none;text-align:left;cursor:pointer;justify-content:flex-start;border-radius:9px}button.plan-head:hover{background:var(--quiet)}
.plan-head small{font-weight:400;font-size:11px;color:var(--muted)}.plan-head .plan-state{margin-left:auto}
.plan-fold{color:var(--subtle);transition:transform .15s}.plan-fold.up{transform:rotate(180deg)}
.plan-head em{margin-left:auto;display:flex;align-items:center;gap:3px;font-style:normal;font-weight:500;font-size:11px;color:var(--success)}
.plan-module{margin:0 8px 8px}.plan-module h4{margin:4px 0 2px;font-size:12px;font-weight:600;color:var(--ink)}
.plan-module ul{list-style:none;margin:0;padding:0}
.plan-module li{display:grid;grid-template-columns:16px auto auto 1fr;align-items:center;gap:6px;padding:3px 0}
.plan-module li.off b,.plan-module li.off small,.plan-module li.off .plan-type{opacity:.5}
.plan-dot{width:5px;height:5px;margin-left:5px;border-radius:50%;background:var(--subtle)}
.plan-pick input{margin:0}
.plan-module b{font-weight:500;color:var(--ink)}
.plan-type{padding:0 6px;border-radius:8px;background:var(--quiet);font-size:11px;color:var(--muted)}
.plan-type.dashboard,.plan-type.report{background:#eef3fc;color:#2f5bb5}.plan-type.tasks{background:#f2f0fb;color:#5b47a8}
.plan-module small{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)}
.plan-metrics{grid-column:2 / -1;margin:0;font-size:11.5px;color:#5f5a52}
.plan-choices{margin:6px 4px 0;padding:8px 4px 2px;border-top:1px solid #f0ede4}
.plan-q{margin:0 4px 8px}.plan-q p{margin:0 0 5px;font-weight:500;color:var(--ink)}
.plan-q div{display:flex;flex-wrap:wrap;gap:5px}
.plan-q button{flex-shrink:1;min-width:0;max-width:100%;justify-content:flex-start;gap:5px;padding:4px 10px;border:1px solid var(--line);border-radius:999px;background:#fff;font-size:12px;color:#4d4a44;white-space:normal;text-align:left}
.plan-q button.on{border-color:var(--primary);background:var(--primary-soft);color:var(--primary)}
.plan-q em{flex:none;font-style:normal;font-size:10px;padding:0 5px;border-radius:7px;background:#fff;color:var(--primary)}
.plan-decided{list-style:none;margin:2px 8px 4px;padding:6px 0 0;border-top:1px solid #f0ede4;font-size:12px}.plan-decided li{display:flex;gap:8px;padding:2px 0}.plan-decided span{color:var(--muted)}.plan-decided b{font-weight:500;color:var(--ink)}
.plan-foot{display:flex;align-items:center;gap:6px;margin-top:4px;padding:6px 2px 0;border-top:1px solid #f0ede4}
.plan-note{flex:1;min-width:0;height:32px;padding:0 8px;border:none;border-radius:9px;outline:none;background:none;font-size:12.5px;color:var(--ink)}.plan-note:focus{background:var(--quiet)}
.plan-draw{flex:none;min-height:32px;padding:5px 12px;border-radius:9px;font-size:12.5px}
.plan-card.done{background:transparent}
</style>
