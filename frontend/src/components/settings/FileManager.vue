<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { FolderOpen, FileCode2, Pencil, Trash2, RotateCcw, Search, LoaderCircle, ChevronRight } from 'lucide-vue-next'
const props = defineProps({ currentProjectId: String })
const emit = defineEmits(['changed', 'open', 'busy'])
const projects = ref([]), trash = ref([]), view = ref('projects'), query = ref('')
const busy = ref(false), error = ref(''), message = ref(''), deleting = ref(null), renaming = ref(null), purging = ref(null), name = ref('')
const actionBox = ref(null)
const visibleProjects = computed(() => projects.value.filter(p => p.name.toLowerCase().includes(query.value.toLowerCase()) || p.pages.some(page => page.title.toLowerCase().includes(query.value.toLowerCase()))))
const visibleTrash = computed(() => trash.value.filter(p => p.name.toLowerCase().includes(query.value.toLowerCase())))
async function request(url, method = 'GET', body) {
  const response = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) })
  const data = await response.json().catch(() => ({}))   // 出错时后台可能回的是纯文本
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '操作失败，请重试')
  return data
}
async function load() { [projects.value, trash.value] = await Promise.all([request('/api/projects'), request('/api/trash')]) }
async function perform(action, success) {
  if (busy.value) return
  busy.value = true; emit('busy', true); error.value = ''; message.value = ''
  try { await action(); await load(); message.value = success; emit('changed') }
  catch (e) { error.value = e.message }
  finally { busy.value = false; emit('busy', false) }
}
function target(project, page) { return { kind: page ? 'page' : 'project', project_id: project.id, page_id: page?.id || '', name: page?.title || project.name, page_count: project.page_count } }
function url(item) { return `/api/projects/${item.project_id}` + (item.page_id ? `/pages/${item.page_id}` : '') }
async function rename(item) { renaming.value = item; deleting.value = null; purging.value = null; name.value = item.name; error.value = ''; await nextTick(); actionBox.value?.querySelector('input')?.focus() }
async function remove(item) { deleting.value = item; renaming.value = null; purging.value = null; error.value = ''; await nextTick(); actionBox.value?.querySelector('button')?.focus() }
async function saveName() { await perform(async () => { await request(url(renaming.value), 'PATCH', { name: name.value }); renaming.value = null }, '名称已更新，原始文件路径保持不变') }
async function confirmDelete() { await perform(async () => { await request(url(deleting.value), 'DELETE'); deleting.value = null }, '已移入回收站，可以随时恢复') }
async function restore(item) { await perform(() => request('/api/trash/restore', 'POST', { project_id: item.project_id, page_id: item.page_id || '' }), '已恢复，可在项目列表中打开') }
// 彻底删除：回收站里不要的东西真正删掉，腾出空间。删前确认一次，删了不能恢复
async function askPurge(item) { purging.value = item; deleting.value = null; renaming.value = null; error.value = ''; await nextTick(); actionBox.value?.querySelector('button')?.focus() }
async function confirmPurge() {
  const item = purging.value
  await perform(async () => {
    if (item.all) await request('/api/trash/empty', 'POST')
    else await request('/api/trash/purge', 'POST', { project_id: item.project_id, page_id: item.page_id || '' })
    purging.value = null
  }, item.all ? '回收站已清空' : '已彻底删除')
}
function switchView(value) { view.value = value; deleting.value = null; purging.value = null; renaming.value = null; error.value = ''; message.value = '' }
function date(value) { return new Date(value).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) }
onMounted(async () => { busy.value = true; try { await load() } catch (e) { error.value = e.message } finally { busy.value = false } })
</script>

