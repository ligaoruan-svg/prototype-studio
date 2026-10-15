<script setup>
import { computed, ref } from 'vue'
import { Check, Pencil, Plus, ShieldCheck, Trash2, LoaderCircle, Eye, PlugZap } from 'lucide-vue-next'
// 绑定多个模型：可以同时绑好几家服务商、好几个模型，在输入框下面一点就切。
// 每个模型一套：显示名、接口地址、模型名、密钥、能不能看图、输出上限。密钥只存在本机服务里。
const props = defineProps({ model: Object, notice: String, keepInspector: Boolean })
const emit = defineEmits(['saved', 'update:keepInspector'])
const profiles = computed(() => props.model?.profiles || [])
// 常见服务商：只帮你填接口地址（都兼容 OpenAI 的 Chat Completions）；模型名去服务商控制台看
const PROVIDERS = [
  { name: 'DeepSeek', url: 'https://api.deepseek.com', models: ['deepseek-flash', 'deepseek-v4-pro'] },
  { name: '通义千问', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { name: 'Kimi', url: 'https://api.moonshot.cn/v1' },
  { name: '智谱', url: 'https://open.bigmodel.cn/api/paas/v4' },
  { name: '豆包', url: 'https://ark.cn-beijing.volces.com/api/v3' },
  { name: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
  { name: 'OpenAI', url: 'https://api.openai.com/v1' },
]
const blank = () => ({ id: '', name: '', base_url: 'https://api.deepseek.com', model: '', api_key: '', supports_vision: false, stream: true, max_tokens: 16384, context_budget: 200000, max_rounds: 24 })
const form = ref(null), busy = ref(''), error = ref(''), done = ref('')
const host = url => { try { return new URL(url).host } catch { return '' } }
const provider = computed(() => PROVIDERS.find(p => form.value && host(p.url) === host(form.value.base_url)))
const sameHost = computed(() => form.value && profiles.value.find(p => p.host === host(form.value.base_url) && p.has_key && p.id !== form.value.id))
const editingOld = computed(() => form.value?.id && profiles.value.find(p => p.id === form.value.id))
const keyHint = computed(() => {
  if (editingOld.value && editingOld.value.has_key && editingOld.value.host === host(form.value.base_url)) return '已保存在本机，留空沿用'
  if (sameHost.value) return `留空就用已绑定的「${sameHost.value.name || sameHost.value.model}」那把密钥`
  return '填这个服务商给你的 API Key'
})
function addNew() { form.value = blank(); error.value = ''; done.value = '' }
function edit(p) { form.value = { ...blank(), ...p, api_key: '' }; error.value = ''; done.value = '' }
function pickProvider(p) { form.value.base_url = p.url; if (p.models && !p.models.includes(form.value.model)) form.value.model = p.models[0] }
async function call(url, method = 'POST', body) {
  const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) })
  const j = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : '操作没成功，请重试')
  return j
}
async function act(kind, fn) {
  if (busy.value) return
  busy.value = kind; error.value = ''; done.value = ''
  try { await fn() } catch (e) { error.value = e.message } finally { busy.value = '' }
}
// 保存（可选：顺便用它 / 顺便测一下连接）
function save({ use = false, test = false } = {}) {
  return act(test ? 'test' : 'save', async () => {
    const out = await call('/api/config/profiles', 'POST', { ...form.value, activate: use })
    emit('saved', out)
    const name = form.value.name || form.value.model
    if (test) { await call('/api/config/test', 'POST', { id: out.saved_id }); done.value = `「${name}」连接成功` }
    else done.value = use ? `已保存，正在用「${name}」` : `已保存「${name}」，在输入框下面可以切换过去`
    form.value = null
  })
}
function use(p) { act('use' + p.id, async () => { emit('saved', await call('/api/config/switch', 'POST', { id: p.id })); done.value = `正在用「${p.name || p.model}」` }) }
function remove(p) {
  if (!window.confirm(`解绑「${p.name || p.model}」？它的密钥也会从本机删掉。`)) return
  act('del' + p.id, async () => { emit('saved', await call(`/api/config/profiles/${p.id}`, 'DELETE')); done.value = '已解绑' })
}
function testOne(p) { act('test' + p.id, async () => { await call('/api/config/test', 'POST', { id: p.id }); done.value = `「${p.name || p.model}」连接成功` }) }
</script>
<template>
  <div class="models">
    <p class="dialog-intro">可以绑定多个模型（不同服务商也行），在输入框下面的模型名那里一点就能切换。都需要兼容 Chat Completions 接口。</p>
    <p v-if="notice" class="form-error" role="alert">{{ notice }}</p>
    <ul class="model-list">
      <li v-for="p in profiles" :key="p.id" :class="{ active: p.active, editing: form?.id === p.id }">
        <div class="who"><b>{{ p.name || p.model }}</b><small>{{ p.name ? p.model + ' · ' : '' }}{{ p.host }}<template v-if="!p.has_key"> · <em class="warn">缺密钥</em></template></small></div>
        <span v-if="p.supports_vision" class="tag" title="能看截图"><Eye :size="11" />看图</span>
        <span v-if="p.active" class="tag on"><Check :size="11" />正在用</span>
        <button v-else type="button" class="outline small" :disabled="!!busy || !p.has_key" @click="use(p)">用它</button>
        <button type="button" class="icon-button" title="测试连接（会发一条短消息）" :disabled="!!busy || !p.has_key" @click="testOne(p)"><LoaderCircle v-if="busy === 'test' + p.id" :size="13" class="spin" /><PlugZap v-else :size="13" /></button>
        <button type="button" class="icon-button" title="修改" :disabled="!!busy" @click="edit(p)"><Pencil :size="13" /></button>
        <button type="button" class="icon-button" :title="p.active ? '正在用的不能解绑，先切到别的' : '解绑'" :disabled="!!busy || p.active" @click="remove(p)"><Trash2 :size="13" /></button>
      </li>
    </ul>
    <button v-if="!form" type="button" class="outline add-model" :disabled="!!busy" @click="addNew"><Plus :size="14" />绑定新模型</button>
    <form v-else class="model-form" @submit.prevent="save({ use: !form.id })">
      <h4>{{ form.id ? '修改「' + (form.name || form.model) + '」' : '绑定新模型' }}</h4>
      <div class="providers" role="group" aria-label="服务商"><span>服务商</span><button v-for="p in PROVIDERS" :key="p.name" type="button" :class="{ on: provider?.name === p.name }" @click="pickProvider(p)">{{ p.name }}</button><button type="button" :class="{ on: !provider }" @click="form.base_url = ''">其他</button></div>
      <label>接口地址<input v-model="form.base_url" type="url" required placeholder="https://…/v1"></label>
      <div class="two"><label>模型名称<input v-model="form.model" required :placeholder="provider?.models?.[0] || '服务商控制台里的模型名'" list="model-name-options"><datalist id="model-name-options"><option v-for="m in provider?.models || []" :key="m" :value="m"></option></datalist></label>
        <label>显示名<small>可不填</small><input v-model="form.name" maxlength="30" placeholder="比如：快的 / 能看图的"></label></div>
      <label>API 密钥<input v-model="form.api_key" type="password" autocomplete="off" :placeholder="keyHint"></label>
      <div class="limit-grid"><label>单次输出<small>tokens</small><input v-model.number="form.max_tokens" type="number" min="1024" max="131072" step="1024" required></label><label>上下文预算<small>字符</small><input v-model.number="form.context_budget" type="number" min="20000" max="2000000" step="20000" required></label><label>轮次上限<small>次</small><input v-model.number="form.max_rounds" type="number" min="4" max="60" step="2" required></label></div>
      <p class="field-hint">按模型的真实能力填，填大了接口会报错。上下文预算要大于你的组件库，否则读进来就被折叠掉。</p>
      <label class="vision-option"><input type="checkbox" v-model="form.supports_vision">这个模型能看图片（截图理解）</label>
      <label class="vision-option"><input type="checkbox" v-model="form.stream">逐字显示回复（接口不支持流式时关掉）</label>
      <div class="dialog-actions"><button type="button" class="quiet" :disabled="!!busy" @click="form = null">取消</button><button type="button" class="outline" :disabled="!!busy" @click="save({ test: true })"><LoaderCircle v-if="busy === 'test'" :size="13" class="spin" />保存并测试</button><button class="primary" :disabled="!!busy">{{ form.id ? '保存' : '保存并使用' }}</button></div>
    </form>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <p v-else-if="done" class="model-done"><Check :size="12" />{{ done }}</p>
    <label class="vision-option pref"><input type="checkbox" :checked="keepInspector" @change="emit('update:keepInspector', $event.target.checked)">始终展开属性面板</label>
    <div class="settings-note"><ShieldCheck :size="17" /><p>密钥只保存在本机服务配置里，不写进浏览器或原型文件。截图理解要用勾了「能看图片」的模型。测试连接会发一条短消息，可能产生少量费用。</p></div>
    <p class="field-hint">当前服务 v{{ model.version || '?' }}，{{ model.started_at || '未知时间' }} 启动——改了后端代码要重启才生效。</p>
  </div>
