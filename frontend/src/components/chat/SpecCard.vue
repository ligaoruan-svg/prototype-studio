<script setup>
// 业务梳理卡（参照 Claude 先给计划、你点头再动手）：出架构之前先看这一张——角色、业务对象和状态、主流程、规则、范围。
// 每一块一行摘要，点开看全；AI 拿不准的地方带选项问你（默认选第一个，就是它推荐的）。
// 底下一行：写了字就是「发送修改」（改梳理），没写就是确认——接着出页面清单卡
import { computed, ref, watch } from 'vue'
import { Check, ChevronDown, ListChecks } from 'lucide-vue-next'

// state：open 等你确认；confirmed 已确认、出了页面清单；drawn 已经按它画了；replaced 后面有了新版
const props = defineProps({ spec: Object, state: { type: String, default: 'open' }, locked: Boolean })
const done = computed(() => props.state !== 'open')
const emit = defineEmits(['draw', 'revise'])
const sections = computed(() => {
  const s = props.spec || {}, scope = s.scope || {}
  return [
    { key: 'roles', label: '角色', count: s.roles?.length, line: (s.roles || []).map(r => r.name).join('、') },
    { key: 'objects', label: '业务对象', count: s.objects?.length, line: (s.objects || []).map(o => o.name).join('、') },
    { key: 'flows', label: '主流程', count: s.flows?.length, line: s.flows?.[0] || '' },
    { key: 'rules', label: '规则', count: s.rules?.length, line: s.rules?.[0] || '' },
    { key: 'scope', label: '范围', count: (scope.in?.length || 0) + (scope.out?.length || 0) + (scope.external?.length || 0),
      line: [scope.in?.length && `做 ${scope.in.length}`, scope.out?.length && `不做 ${scope.out.length}`, scope.external?.length && `外部 ${scope.external.length}`].filter(Boolean).join(' · ') },
  ].filter(x => x.count)
})
// 确认过的卡片收起来只留一行（像 Claude 做完的计划那样），点标题再展开
const folded = ref(done.value)
const foldable = computed(() => done.value || drawing.value)
const opened = ref(new Set(done.value ? [] : ['objects']))
// 字段表在卡片上只露名字和 * 🔒，控件、选项放到悬停提示里（不然一个对象占好几行）
const short = f => String(f).replace(/\s*[（(].*$/, '')
function toggle(key) { const next = new Set(opened.value); next.has(key) ? next.delete(key) : next.add(key); opened.value = next }
// 问题的回答：默认第一个（推荐的）
const picks = ref((props.spec?.questions || []).map(() => 0))
const note = ref('')
const answers = computed(() => (props.spec?.questions || []).map((q, i) => `${q.q}：${q.options[picks.value[i]]}`))
// 点了「按这个画架构」就不能再点（以前点两下会画两遍）
const drawing = ref(false)
// 点了确认、或者后面已经出了清单 / 画好了：收起来，下面接着出的东西才看得见
watch([done, drawing], ([d, w]) => { if (d || w) folded.value = true })
function primary() {
  if (props.locked || drawing.value) return
  const text = note.value.trim()
  if (text) { note.value = ''; emit('revise', text) }
  else { drawing.value = true; emit('draw', { answers: answers.value }) }
}
</script>

<template>
  <div class="spec-card" :class="{ done }">
    <component :is="foldable ? 'button' : 'div'" class="spec-head" :type="foldable ? 'button' : undefined" :aria-expanded="foldable ? !folded : undefined" @click="foldable && (folded = !folded)"><ListChecks :size="14" /><span>{{ $t('业务梳理') }}</span><ChevronDown v-if="foldable" :size="13" class="spec-fold" :class="{ up: !folded }" /><em v-if="state === 'drawn'"><Check :size="11" />{{ $t('已按它画好架构') }}</em><em v-else-if="state === 'confirmed'"><Check :size="11" />{{ $t('已确认') }}</em><small v-else-if="state === 'replaced'">{{ $t('已更新，看下面的新版') }}</small><small v-else>{{ $t('确认后再画架构') }}</small></component>
    <p v-if="spec.summary" class="spec-summary">{{ spec.summary }}</p>
    <ul v-if="!folded" class="spec-sections">
      <li v-for="sec in sections" :key="sec.key" :class="{ open: opened.has(sec.key) }">
        <button type="button" class="spec-row" :aria-expanded="opened.has(sec.key)" @click="toggle(sec.key)">
          <b>{{ $t(sec.label) }}</b><i>{{ sec.count }}</i><span>{{ sec.line }}</span><ChevronDown :size="14" class="fold" />
        </button>
        <div v-if="opened.has(sec.key)" class="spec-detail">
          <template v-if="sec.key === 'roles'"><p v-for="r in spec.roles" :key="r.name"><b>{{ r.name }}</b>{{ r.does ? '：' + r.does : '' }}</p></template>
          <template v-else-if="sec.key === 'objects'">
            <div v-for="o in spec.objects" :key="o.name" class="spec-object">
              <p><b>{{ o.name }}</b><span v-if="o.desc">{{ o.desc }}</span><small v-if="o.owner">{{ $t('{0} 管', [o.owner]) }}</small></p>
              <p v-if="o.fields?.length" class="spec-fields" :title="o.fields.join('、')"><em>{{ $t('字段') }}</em>{{ o.fields.map(short).join('、') }}</p>
              <div v-if="o.states.length" class="spec-states"><span v-for="(st, i) in o.states" :key="st">{{ st }}<i v-if="i < o.states.length - 1">→</i></span></div>
              <ul v-if="o.actions.length" class="spec-actions"><li v-for="a in o.actions" :key="a">{{ a }}</li></ul>
            </div>
          </template>
          <template v-else-if="sec.key === 'scope'">
            <p v-if="spec.scope.in.length"><b>{{ $t('这次做') }}</b>{{ spec.scope.in.join('、') }}</p>
            <p v-if="spec.scope.out.length"><b>{{ $t('这次不做') }}</b>{{ spec.scope.out.join('、') }}</p>
            <p v-if="spec.scope.external.length"><b>{{ $t('外部系统') }}</b>{{ spec.scope.external.join('、') }}</p>
          </template>
          <ul v-else class="spec-list"><li v-for="x in spec[sec.key]" :key="x">{{ x }}</li></ul>
        </div>
      </li>
    </ul>
    <div v-if="!folded && spec.assumptions?.length" class="spec-assume"><b>{{ $t('我先这样假设') }}</b><ul><li v-for="a in spec.assumptions" :key="a">{{ a }}</li></ul></div>
    <div v-if="!done && !folded && spec.questions?.length" class="spec-questions">
      <div v-for="(q, qi) in spec.questions" :key="q.q" class="spec-q">
        <p>{{ q.q }}</p>
        <div class="spec-options"><button v-for="(o, oi) in q.options" :key="o" type="button" :class="{ on: picks[qi] === oi }" :aria-pressed="picks[qi] === oi" :disabled="locked" @click="picks[qi] = oi">{{ o }}<em v-if="oi === 0">{{ $t('推荐') }}</em></button></div>
      </div>
    </div>
    <div v-if="!done && !folded" class="spec-foot">
      <input v-model="note" class="spec-note" maxlength="600" :disabled="locked" :placeholder="$t('哪里要改？直接说')" :aria-label="$t('修改梳理')" @keydown.enter.prevent="primary">
      <button class="primary spec-draw" :disabled="locked || drawing" @click="primary">{{ note.trim() ? $t('发送修改') : drawing ? $t('正在列页面清单…') : $t('确认，列页面清单') }}</button>
    </div>
  </div>
</template>

<style scoped>
.spec-card{margin-top:12px;border:1px solid var(--line);border-radius:14px;background:#fff;padding:8px 6px 6px;box-shadow:0 1px 2px #2b201a08;font-size:12.5px;line-height:1.65}
.spec-head{display:flex;align-items:center;gap:6px;padding:2px 8px 4px;font-size:12px;font-weight:600;color:var(--ink)}.spec-head>svg{color:var(--primary)}
button.spec-head{width:100%;border:0;background:none;text-align:left;cursor:pointer;justify-content:flex-start;border-radius:9px}button.spec-head:hover{background:var(--quiet)}
.spec-fold{color:var(--subtle);transition:transform .15s}.spec-fold.up{transform:rotate(180deg)}
.spec-head small{margin-left:auto;font-weight:400;font-size:11px;color:var(--muted)}
.spec-head em{margin-left:auto;display:flex;align-items:center;gap:3px;font-style:normal;font-weight:500;font-size:11px;color:var(--success)}
.spec-summary{margin:0 8px 6px;color:#4d4a44}
.spec-sections{list-style:none;margin:0;padding:0}
.spec-row{display:grid;grid-template-columns:auto auto 1fr auto;align-items:center;gap:7px;width:100%;padding:6px 8px;border-radius:9px;text-align:left;justify-content:stretch}
.spec-row:hover{background:var(--quiet)}
.spec-row b{font-weight:500;color:var(--ink)}
.spec-row i{font-style:normal;min-width:18px;padding:0 5px;border-radius:8px;background:var(--quiet);font-size:11px;color:var(--muted);text-align:center}
.spec-row span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)}
.spec-row .fold{color:var(--subtle);transition:transform .15s}.open>.spec-row .fold{transform:rotate(180deg)}
.spec-detail{margin:0 8px 8px 10px;padding:6px 0 2px 12px;border-left:1.5px solid var(--line);color:#4d4a44}
.spec-detail p{margin:2px 0}.spec-detail p b{font-weight:500;color:var(--ink);margin-right:6px}
.spec-object{margin-bottom:8px}.spec-object p span{color:var(--muted)}.spec-object small{margin-left:6px;font-size:11px;color:var(--subtle)}
.spec-fields{color:#5f5a52;font-size:12px}.spec-fields em{font-style:normal;color:var(--subtle);margin-right:6px}
.spec-states{display:flex;flex-wrap:wrap;gap:3px;margin:3px 0}.spec-states span{display:inline-flex;align-items:center;gap:3px;padding:0 7px;border-radius:9px;background:#eef3fc;color:#2f5bb5;font-size:11.5px}
.spec-states i{font-style:normal;color:var(--subtle);margin-left:2px}
.spec-actions,.spec-list{margin:2px 0 0;padding-left:16px;color:#5f5a52}.spec-actions li,.spec-list li{margin:1px 0}
.spec-assume{margin:6px 8px;padding:6px 9px;border-radius:9px;background:var(--quiet);font-size:12px;color:#5f5a52}.spec-assume b{display:block;font-weight:500;color:var(--ink)}
.spec-assume ul{margin:2px 0 0;padding-left:16px}.spec-assume li{margin:1px 0}
.spec-questions{margin:6px 4px 0;padding:8px 4px 2px;border-top:1px solid #f0ede4}
.spec-q{margin:0 4px 8px}.spec-q p{margin:0 0 7px;font-weight:500;color:var(--ink);line-height:1.6}
.spec-options{display:flex;flex-direction:column;gap:6px;min-width:0}
.spec-options button{display:flex;align-items:center;gap:8px;width:100%;min-width:0;max-width:none;padding:7px 10px;border:1px solid var(--line);border-radius:10px;background:#fff;font-size:12.5px;line-height:1.5;color:var(--ink);white-space:normal;text-align:left;justify-content:flex-start}
.spec-options button::before{content:'';flex:none;width:12px;height:12px;border:1.5px solid #cfcbc0;border-radius:50%;box-sizing:border-box}
.spec-options button:hover:not(:disabled){background:var(--quiet)}
.spec-options button.on{border-color:var(--primary);background:var(--primary-soft)}.spec-options button.on::before{border:4px solid var(--primary)}
.spec-options em{flex:none;margin-left:auto;font-style:normal;font-size:10.5px;padding:0 6px;border-radius:7px;background:#fff;color:var(--primary)}
.spec-foot{display:flex;align-items:center;gap:6px;margin-top:4px;padding:6px 2px 0;border-top:1px solid #f0ede4}
.spec-note{flex:1;min-width:0;height:32px;padding:0 8px;border:none;border-radius:9px;outline:none;background:none;font-size:12.5px;color:var(--ink)}.spec-note:focus{background:var(--quiet)}
.spec-draw{flex:none;min-height:32px;padding:5px 12px;border-radius:9px;font-size:12.5px}
.spec-card.done{background:transparent}
</style>
