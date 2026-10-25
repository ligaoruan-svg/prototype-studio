<script setup>
// 架构模式：页面树 / 数据关系 / 业务流程三个视图，右边是选中项的详情，底下是生成顺序和「按架构生成」
import { computed, inject, onUnmounted, ref, watch } from 'vue'
import { AlertCircle, Check, Ruler, ChevronDown, ChevronUp, ClipboardPaste, Layers, ListTree, LoaderCircle, Network, Sparkles, Undo2, Wand2, X } from 'lucide-vue-next'
import ArchNode from './ArchNode.vue'
import ArchData from './ArchData.vue'
import ArchFlow from './ArchFlow.vue'
import ArchDetail from './ArchDetail.vue'
import ArchOutline from './ArchOutline.vue'
import { NODE_TYPES } from '../../lib/architecture.js'
import { t } from '../../lib/i18n.js'

const s = inject('studio')
const { arch, archIssues, archOrder, archCounts, archBusy, archError, archView, archSelected, archShowDesc, archQuery, archRemoved,
  archHistory, archDraft, locked, page, sourceInfo } = s
const need = ref(''), issuesOpen = ref(false), aiOpen = ref(false), rulesOpen = ref(false), main = ref(null)
// 换视图时回到左上角：三个视图宽窄不一样，留着上一个的滚动位置会看到半截
watch(archView, () => { if (main.value) { main.value.scrollLeft = 0; main.value.scrollTop = 0 } })
const hasPage = computed(() => !!page.value && (sourceInfo.value.source || '').length > 400)
const errors = computed(() => archIssues.value.filter(i => i.level === 'error').length)
const levels = [{ v: 1, label: '模块' }, { v: 2, label: '菜单页' }, { v: 3, label: '页签' }, { v: 99, label: '全部' }]
const views = [{ id: 'tree', label: '页面树' }, { id: 'outline', label: '大纲' }, { id: 'data', label: '数据关系' }, { id: 'flow', label: '业务流程' }]
// 生成顺序默认收成一行（几十页时占半屏）；点「展开」才全部列出来
const orderOpen = ref(false)
// AI 起草的进度：每秒刷一下用了多久
const now = ref(Date.now())
const ticker = setInterval(() => { if (archDraft.value) now.value = Date.now() }, 1000)
onUnmounted(() => clearInterval(ticker))
const draftSeconds = computed(() => archDraft.value ? Math.max(0, Math.round((now.value - archDraft.value.started) / 1000)) : 0)
const counts = computed(() => {
  const c = archCounts.value || {}
  return [[c.modules, '{0} 个模块'], [c.pages, '{0} 个菜单页'], [c.tabs, '{0} 个页签'], [c.drills, '{0} 个下钻页'], [c.layers, '{0} 个弹窗 / 抽屉'], [c.entities, '{0} 类数据']]
    .filter(([n]) => n).map(([n, label]) => t(label, [n]))
})
function pickIssue(issue) {
  issuesOpen.value = false
  if (issue.node) { archView.value = 'tree'; s.archSelect('node', issue.node) }
  else if (issue.entity) { archView.value = 'data'; s.archSelect('entity', issue.entity) }
  else if (issue.step) { archView.value = 'flow'; s.archSelect('step', issue.step) }
}
function draft(mode) { aiOpen.value = false; s.draftArch(mode, mode === 'refine' ? '' : need.value.trim()) }
function root() { s.archSelect('root', 'root') }
function setRules(text) { s.archSnapshot(); arch.value.rules = text.split('\n').map(v => v.trim()).filter(Boolean); s.archDirty() }
function pop(name) { issuesOpen.value = name === 'issues' && !issuesOpen.value; aiOpen.value = name === 'ai' && !aiOpen.value; rulesOpen.value = name === 'rules' && !rulesOpen.value }
</script>

