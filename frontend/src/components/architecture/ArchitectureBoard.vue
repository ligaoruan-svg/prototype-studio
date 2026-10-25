<script setup>
// 架构：原型的镜子。页面树跟着原型自动读出来；在树里改了，底下列着还有哪些没同步，点「同步到原型」交给左边对话里的 AI 只改这几处。
// 用 AI 做原型都在左边对话里；这里只负责看和改结构。「⋯」里是用文字编辑和照原型重读
import { computed, inject, ref, watch } from 'vue'
import { ArrowUpRight, Check, ChevronDown, ChevronUp, ListTree, LoaderCircle, MoreHorizontal, Network, RotateCcw, Undo2, X } from 'lucide-vue-next'
import ArchNode from './ArchNode.vue'
import ArchDetail from './ArchDetail.vue'
import ArchOutline from './ArchOutline.vue'
import { NODE_TYPES, changeLabel } from '../../lib/architecture.js'
import { t } from '../../lib/i18n.js'

const s = inject('studio')
const { arch, archCounts, archBusy, archError, archView, archSelected, archShowDesc, archQuery, archRemoved,
  archHistory, archChanges, archReading, locked, sourceInfo } = s
const moreOpen = ref(false), changesOpen = ref(false), main = ref(null)
watch(archView, () => { if (main.value) { main.value.scrollLeft = 0; main.value.scrollTop = 0 } })
const hasPage = computed(() => (sourceInfo.value.source || '').length > 400)
const levels = [{ v: 1, label: '模块' }, { v: 2, label: '菜单页' }, { v: 3, label: '页签' }, { v: 99, label: '全部' }]
const counts = computed(() => {
  const c = archCounts.value || {}
  return [[c.modules, '{0} 个模块'], [c.pages, '{0} 个菜单页'], [c.tabs, '{0} 个页签'], [c.drills, '{0} 个下钻页'], [c.layers, '{0} 个弹窗 / 抽屉']]
    .filter(([n]) => n).map(([n, label]) => t(label, [n]))
})
const changes = computed(() => archChanges.value.map(c => ({ ...c, label: changeLabel(c) })))
function pickChange(c) { if (c.kind !== 'remove') { archView.value = 'tree'; s.archSelect('node', c.id) } }
function root() { s.archSelect('root', 'root') }
function more(action) { moreOpen.value = false; action() }
</script>

