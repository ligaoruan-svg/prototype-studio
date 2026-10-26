<script setup>
// 架构：只有一块画布，上面是这个原型的页面树。可以手动加、改、删、挪；选中时右边出详情改字段。
// 改结构也可以在对话的「架构」模式里跟 AI 说（只改画布，不碰原型）。
// 画布上规划了、原型里还没有的卡片是虚线，点「让 AI 做出来」把话填进输入框；
// 画布上改了的（加、删、改名、改字段）右下角记着几处，点「同步到原型」把这几处填进输入框交给 AI
import { computed, inject, ref } from 'vue'
import { ArrowUpRight, ChevronDown, ChevronUp, LoaderCircle, RefreshCw, Undo2, X } from 'lucide-vue-next'
import ArchNode from './ArchNode.vue'
import ArchDetail from './ArchDetail.vue'
import { NODE_TYPES, changeLabel } from '../../lib/architecture.js'

const s = inject('studio')
const { arch, archError, archSelected, archShowDesc, archRemoved, archHistory } = s
const reading = computed(() => s.archReading())
const changes = computed(() => s.archChanges.value.map(c => ({ ...c, label: changeLabel(c) })))
const listOpen = ref(false)
function pick(c) { if (c.kind !== 'remove') s.archSelect('node', c.id) }
function root() { s.archSelect('root', 'root') }
</script>

<template>
  <section class="arch-board" :aria-label="$t('架构')" @click="s.archSelect(null)">
    <div class="arch-float" @click.stop>
      <span v-if="reading" class="arch-reading"><LoaderCircle :size="13" class="spin" />{{ $t('正在从原型读页面…') }}</span>
      <button v-else class="icon-button" :title="$t('从原型读一遍：原型改过、画布没跟上时点。画布上没同步的改动不会丢')" :aria-label="$t('从原型读一遍')" @click="s.readPrototype()"><RefreshCw :size="14" /></button>
      <button class="icon-button" :disabled="!archHistory.length" :title="$t('撤销')" :aria-label="$t('撤销')" @click="s.undoArch()"><Undo2 :size="15" /></button>
      <button class="icon-button" :title="$t('回到预览 · Esc')" :aria-label="$t('回到预览')" @click="s.showPreview()"><X :size="16" /></button>
    </div>
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
          <p class="arch-legend"><span v-for="(v, k) in NODE_TYPES" :key="k" class="an-legend" :class="k">{{ $t(v.label) }}</span><span class="an-legend planned">{{ $t('虚线：原型里还没有') }}</span></p>
        </div>
      </div>
      <ArchDetail v-if="archSelected" class="arch-side" @click.stop />
    </div>

    <!-- 还没同步到原型的：右下角记着，点开看是哪几处 -->
    <div v-if="changes.length" class="arch-sync" @click.stop>
      <div v-if="listOpen" class="arch-sync-list"><b>{{ $t('画布上改了，原型里还没有：') }}</b><button v-for="c in changes" :key="c.kind + c.id" :class="c.kind" @click="pick(c)">{{ c.label }}</button></div>
      <div class="arch-sync-bar"><button class="quiet" :aria-expanded="listOpen" @click="listOpen = !listOpen"><ChevronDown v-if="listOpen" :size="13" /><ChevronUp v-else :size="13" />{{ $t('{0} 处没同步', [changes.length]) }}</button>
        <button class="primary" :disabled="s.locked.value" :title="$t('把这几处填进输入框、切到「自动」，你看一眼再发')" @click="listOpen = false; s.syncToPrototype()"><ArrowUpRight :size="14" />{{ $t('同步到原型') }}</button></div>
    </div>
    <div v-if="archRemoved" class="arch-undo" @click.stop><span>{{ archRemoved.impact ? $t('已删除「{0}」（{1}）', [archRemoved.name, archRemoved.impact]) : $t('已删除「{0}」', [archRemoved.name]) }}</span><button @click="s.undoArch()">{{ $t('撤销') }}</button></div>
  </section>
</template>