<template>
  <section class="arch-board" :aria-label="$t('架构')" @click="s.archSelect(null); pop('')">
    <header class="arch-bar" @click.stop>
      <div class="arch-title"><Network :size="16" /><b>{{ $t('架构') }}</b>
        <span v-if="arch" class="arch-state" :class="arch.status">{{ arch.status === 'confirmed' ? $t('已确认') : $t('草稿') }}</span></div>
      <div v-if="arch" class="arch-views" role="tablist"><button v-for="v in views" :key="v.id" role="tab" :aria-selected="archView === v.id" :class="{ active: archView === v.id }" @click="archView = v.id">{{ $t(v.label) }}</button></div>
      <div v-if="arch" class="arch-tools">
        <div class="arch-pop-wrap"><button class="outline" :class="{ warn: errors }" @click="pop('issues')"><AlertCircle v-if="archIssues.length" :size="14" /><Check v-else :size="14" /><span class="lbl">{{ archIssues.length ? $t('一致性检查') : $t('对得上') }}</span><b v-if="archIssues.length">{{ archIssues.length }}</b></button>
          <div v-if="issuesOpen" class="arch-pop"><p v-if="!archIssues.length" class="arch-muted">{{ $t('页面、数据、流程都对得上') }}</p>
            <button v-for="(issue, i) in archIssues" :key="i" class="arch-issue" :class="issue.level" @click="pickIssue(issue)"><AlertCircle :size="13" /><span>{{ issue.text }}</span></button></div></div>
        <div class="arch-pop-wrap"><button class="outline" :disabled="archBusy === 'draft'" @click="pop('ai')"><Sparkles :size="14" />{{ $t('AI') }}</button>
          <div v-if="aiOpen" class="arch-pop arch-ai"><button :disabled="!hasPage" @click="aiOpen = false; s.fromExpand()"><Layers :size="14" /><span><b>{{ $t('照展开图重新整理（不用 AI）') }}</b>{{ $t('几秒就好：菜单、页签、弹窗、子页面照原型搭出来，会替换现在的页面树') }}</span></button>
            <button @click="draft('refine')"><Wand2 :size="14" /><span><b>{{ $t('补全') }}</b>{{ $t('给缺介绍的页面补介绍、补字段和流程，已有的不动') }}</span></button>
            <button :disabled="!hasPage" @click="draft('page')"><Network :size="14" /><span><b>{{ $t('从当前原型重新整理') }}</b>{{ $t('照着现在的原型重新起一份，会替换现在的架构') }}</span></button>
            <div class="arch-ai-need"><textarea v-model="need" rows="3" :placeholder="$t('换个需求重新起草：做什么系统、给谁用、管哪些东西')"></textarea><button class="primary" :disabled="!need.trim()" @click="draft('request')">{{ $t('重新起草') }}</button></div></div></div>
        <div class="arch-pop-wrap"><button class="outline" :title="$t('统一规则')" @click="pop('rules')"><Ruler :size="14" /><span class="lbl">{{ $t('统一规则') }}</span></button>
          <div v-if="rulesOpen" class="arch-pop arch-rules"><b>{{ $t('电脑端统一规则') }}</b><p class="arch-muted">{{ $t('生成时每一页都按这几条来，一行一条，可以改') }}</p>
            <textarea rows="11" :value="(arch.rules || []).join('\n')" @change="setRules($event.target.value)"></textarea></div></div>
        <button class="icon-button" :disabled="!archHistory.length" :title="$t('撤销')" :aria-label="$t('撤销')" @click="s.undoArch()"><Undo2 :size="15" /></button>
        <span class="arch-saving"><LoaderCircle v-if="archBusy === 'saving'" :size="13" class="spin" /></span>
      </div>
      <button class="icon-button arch-close" :title="$t('回到预览 · Esc')" :aria-label="$t('回到预览')" @click="s.showPreview()"><X :size="16" /></button>
    </header>

    <div v-if="arch" class="arch-sub" @click.stop>
      <template v-if="archView === 'tree'">
        <input v-model="archQuery" class="arch-search" :placeholder="$t('搜索节点')" :aria-label="$t('搜索节点')">
        <div class="arch-level" role="group" :aria-label="$t('展开到')"><span>{{ $t('展开到') }}</span><button v-for="l in levels" :key="l.v" :class="{ active: s.archLevel.value === l.v }" @click="s.setLevel(l.v)">{{ $t(l.label) }}</button></div>
        <label class="arch-check"><input v-model="archShowDesc" type="checkbox">{{ $t('显示介绍') }}</label>
      </template>
      <span class="arch-counts" :title="counts.join(' · ')">{{ counts.join(' · ') }}</span>
    </div>

    <div v-if="archError" class="arch-error" role="alert" @click.stop><AlertCircle :size="14" /><span>{{ $t(archError) }}</span><button class="icon-button" :aria-label="$t('关闭')" @click="archError = ''"><X :size="13" /></button></div>

    <!-- 还没有架构：自己编（大纲 / 粘贴功能清单 / 一个个加）、照现有原型整理、让 AI 起草 -->
    <div v-if="!arch" class="arch-empty" @click.stop>
      <div class="arch-empty-card">
        <h2>{{ $t('先定架构，再出页面') }}</h2>
        <p>{{ $t('把系统 → 模块 → 页面 → 功能、页面共用的数据、业务流程先理清楚，确认了再按它一页一步生成。只做电脑端。') }}</p>
        <div class="arch-start">
          <div class="arch-start-col"><b>{{ $t('自己编') }}</b>
            <button class="outline" @click="s.startBlank('outline')"><ListTree :size="15" />{{ $t('写大纲 / 粘贴功能清单') }}</button>
            <button class="quiet" @click="s.startBlank()">{{ $t('在页面树里一个个加') }}</button></div>
          <div class="arch-start-col"><b>{{ $t('照现有原型') }}</b>
            <button class="outline" :disabled="!hasPage || archBusy === 'draft'" :title="hasPage ? $t('用展开图里的菜单、页签、弹窗、子页面，几秒就好') : $t('当前原型还是空的')" @click="s.fromExpand()"><Layers :size="15" />{{ $t('照展开图整理（不用 AI）') }}</button>
            <button class="quiet" :disabled="!hasPage || archBusy === 'draft' || locked" @click="draft('page')"><Network :size="15" />{{ $t('让 AI 整理（带数据和流程）') }}</button></div>
        </div>
        <div class="arch-start-ai"><b>{{ $t('让 AI 起草') }}</b>
          <textarea v-model="need" rows="3" :placeholder="$t('用几句话说要做什么：给谁用、管哪些东西、有哪些流程。比如：设备巡检，管理员配巡检点、路线和计划，系统按周期派任务，异常推给维修系统')"></textarea>
          <button class="primary" :disabled="!need.trim() || archBusy === 'draft' || locked" @click="draft('request')"><Sparkles :size="15" />{{ $t('AI 起草架构') }}</button></div>
      </div>
    </div>

    <div v-else class="arch-body">
      <div ref="main" class="arch-main" @click="s.archSelect(null)">
        <div v-if="archView === 'tree'" class="arch-tree">
          <div class="an-row root-row">
            <div class="an-card root" :class="{ selected: archSelected?.kind === 'root' }" @click.stop="root">
              <div class="an-head"><span class="an-type">{{ $t('系统') }}</span><b>{{ arch.name || $t('未命名系统') }}</b></div>
              <p v-if="archShowDesc && arch.summary" class="an-desc">{{ arch.summary }}</p>
              <div v-if="arch.roles?.length" class="an-chips"><span v-for="r in arch.roles" :key="r" class="an-chip role">{{ r }}</span></div>
              <div v-if="archSelected?.kind === 'root'" class="an-tools" @click.stop><button @click="s.archAdd('', 'module')">{{ $t('+ 模块') }}</button></div>
            </div>
            <div v-if="arch.nodes.length" class="an-kids"><div v-for="child in arch.nodes" :key="child.id" class="an-kid"><ArchNode :node="child" :depth="0" :siblings="arch.nodes" /></div></div>
            <button v-else class="arch-add-first" @click.stop="s.archAdd('', 'module')">{{ $t('+ 加一个模块') }}</button>
          </div>
          <p class="arch-legend"><span v-for="(v, k) in NODE_TYPES" :key="k" class="an-legend" :class="k">{{ $t(v.label) }}</span></p>
        </div>
        <ArchOutline v-else-if="archView === 'outline'" />
        <ArchData v-else-if="archView === 'data'" />
        <ArchFlow v-else />
      </div>
      <ArchDetail v-if="archSelected" class="arch-side" @click.stop />
    </div>

    <footer v-if="arch" class="arch-foot" @click.stop>
      <div class="arch-order" :class="{ open: orderOpen }"><b>{{ $t('生成顺序') }}</b><span class="arch-muted">{{ $t('{0} 页 · 按数据依赖自动排', [archOrder.length]) }}</span>
        <button v-if="archOrder.length" class="arch-order-toggle" :aria-expanded="orderOpen" @click="orderOpen = !orderOpen"><ChevronUp v-if="!orderOpen" :size="13" /><ChevronDown v-else :size="13" />{{ orderOpen ? $t('收起') : $t('展开') }}</button>
        <div class="arch-order-list"><button v-for="(o, i) in archOrder" :key="o.id" class="arch-order-item" :title="(o.module ? o.module + ' › ' : '') + o.name + (o.tabs?.length ? '：' + o.tabs.join('、') : '')" @click="archView = 'tree'; s.archSelect('node', o.id)">{{ i + 1 }} {{ o.name }}<small v-if="o.tabs?.length">{{ $t('{0} 页签', [o.tabs.length]) }}</small></button><span v-if="!archOrder.length" class="arch-muted">{{ $t('还没有页面') }}</span></div></div>
      <button class="primary arch-go" :disabled="locked || !archOrder.length || archBusy === 'draft'" :title="errors ? $t('还有对不上的地方，先改好') : ''" @click="s.generateFromArch()">
        <span><b>{{ arch.status === 'confirmed' ? $t('按架构重新生成') : $t('确认架构，按架构生成') }}</b><small>{{ $t('{0} 页 · 一页一步', [archOrder.length]) }}</small></span></button>
    </footer>

    <div v-if="archRemoved" class="arch-undo" @click.stop><span>{{ archRemoved.impact ? $t('已删除「{0}」（{1}）', [archRemoved.name, archRemoved.impact]) : $t('已删除「{0}」', [archRemoved.name]) }}</span><button @click="s.undoArch()">{{ $t('撤销') }}</button></div>
    <div v-if="archBusy === 'draft'" class="arch-veil" @click.stop><LoaderCircle :size="24" class="spin" />
      <template v-if="archDraft"><span>{{ $t(archDraft.label) }}{{ archDraft.chars ? $t('，已写 {0} 字', [archDraft.chars]) : '' }} · {{ $t('{0} 秒', [draftSeconds]) }}</span>
        <small class="arch-muted">{{ $t('一般一两分钟；超过 5 分钟会自动停下') }}</small>
        <button class="outline" :disabled="!archDraft.id" @click="s.stopDraft()">{{ $t('停止') }}</button></template>
      <span v-else>{{ $t('正在整理…') }}</span></div>
  </section>
</template>