<template>
  <section class="arch-board" :aria-label="$t('架构')" @click="s.archSelect(null); moreOpen = false">
    <header class="arch-bar" @click.stop>
      <div class="arch-title"><Network :size="16" /><b>{{ $t('架构') }}</b></div>
      <div v-if="arch && archView === 'outline'" class="arch-views" role="tablist"><button role="tab" @click="archView = 'tree'">{{ $t('页面树') }}</button>
        <button role="tab" aria-selected="true" class="active extra" @click="archView = 'tree'">{{ $t('文字编辑') }}<X :size="12" :aria-label="$t('关闭')" /></button></div>
      <div v-if="arch" class="arch-tools">
        <div class="arch-pop-wrap"><button class="icon-button" :title="$t('更多')" :aria-label="$t('更多')" :aria-expanded="moreOpen" @click="moreOpen = !moreOpen"><MoreHorizontal :size="16" /></button>
          <div v-if="moreOpen" class="arch-pop arch-ai arch-more"><button @click="more(() => { s.archSelect(null); archView = 'outline' })"><ListTree :size="14" /><span><b>{{ $t('用文字编辑') }}</b>{{ $t('整份架构写成一段缩进文字，适合一次改很多、粘贴 Excel 功能清单') }}</span></button>
            <button :disabled="!hasPage" @click="more(s.discardChanges)"><RotateCcw :size="14" /><span><b>{{ $t('照原型重新读') }}</b>{{ $t('丢掉还没同步的改动，按原型现在的样子重新读一遍（可以撤销）') }}</span></button></div></div>
        <button class="icon-button" :disabled="!archHistory.length" :title="$t('撤销')" :aria-label="$t('撤销')" @click="s.undoArch()"><Undo2 :size="15" /></button>
        <span class="arch-saving"><LoaderCircle v-if="archBusy === 'saving'" :size="13" class="spin" /></span>
      </div>
      <button class="icon-button arch-close" :title="$t('回到预览 · Esc')" :aria-label="$t('回到预览')" @click="s.showPreview()"><X :size="16" /></button>
    </header>

    <div v-if="arch && archView === 'tree'" class="arch-sub" @click.stop>
      <input v-model="archQuery" class="arch-search" :placeholder="$t('搜索节点')" :aria-label="$t('搜索节点')">
      <div class="arch-level" role="group" :aria-label="$t('展开到')"><span>{{ $t('展开到') }}</span><button v-for="l in levels" :key="l.v" :class="{ active: s.archLevel.value === l.v }" @click="s.setLevel(l.v)">{{ $t(l.label) }}</button></div>
      <label class="arch-check"><input v-model="archShowDesc" type="checkbox">{{ $t('显示介绍') }}</label>
      <label class="arch-check"><input v-model="s.archShowFields.value" type="checkbox">{{ $t('展开字段') }}</label>
      <span class="arch-counts" :title="counts.join(' · ')">{{ counts.join(' · ') }}</span>
    </div>

    <div v-if="s.archMissing.value" class="arch-error" role="alert" @click.stop><span>{{ $t('原型里没找到：{0}，AI 可能没做出来', [s.archMissing.value.names.map(n => '「' + n + '」').join('、')]) }}</span><button class="outline" @click="s.restoreMissing()">{{ $t('放回去再同步') }}</button><button class="icon-button" :aria-label="$t('关闭')" @click="s.archMissing.value = null"><X :size="13" /></button></div>
    <div v-if="archError" class="arch-error" role="alert" @click.stop><span>{{ $t(archError) }}</span><button class="icon-button" :aria-label="$t('关闭')" @click="archError = ''"><X :size="13" /></button></div>

    <!-- 还没有页面树：有原型就从原型读（展开完自动出来）；没有原型就去左边对话里说要做什么，或者自己先编 -->
    <div v-if="!arch" class="arch-empty" @click.stop>
      <div class="arch-empty-card">
        <h2>{{ $t('原型的页面树') }}</h2>
        <template v-if="hasPage">
          <p v-if="archReading" class="arch-reading"><LoaderCircle :size="15" class="spin" />{{ $t('正在从原型读页面：把每个菜单页、弹窗点一遍，读完这里自动出来') }}</p>
          <template v-else><p>{{ $t('从原型读出菜单、页签、弹窗和字段，不用 AI，几秒到一两分钟。') }}</p>
            <button class="primary" @click="s.readPrototype()"><Network :size="15" />{{ $t('从原型读出来') }}</button></template>
        </template>
        <template v-else>
          <p>{{ $t('先在左边对话里说要做什么系统，原型做出来以后，这里自动长出页面树。也可以先自己把结构编好，再同步到原型。') }}</p>
          <div class="arch-start-row"><button class="outline" @click="s.startBlank()">{{ $t('在页面树里一个个加') }}</button>
            <button class="outline" @click="s.startBlank('outline')"><ListTree :size="15" />{{ $t('用文字写 / 粘贴功能清单') }}</button></div>
        </template>
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
              <div v-if="archSelected?.kind === 'root'" class="an-tools" @click.stop><button @click="s.archAdd('', 'module')">{{ $t('+ 模块') }}</button><button @click="s.archAdd('', 'page')">{{ $t('+ 菜单页') }}</button></div>
            </div>
            <div v-if="arch.nodes.length" class="an-kids"><div v-for="child in arch.nodes" :key="child.id" class="an-kid"><ArchNode :node="child" :depth="0" :siblings="arch.nodes" /></div></div>
            <button v-else class="arch-add-first" @click.stop="s.archAdd('', 'module')">{{ $t('+ 加一个模块') }}</button>
          </div>
          <p class="arch-legend"><span v-for="(v, k) in NODE_TYPES" :key="k" class="an-legend" :class="k">{{ $t(v.label) }}</span></p>
        </div>
        <ArchOutline v-else />
      </div>
      <ArchDetail v-if="archSelected" class="arch-side" @click.stop />
    </div>

    <!-- 底下：和原型对不对得上。改了就列出来，点「同步到原型」 -->
    <footer v-if="arch" class="arch-foot" @click.stop>
      <div class="arch-order" :class="{ open: changesOpen }">
        <template v-if="archBusy === 'sync'"><LoaderCircle :size="14" class="spin" /><b>{{ $t('正在同步到原型') }}</b><span class="arch-muted">{{ $t('进度看左边对话') }}</span></template>
        <template v-else-if="changes.length"><b class="arch-pending">{{ $t('{0} 处还没同步到原型', [changes.length]) }}</b>
          <button class="arch-order-toggle" :aria-expanded="changesOpen" @click="changesOpen = !changesOpen"><ChevronUp v-if="!changesOpen" :size="13" /><ChevronDown v-else :size="13" />{{ changesOpen ? $t('收起') : $t('展开') }}</button>
          <div class="arch-order-list"><button v-for="c in changes" :key="c.kind + c.id" class="arch-order-item" :class="c.kind" @click="pickChange(c)">{{ c.label }}</button></div></template>
        <template v-else-if="archReading"><LoaderCircle :size="14" class="spin" /><span class="arch-muted">{{ $t('正在从原型读…') }}</span></template>
        <template v-else><Check :size="14" class="arch-ok" /><span class="arch-muted">{{ $t('和原型一致 · AI 在左边改完原型，这里会自动跟着变') }}</span></template>
      </div>
      <button v-if="changes.length && archBusy !== 'sync' && s.archSynced.value" class="quiet" :disabled="!hasPage" @click="s.discardChanges()">{{ $t('放弃改动') }}</button>
      <button class="primary arch-go" :disabled="locked || !changes.length || archBusy === 'sync'" @click="s.syncToPrototype()">
        <span><b><ArrowUpRight :size="14" />{{ $t('同步到原型') }}</b><small>{{ changes.length ? $t('只改这 {0} 处', [changes.length]) : $t('没有要同步的') }}</small></span></button>
    </footer>

    <div v-if="archRemoved" class="arch-undo" @click.stop><span>{{ archRemoved.impact ? $t('已删除「{0}」（{1}）', [archRemoved.name, archRemoved.impact]) : $t('已删除「{0}」', [archRemoved.name]) }}</span><button @click="s.undoArch()">{{ $t('撤销') }}</button></div>
  </section>
</template>
