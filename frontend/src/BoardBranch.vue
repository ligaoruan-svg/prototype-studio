<script setup>
import { ArrowRight, ChevronRight, ChevronDown } from 'lucide-vue-next'
import SceneCard from './SceneCard.vue'
import BoardBranch from './BoardBranch.vue'
// 一条按钮链：「新增因子 →」弹窗卡片，后面接着它里面再点开的弹窗。
// 后续默认收起，只展开当前路径（选中的、搜到的、正在编辑的），不然越往右越宽
defineProps({ node: Object, styles: Object, frame: Object, picked: Object, mode: String, open: Object })
defineEmits(['pick', 'edit', 'play', 'refind', 'toggle'])
</script>
<template>
  <div class="branch">
    <span class="edge" :title="node.label">{{ node.label }}<ArrowRight :size="12" /></span>
    <div class="branch-card">
      <SceneCard :node="node" :styles="styles" :frame="frame" :picked="picked" :mode="mode" :crumb="node.crumb" :notes="node.notes" :width="336" compact @pick="$emit('pick', $event)" @edit="$emit('edit', $event)" @play="$emit('play', $event)" @refind="$emit('refind')" />
    </div>
    <template v-if="node.children.length">
      <button v-if="!open.has(node.id)" type="button" class="more" :title="`展开「${node.title}」里还能打开的 ${node.children.length} 个视图`" @click="$emit('toggle', node.id)">后续 {{ node.children.length }} 个<ChevronRight :size="13" /></button>
      <div v-else class="branch-children">
        <button type="button" class="fold" title="收起后续" @click="$emit('toggle', node.id)"><ChevronDown :size="13" />收起</button>
        <BoardBranch v-for="child in node.children" :key="child.id" :node="child" :styles="styles" :frame="frame" :picked="picked" :mode="mode" :open="open" @pick="$emit('pick', $event)" @edit="$emit('edit', $event)" @play="$emit('play', $event)" @refind="$emit('refind')" @toggle="$emit('toggle', $event)" />
      </div>
    </template>
  </div>
</template>
<style scoped>
.branch{display:flex;align-items:flex-start;gap:10px}
.edge{display:inline-flex;align-items:center;gap:5px;width:max-content;max-width:160px;margin-top:12px;padding:5px 10px;border-radius:12px;background:#fff;border:1px solid var(--line);color:var(--muted);font-size:11.5px;line-height:1.45;flex-shrink:0;overflow-wrap:anywhere}
.edge svg{color:var(--subtle);flex-shrink:0}
.branch-card{width:360px;flex-shrink:0}
.more{gap:3px;margin-top:12px;padding:5px 10px;border-radius:12px;font-size:11.5px;color:var(--primary);background:var(--primary-soft);flex-shrink:0}
.more:hover{background:#f1dccf}
.branch-children{display:flex;flex-direction:column;gap:14px;padding-left:12px;border-left:1.5px solid var(--line)}
.fold{align-self:flex-start;gap:3px;padding:2px 7px;margin-bottom:-6px;border-radius:8px;font-size:11px;color:var(--muted)}
.fold:hover{background:#fff;color:var(--ink)}
</style>
