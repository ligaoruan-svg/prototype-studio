<script setup>
// 架构：只有一块画布，上面是这个原型的页面树。可以手动加、改、删、挪；选中时右边出详情改字段。
// 改结构也可以在对话的「架构」模式里跟 AI 说（只改画布，不碰原型）。
// 画布上规划了、原型里还没有的卡片是虚线；画布上改了的（加、删、改名、改字段）右下角记着几处。
// 「同步到原型」（底部，整个）和卡片工具条上的「同步」（这一块）一直都能点：有改动交代改动，没有就让 AI 照画布核对
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ArrowUpRight, Check, ChevronDown, ChevronUp, Copy, Download, FileText, LoaderCircle, RefreshCw, Sheet, Undo2, X } from 'lucide-vue-next'
import ArchNode from './ArchNode.vue'
import ArchDetail from './ArchDetail.vue'
import { NODE_TYPES, changeLabel } from '../../lib/architecture.js'
import { download, toCsv, toMarkdown } from '../../lib/archExport.js'

const s = inject('studio')
const { arch, archError, archSelected, archShowDesc, archRemoved, archHistory } = s
const reading = computed(() => s.archReading())
// 展开到哪一层：一个个点开太麻烦，一下全展开
const levels = [{ v: 1, label: '模块' }, { v: 2, label: '菜单页' }, { v: 3, label: '页签' }, { v: 99, label: '全部' }]
const changes = computed(() => s.archChanges.value.map(c => ({ ...c, label: changeLabel(c) })))
const listOpen = ref(false)
function pick(c) { if (c.kind !== 'remove') s.archSelect('node', c.id) }
function root() { s.archSelect('root', 'root') }
// 导出：Markdown 大纲（贴进需求文档、导入 XMind）、表格（Excel 打开）、或者直接复制成文字
const exportOpen = ref(false)
const closeExport = () => { exportOpen.value = false }
onMounted(() => document.addEventListener('click', closeExport))
onUnmounted(() => document.removeEventListener('click', closeExport))
const fileName = ext => `${(arch.value?.name || '页面树').replace(/[\\/:*?"<>|]/g, '_')}-架构.${ext}`
function exportAs(kind) {
  exportOpen.value = false
  const tracked = !!s.archBase.value
  if (kind === 'md') download(fileName('md'), toMarkdown(arch.value, { tracked }), 'text/markdown;charset=utf-8')
  else if (kind === 'csv') download(fileName('csv'), toCsv(arch.value, { tracked }), 'text/csv;charset=utf-8')
  else s.copyMessage(toMarkdown(arch.value, { tracked }))
}
</script>