<template>
  <div class="file-manager">
    <p class="dialog-intro">管理导入和新建的项目。删除会放入回收站，源码、资源和历史版本仍可恢复。</p>
    <div class="file-tabs" role="tablist" aria-label="文件分类">
      <button role="tab" :aria-selected="view === 'projects'" :disabled="busy" @click="switchView('projects')"><FolderOpen :size="15" />项目<span>{{ projects.length }}</span></button>
      <button role="tab" :aria-selected="view === 'trash'" :disabled="busy" @click="switchView('trash')"><Trash2 :size="15" />回收站<span>{{ trash.length }}</span></button>
    </div>
    <div class="file-search"><Search :size="16" /><input v-model="query" aria-label="搜索文件" placeholder="搜索项目或页面名称"></div>
    <form v-if="renaming" ref="actionBox" class="file-action-box" @submit.prevent="saveName">
      <label for="file-name">重命名{{ renaming.kind === 'project' ? '项目' : '页面' }}</label><input id="file-name" v-model="name" aria-label="新名称" maxlength="80" required :disabled="busy">
      <p>只更新工作台名称，不改动文件路径或原型中的内容。</p>
      <div class="file-action-buttons"><button type="button" class="outline" :disabled="busy" @click="renaming = null">取消</button><button class="primary" :disabled="busy || !name.trim()">保存名称</button></div>
    </form>
    <div v-if="deleting" ref="actionBox" class="file-action-box delete-confirm" role="alert">
      <h3>删除{{ deleting.kind === 'project' ? '项目' : '页面' }}“{{ deleting.name }}”？</h3>
      <p>{{ deleting.kind === 'project' ? `此项目及其 ${deleting.page_count} 个在用页面将从工作区移除。` : '此页面将从项目中移除，其他页面不受影响；指向它的链接可能暂时不可用。' }}你可以在回收站恢复，不会删除最初上传的文件。</p>
      <div class="file-action-buttons"><button class="outline" :disabled="busy" @click="deleting = null">取消</button><button class="danger-button" :disabled="busy" @click="confirmDelete"><Trash2 :size="15" />移入回收站</button></div>
    </div>
    <div v-if="purging" ref="actionBox" class="file-action-box delete-confirm" role="alert">
      <h3>{{ purging.all ? `清空回收站（${trash.length} 项）？` : `彻底删除${purging.kind === 'project' ? '项目' : '页面'}“${purging.name}”？` }}</h3>
      <p>删除后无法恢复：工作区里的源码副本、历史版本、修改记录和展开结果都会删掉。你电脑上最初导入的那个文件不受影响。</p>
      <div class="file-action-buttons"><button class="outline" :disabled="busy" @click="purging = null">取消</button><button class="danger-button" :disabled="busy" @click="confirmPurge"><Trash2 :size="15" />{{ purging.all ? '全部彻底删除' : '彻底删除' }}</button></div>
    </div>
    <p v-if="error" class="form-error" role="alert">{{ error }}<button class="text-button" :disabled="busy" @click="perform(load, '列表已刷新')">重试加载</button></p>
    <p v-if="message" class="file-feedback" role="status">{{ message }}</p>
    <div v-if="busy" class="file-loading" role="status"><LoaderCircle class="spin" :size="16" />正在更新文件…</div>
    <div class="file-list" :aria-busy="busy">
      <template v-if="view === 'projects'">
        <article v-for="project in visibleProjects" :key="project.id" class="managed-project">
          <div class="managed-row"><FolderOpen :size="21" class="file-kind" /><div class="managed-title"><b>{{ project.name }}</b><small>{{ project.page_count }} 个页面 · {{ date(project.updated_at) }} 更新<span v-if="project.id === props.currentProjectId"> · 当前项目</span></small></div><button class="icon-button" :aria-label="`重命名项目 ${project.name}`" title="重命名项目" :disabled="busy" @click="rename(target(project))"><Pencil :size="15" /></button><button class="icon-button file-delete" :aria-label="`删除项目 ${project.name}`" title="删除项目" :disabled="busy" @click="remove(target(project))"><Trash2 :size="15" /></button><button class="outline" :aria-label="`打开项目 ${project.name}`" :disabled="busy" @click="emit('open', project.id)">打开</button></div>
          <details v-if="project.pages.length" class="managed-pages"><summary><ChevronRight :size="13" />管理 {{ project.pages.length }} 个页面</summary><div v-for="page in project.pages" :key="page.id" class="managed-row page-file"><FileCode2 :size="17" class="file-kind" /><div class="managed-title"><b>{{ page.title }}</b><small :title="page.path">{{ page.path }} · v{{ page.version }}</small></div><button class="icon-button" :aria-label="`重命名页面 ${page.title}`" title="重命名页面" :disabled="busy" @click="rename(target(project, page))"><Pencil :size="14" /></button><button class="icon-button file-delete" :aria-label="`删除页面 ${page.title}`" title="删除页面" :disabled="busy" @click="remove(target(project, page))"><Trash2 :size="14" /></button></div></details>
        </article>
        <p v-if="!visibleProjects.length && !busy" class="file-empty">{{ query ? '没有匹配的项目或页面' : '还没有项目，可以从顶部导入或新建。' }}</p>
      </template>
      <template v-else>
        <div v-if="trash.length && !query" class="trash-bar"><span>回收站不会自动清空，不要的可以彻底删除</span><button type="button" class="text-button danger-text" :disabled="busy" @click="askPurge({ all: true })"><Trash2 :size="14" />清空回收站</button></div>
        <article v-for="item in visibleTrash" :key="item.project_id + (item.page_id || '')" class="managed-row recycled-row"><component :is="item.kind === 'project' ? FolderOpen : FileCode2" :size="21" class="file-kind" /><div class="managed-title"><b>{{ item.name }}</b><small>{{ item.kind === 'project' ? `项目 · ${item.page_count} 个页面` : `页面 · ${item.project_name}` }} · {{ date(item.deleted_at) }} 删除</small></div><button class="outline" :aria-label="`恢复${item.kind === 'project' ? '项目' : '页面'} ${item.name}`" :disabled="busy" @click="restore(item)"><RotateCcw :size="14" />恢复</button><button class="icon-button file-delete" :aria-label="`彻底删除${item.kind === 'project' ? '项目' : '页面'} ${item.name}`" title="彻底删除（不能恢复）" :disabled="busy" @click="askPurge(item)"><Trash2 :size="15" /></button></article>
        <p v-if="!visibleTrash.length && !busy" class="file-empty">{{ query ? '回收站中没有匹配结果' : '回收站是空的' }}</p>
      </template>
    </div>
    <p class="field-hint">{{ view === 'trash' ? '彻底删除只删工作区里的副本，你电脑上最初导入的文件不受影响。' : '删除先放进回收站；在回收站里可以恢复，也可以彻底删除。' }}</p>
  </div>
