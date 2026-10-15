<script setup>
import { computed, onMounted, ref } from 'vue'
import { LoaderCircle, Pencil, Plus, Sparkles, X, Check } from 'lucide-vue-next'
// 记忆面板，参照 Claude 的记忆：
// · 两层：「这个项目」只在本项目生效；「所有项目」是你个人的习惯，每个项目都带上
// · 按类别看；每条标明来源（你说的 / AI 自己整理的 / 你加的），能改、能删
// · 一句话让 AI 改记忆；可以暂停（照旧遵守、不再新记）、清空、马上整理一次
const props = defineProps({ projectId: String })
const emit = defineEmits(['count'])
const data = ref(null), busy = ref(false), error = ref(''), notice = ref('')
const instruction = ref(''), editing = ref(null), editText = ref('')
const adding = ref(false), draft = ref({ note: '', category: '设计风格', scope: 'project' })
const SOURCE = { said: '你说的', auto: '自己整理的', manual: '你加的' }
const api = async (url, method = 'GET', body) => {
  const r = await fetch(`/api/projects/${props.projectId}/memory${url}`, { method, headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) })
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : '操作没成功，请重试')
  return j
}
async function load() { data.value = await api(''); emit('count', total.value) }
async function run(action, done = '') {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { const out = await action(); await load(); notice.value = typeof done === 'function' ? done(out) : done }
  catch (e) { error.value = e.message }
  finally { busy.value = false }
}
const total = computed(() => (data.value?.project.memory.length || 0) + (data.value?.global.memory.length || 0))
const groups = scope => (data.value?.categories || []).map(c => ({ name: c, items: (data.value?.[scope].memory || []).filter(e => e.category === c) })).filter(g => g.items.length)
const paused = computed(() => !!data.value?.project.state.paused)
const lastSynth = computed(() => data.value?.project.state.synthesized_at ? new Date(data.value.project.state.synthesized_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '')
const changes = out => { const n = (out?.added?.length || 0) + (out?.updated?.length || 0) + (out?.removed?.length || 0); return n ? `改了 ${n} 处：新增 ${out.added.length}、修改 ${out.updated.length}、删除 ${out.removed.length}` : '看过了，没有需要改的' }
function askEdit() { const text = instruction.value.trim(); if (!text) return; run(async () => { const out = await api('/edit', 'POST', { instruction: text }); instruction.value = ''; return out }, changes) }
function synthesize() { run(() => api('/synthesize', 'POST'), out => out?.skipped === 'paused' ? '记忆暂停中，没有整理' : changes(out)) }
function togglePause() { run(() => api('/pause', 'POST', { scope: 'project', paused: !paused.value }), paused.value ? '记忆已恢复' : '已暂停：照旧遵守已记住的，不再记新的') }
function clearScope(scope) {
  if (!window.confirm(scope === 'global' ? '清空「所有项目」里你的习惯？每个项目都会受影响，不能恢复。' : '清空这个项目记住的所有内容？不能恢复。')) return
  run(() => api('/clear', 'POST', { scope }), '已清空')
}
function remove(item) { run(() => api(`/${item.id}`, 'DELETE'), '已删掉') }
function startEdit(item) { editing.value = item.id; editText.value = item.text }
function saveEdit(item) { const text = editText.value.trim(); if (!text || text === item.text) { editing.value = null; return } run(async () => { await api(`/${item.id}`, 'PATCH', { text }); editing.value = null }, '已修改') }
function addOne() { const d = draft.value; if (d.note.trim().length < 4) return; run(async () => { await api('', 'POST', { ...d, note: d.note.trim() }); draft.value = { ...d, note: '' }; adding.value = false }, '已记住') }
onMounted(() => load().catch(e => { error.value = e.message }))
</script>
<template>
  <div class="mem">
    <div class="mem-head">
      <p>AI 会记住以后还用得上的工作背景：你说过的约定、反复改过的偏好、业务里的叫法。每聊几句会在后台自己整理一次。</p>
      <button type="button" class="mem-switch" :class="{ off: paused }" role="switch" :aria-checked="!paused" :disabled="busy || !data" :title="paused ? '恢复：继续记新的' : '暂停：照旧遵守已记住的，但不再记新的'" @click="togglePause"><i></i>{{ paused ? '已暂停' : '记忆开着' }}</button>
    </div>
    <form class="mem-ask" @submit.prevent="askEdit">
      <Sparkles :size="14" />
      <input v-model="instruction" maxlength="300" :disabled="busy" placeholder="告诉 AI 要怎么改记忆，比如：描边那条只对次要按钮；记一下「配额」是年度免费排放额度" aria-label="用一句话修改记忆">
      <button class="primary" :disabled="busy || !instruction.trim()"><LoaderCircle v-if="busy" :size="13" class="spin" /><span v-else>改</span></button>
    </form>
    <p v-if="error" class="form-error">{{ error }}</p>
    <p v-else-if="notice" class="mem-notice"><Check :size="12" />{{ notice }}</p>
    <div v-if="!data" class="mem-empty"><LoaderCircle :size="14" class="spin" />正在读取…</div>
    <template v-else>
      <section v-for="scope in ['project', 'global']" :key="scope" class="mem-scope">
        <header><h4>{{ scope === 'project' ? '这个项目' : '所有项目 · 你的习惯' }}</h4><small>{{ scope === 'project' ? '只在这个项目里生效' : '每个项目都会带上' }} · {{ data[scope].memory.length }} / {{ data.max }}</small>
          <button v-if="data[scope].memory.length" type="button" class="text-button" :disabled="busy" @click="clearScope(scope)">清空</button></header>
        <p v-if="!data[scope].memory.length" class="mem-empty">{{ scope === 'project' ? '还没有。对话里说「以后表格都带斑马纹」，或者多聊几句，它会自己记下来。' : '还没有。说「我所有项目都……」「以后回复短一点」这类个人习惯会记在这里。' }}</p>
        <div v-for="g in groups(scope)" :key="g.name" class="mem-group">
          <h5>{{ g.name }}</h5>
          <div v-for="item in g.items" :key="item.id" class="mem-row">
            <template v-if="editing === item.id">
              <input v-model="editText" maxlength="120" class="mem-edit" aria-label="修改这条记忆" @keydown.enter.prevent="saveEdit(item)" @keydown.esc="editing = null">
              <button type="button" class="icon-button" title="保存" :disabled="busy" @click="saveEdit(item)"><Check :size="13" /></button>
            </template>
            <template v-else>
              <div><b>{{ item.text }}</b><small><span class="src" :class="item.source">{{ SOURCE[item.source] || '你说的' }}</span>{{ new Date(item.updated_at || item.created_at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) }}</small></div>
              <button type="button" class="icon-button" title="改这条" :disabled="busy" @click="startEdit(item)"><Pencil :size="12" /></button>
              <button type="button" class="icon-button" title="删掉这条" :aria-label="'删掉：' + item.text" :disabled="busy" @click="remove(item)"><X :size="13" /></button>
            </template>
          </div>
        </div>
      </section>
      <form v-if="adding" class="mem-add" @submit.prevent="addOne">
        <input v-model="draft.note" maxlength="120" placeholder="写成一句话，比如：表格都带斑马纹" aria-label="新的记忆" :disabled="busy">
        <select v-model="draft.category" aria-label="类别"><option v-for="c in data.categories" :key="c">{{ c }}</option></select>
        <select v-model="draft.scope" aria-label="范围"><option value="project">这个项目</option><option value="global">所有项目</option></select>
        <button class="primary" :disabled="busy || draft.note.trim().length < 4">记住</button><button type="button" class="quiet" @click="adding = false">取消</button>
      </form>
      <footer class="mem-foot">
        <button v-if="!adding" type="button" class="text-button" :disabled="busy" @click="adding = true"><Plus :size="13" />自己加一条</button>
        <span>{{ paused ? '暂停中，不会自动整理' : data.synthesizing ? '正在整理…' : lastSynth ? `上次整理 ${lastSynth}` : '还没整理过' }}{{ !paused && data.pending ? ` · 有 ${data.pending} 句新对话待整理` : '' }}</span>
        <button type="button" class="text-button" :disabled="busy || paused" title="不等攒够，马上从最近的对话里整理一次" @click="synthesize">现在整理</button>
      </footer>
      <p class="field-hint">只记工作上的背景；一次性的修改、页面里已经有的内容、密钥这类不会记。</p>
    </template>
  </div>
</template>
<style scoped>
.mem{font-size:12px}
.mem-head{display:flex;align-items:flex-start;gap:12px}
.mem-head p{flex:1;margin:0;color:var(--muted);line-height:1.7}
.mem-switch{display:inline-flex;align-items:center;gap:7px;flex-shrink:0;padding:4px 10px 4px 5px;border:1px solid var(--line);border-radius:20px;background:#fff;font-size:12px;color:var(--ink)}
.mem-switch i{position:relative;width:26px;height:15px;border-radius:10px;background:var(--success)}
.mem-switch i::after{content:'';position:absolute;top:2px;left:13px;width:11px;height:11px;border-radius:50%;background:#fff;transition:left .15s}
.mem-switch.off{color:var(--muted)}.mem-switch.off i{background:#cfc8bd}.mem-switch.off i::after{left:2px}
.mem-ask{display:flex;align-items:center;gap:8px;margin:14px 0 6px;padding:6px 6px 6px 11px;border:1px solid var(--line);border-radius:11px;background:#fff}
.mem-ask svg{color:var(--primary);flex-shrink:0}
.mem-ask input{flex:1;min-width:0;border:0;padding:4px 0;background:none;font-size:12px;outline:none}
.mem-ask button{min-width:44px;height:28px;padding:0 12px;border-radius:8px;font-size:12px}
.mem-notice{display:flex;align-items:center;gap:5px;color:var(--success);margin:4px 0}
.mem-scope{margin-top:16px}
.mem-scope header{display:flex;align-items:baseline;gap:8px;margin-bottom:6px}
.mem-scope h4{margin:0;font-size:13px;font-weight:600}
.mem-scope header small{flex:1;color:var(--subtle);font-size:11px}
.mem-group h5{margin:10px 0 5px;font-size:11px;font-weight:500;color:var(--muted)}
.mem-row{display:flex;align-items:flex-start;gap:4px;padding:8px 8px 8px 11px;margin-bottom:6px;border:1px solid var(--line);border-radius:10px;background:var(--surface)}
.mem-row>div{flex:1;min-width:0}
.mem-row b{display:block;font-weight:400;line-height:1.7;overflow-wrap:anywhere}
.mem-row small{display:flex;align-items:center;gap:6px;margin-top:2px;font-size:10.5px;color:var(--subtle)}
.mem-row .icon-button{width:26px;height:26px;color:var(--subtle)}.mem-row .icon-button:hover{color:var(--ink)}
.src{padding:0 6px;border-radius:10px;background:var(--quiet);color:var(--muted)}
.src.auto{background:#eef3fb;color:#4c6a8a}.src.manual{background:#f1f5ee;color:#4c7a52}
.mem-edit{flex:1;min-width:0;font-size:12px}
.mem-empty{display:flex;align-items:center;gap:6px;padding:10px 12px;border:1px dashed var(--line);border-radius:10px;color:var(--subtle);line-height:1.7}
.mem-add{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}
.mem-add input{flex:1 1 220px;min-width:0}
.mem-add select{font-size:12px}
.mem-foot{display:flex;align-items:center;gap:10px;margin-top:14px;padding-top:10px;border-top:1px solid var(--line);color:var(--subtle);font-size:11px}
.mem-foot span{flex:1;text-align:right}
.mem-foot .text-button{display:inline-flex;align-items:center;gap:4px;font-size:12px}
</style>