<template>
  <section class="arch-board" :aria-label="$t('架构')" @click="s.archSelect(null)">
    <!-- 上面一条固定的：展开到哪一层、显示介绍 / 字段；右边从原型读、撤销、关闭 -->
    <header class="arch-head" @click.stop>
      <div class="arch-level" role="group" :aria-label="$t('展开到')"><span>{{ $t('展开到') }}</span><button v-for="l in levels" :key="l.v" :class="{ active: s.archLevel.value === l.v }" @click="s.setLevel(l.v)">{{ $t(l.label) }}</button></div>
      <label class="arch-check"><input v-model="archShowDesc" type="checkbox">{{ $t('显示介绍') }}</label>
      <label class="arch-check"><input v-model="s.archShowFields.value" type="checkbox">{{ $t('展开字段') }}</label>
      <div class="arch-head-tools">
        <span v-if="reading" class="arch-reading"><LoaderCircle :size="13" class="spin" />{{ $t('正在从原型读页面…') }}</span>
        <button v-else class="icon-button" :title="$t('从原型读一遍：原型改过、画布没跟上时点。画布上没同步的改动不会丢')" :aria-label="$t('从原型读一遍')" @click="s.readPrototype()"><RefreshCw :size="14" /></button>
        <div class="arch-export" @click.stop><button class="icon-button" :disabled="!arch?.nodes?.length" :aria-expanded="exportOpen" :title="$t('导出架构')" :aria-label="$t('导出架构')" @click="exportOpen = !exportOpen"><Download :size="15" /></button>
          <div v-if="exportOpen" class="arch-export-menu" role="menu"><button role="menuitem" @click="exportAs('md')"><FileText :size="14" /><span><b>{{ $t('Markdown 大纲') }}</b><small>{{ $t('贴进需求文档；XMind、幕布能导入成脑图') }}</small></span></button><button role="menuitem" @click="exportAs('csv')"><Sheet :size="14" /><span><b>{{ $t('表格') }}</b><small>{{ $t('一行一个页面 / 按钮 / 弹窗，Excel 直接打开') }}</small></span></button><button role="menuitem" @click="exportAs('copy')"><Copy :size="14" /><span><b>{{ $t('复制成文字') }}</b><small>{{ $t('直接粘贴到飞书、钉钉、微信') }}</small></span></button></div></div>
        <button class="icon-button" :disabled="!archHistory.length" :title="$t('撤销')" :aria-label="$t('撤销')" @click="s.undoArch()"><Undo2 :size="15" /></button>
        <button class="icon-button" :title="$t('回到预览 · Esc')" :aria-label="$t('回到预览')" @click="s.showPreview()"><X :size="16" /></button>
      </div>
    </header>
    <div v-if="archError" class="arch-error" role="alert" @click.stop><span>{{ $t(archError) }}</span><button class="icon-button" :aria-label="$t('关闭')" @click="archError = ''"><X :size="13" /></button></div>

    <div class="arch-body">
      <div class="arch-main" @click="s.archSelect(null)">
        <div v-if="!arch" class="arch-wait"><LoaderCircle :size="18" class="spin" />{{ $t('正在从原型读页面：和「展开」一样把每个菜单页、弹窗点一遍，读完画布自动出来') }}</div>
        <div v-else class="arch-tree">
          <div class="an-row root-row">
            <div class="an-card root" :class="{ selected: archSelected?.kind === 'root' }" @click.stop="root">
              <div class="an-head"><span class="an-type">{{ $t('系统') }}</span><b>{{ arch.name || $t('未命名系统') }}</b></div>
              <p v-if="archShowDesc && arch.summary" class="an-desc">{{ arch.summary }}</p>
              <div v-if="archSelected?.kind === 'root'" class="an-tools" @click.stop><button @click="s.archAdd('', 'module')">{{ $t('+ 模块') }}</button><button @click="s.archAdd('', 'page')">{{ $t('+ 菜单页') }}</button></div>
            </div>
            <div v-if="arch.nodes.length" class="an-kids"><div v-for="child in arch.nodes" :key="child.id" class="an-kid"><ArchNode :node="child" :depth="0" :siblings="arch.nodes" parent-state="in" /></div></div>
            <div v-else class="arch-add-first" @click.stop><button @click="s.archAdd('', 'module')">{{ $t('+ 加一个模块') }}</button><button @click="s.archAdd('', 'page')">{{ $t('+ 加一个菜单页') }}</button>
              <span>{{ $t('或者在左边「架构」模式里说要做什么，AI 帮你把页面树画出来') }}</span></div>
          </div>
        </div>
      </div>
      <ArchDetail v-if="archSelected" class="arch-side" @click.stop />
    </div>

    <!-- 下面一条固定的：图例；右边还没同步到原型的几处，点开看清单 -->
    <footer class="arch-foot" @click.stop>
      <p class="arch-legend"><span v-for="(v, k) in NODE_TYPES" :key="k" class="an-legend" :class="k">{{ $t(v.label) }}</span><span class="an-legend planned">{{ $t('虚线：原型里还没有') }}</span></p>
      <div class="arch-sync">
        <div v-if="listOpen && changes.length" class="arch-sync-list"><b>{{ $t('画布上改了，原型里还没有：') }}</b><button v-for="c in changes" :key="c.kind + c.id" :class="c.kind" @click="pick(c)">{{ c.label }}</button><button class="mark-synced" :disabled="s.locked.value" :title="$t('原型里其实已经有了（比如 AI 说早就做好了）：这几处不再算没同步')" @click="listOpen = false; s.acceptSynced(changes.map(c => c.id))"><Check :size="12" />{{ $t('原型里已经有了，标成已同步') }}</button></div>
        <button v-if="changes.length" class="quiet" :aria-expanded="listOpen" @click="listOpen = !listOpen"><ChevronDown v-if="listOpen" :size="13" /><ChevronUp v-else :size="13" />{{ $t('{0} 处没同步', [changes.length]) }}</button>
        <span v-else class="arch-synced"><Check :size="13" />{{ $t('没有记下的改动') }}</span>
        <button class="primary" :disabled="s.locked.value" :title="changes.length ? $t('把这几处附到对话里，发送后 AI 改原型') : $t('让 AI 照画布核对整个原型，对不上的照画布改')" @click="listOpen = false; s.syncToPrototype()"><ArrowUpRight :size="14" />{{ $t('同步到原型') }}</button>
      </div>
    </footer>
    <div v-if="archRemoved" class="arch-undo" @click.stop><span>{{ archRemoved.impact ? $t('已删除「{0}」（{1}）', [archRemoved.name, archRemoved.impact]) : $t('已删除「{0}」', [archRemoved.name]) }}</span><button @click="s.undoArch()">{{ $t('撤销') }}</button></div>
  </section>
</template>