</template>

<style scoped>
.trash-bar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:2px 0 10px;font-size:12px;color:var(--muted);border-bottom:1px solid var(--line)}
.danger-text{display:inline-flex;align-items:center;gap:5px;color:var(--danger)!important;font-size:12.5px}
.file-tabs{display:flex;gap:22px;border-bottom:1px solid var(--line);margin:20px 0 16px}
.file-tabs button{position:relative;padding:0 0 12px;font-size:13px;color:var(--muted)}
.file-tabs button[aria-selected=true]{color:var(--primary);font-weight:600}
.file-tabs button[aria-selected=true]:after{content:'';position:absolute;bottom:-1px;left:0;right:0;height:2px;background:var(--primary)}
.file-tabs button span{font-size:11px;border-radius:4px;padding:1px 5px;background:var(--quiet)}
.file-search{display:flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:6px;padding:9px 11px;color:var(--muted);margin-bottom:12px}
.file-search input{border:0;min-width:0;flex:1;background:transparent;font-size:13px;color:var(--ink);outline:none}
.file-list{max-height:46vh;min-height:120px;overflow:auto}
.managed-project{border-bottom:1px solid var(--line);padding:12px 0}
.managed-row{display:flex;align-items:center;gap:10px;min-width:0}
.file-kind{color:var(--primary);flex-shrink:0}
.managed-title{display:flex;flex-direction:column;gap:6px;min-width:0;flex:1}
.managed-title b{font-size:13px;font-weight:550;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.managed-title small{font-size:11px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.managed-title small span{color:var(--primary)}
.managed-row .icon-button{width:28px;height:30px}
.file-delete:hover:not(:disabled){color:#b13b3b;background:#fdf1f1}
.managed-pages{margin:10px 0 0 31px}
.managed-pages summary{display:flex;align-items:center;gap:4px;list-style:none;cursor:pointer;font-size:11px;color:var(--muted);padding:3px 0}
.managed-pages summary::-webkit-details-marker{display:none}
.managed-pages[open]>summary>svg{transform:rotate(90deg)}
.page-file{padding:10px 0}
.recycled-row{border-bottom:1px solid var(--line);padding:16px 0}
.file-empty{text-align:center;color:var(--muted);font-size:13px;padding:45px 15px}
.file-action-box{border:1px solid var(--line);border-radius:8px;padding:16px;background:var(--quiet);margin:14px 0}
.file-action-box h3,.file-action-box label{font-size:14px;font-weight:600;line-height:1.6;overflow-wrap:anywhere}
.file-action-box p{font-size:12px;color:var(--muted);line-height:1.8;margin:8px 0}
.file-action-box input{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:5px;margin-top:10px;background:white}
.file-action-buttons{display:flex;gap:10px;justify-content:flex-end;margin-top:12px}
.delete-confirm{background:#fffbfa;border-color:#ecdcd8}
.danger-button{background:#b13b3b;color:white;border-radius:6px;padding:8px 12px;font-size:13px}
.danger-button:hover:not(:disabled){background:#963232}
.file-feedback{color:var(--primary);background:var(--primary-soft);border-radius:6px;padding:10px 12px;font-size:12px;margin:10px 0}
.file-loading{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted);padding:8px 0}
.form-error{display:flex;gap:12px;align-items:center;justify-content:space-between}
@media(max-width:540px){.managed-row{gap:7px}.managed-row .outline{padding:6px 8px;font-size:12px}.managed-pages{margin-left:25px}.file-list{max-height:42vh}.file-action-box{padding:12px}}
</style>