</template>
<style scoped>
.model-list{list-style:none;margin:14px 0 10px;padding:0;display:flex;flex-direction:column;gap:6px}
.model-list li{display:flex;align-items:center;gap:6px;padding:9px 8px 9px 12px;border:1px solid var(--line);border-radius:11px;background:#fff}
.model-list li.active{border-color:#e1cabd;background:#fffaf6}
.model-list li.editing{border-color:var(--primary)}
.who{flex:1;min-width:0}
.who b{display:block;font-size:13px;font-weight:550;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.who small{display:block;font-size:11px;color:var(--subtle);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.who .warn{font-style:normal;color:var(--danger)}
.tag{display:inline-flex;align-items:center;gap:3px;flex-shrink:0;padding:1px 7px;border-radius:20px;background:#eef3fb;color:#4c6a8a;font-size:11px}
.tag.on{background:var(--primary-soft);color:var(--primary)}
.outline.small{height:26px;padding:0 10px;font-size:12px;border-radius:8px}
.model-list .icon-button{width:28px;height:28px;color:var(--subtle)}
.model-list .icon-button:hover:not(:disabled){color:var(--ink)}
.add-model{display:inline-flex;align-items:center;gap:6px;height:32px;padding:0 12px;border-radius:9px;font-size:12.5px}
.model-form{margin-top:6px;padding:14px;border:1px solid var(--line);border-radius:12px;background:var(--quiet)}
.model-form h4{margin:0 0 10px;font-size:13px}
.providers{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-bottom:10px}
.providers span{font-size:12px;color:var(--muted);margin-right:2px}
.providers button{padding:3px 10px;border:1px solid var(--line);border-radius:20px;background:#fff;font-size:12px;color:var(--muted)}
.providers button.on{border-color:var(--primary);color:var(--primary);background:var(--primary-soft)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.model-done{display:flex;align-items:center;gap:5px;color:var(--success);font-size:12px;margin:8px 0}
.pref{margin-top:12px}
@media (max-width:640px){.two{grid-template-columns:1fr}}
</style>
