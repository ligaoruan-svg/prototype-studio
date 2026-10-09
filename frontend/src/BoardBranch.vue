<script setup>
import { ArrowRight } from 'lucide-vue-next'
import SceneCard from './SceneCard.vue'
import BoardBranch from './BoardBranch.vue'
// 一条按钮链：「新增因子 →」弹窗卡片，后面接着它里面再点开的弹窗。谁打开了谁一眼就能看出来
defineProps({ node: Object, styles: Object, frame: Object, picked: Object, mode: String })
defineEmits(['pick', 'open', 'focus', 'play'])
</script>
<template>
  <div class="branch">
    <span class="edge" :title="node.label">{{ node.label }}<ArrowRight :size="12" /></span>
    <div class="branch-card">
      <SceneCard :node="node" :styles="styles" :frame="frame" :picked="picked" :mode="mode" :crumb="node.crumb" :notes="node.notes" compact @pick="$emit('pick', $event)" @open="$emit('open', $event)" @focus="$emit('focus', $event)" @play="$emit('play', $event)" />
    </div>
    <div v-if="node.children.length" class="branch-children">
      <BoardBranch v-for="child in node.children" :key="child.id" :node="child" :styles="styles" :frame="frame" :picked="picked" :mode="mode" @pick="$emit('pick', $event)" @open="$emit('open', $event)" @focus="$emit('focus', $event)" @play="$emit('play', $event)" />
    </div>
  </div>
</template>
<style scoped>
.branch{display:flex;align-items:flex-start;gap:10px}
.edge{display:inline-flex;align-items:center;gap:5px;width:max-content;max-width:170px;margin-top:14px;padding:5px 10px;border-radius:12px;background:#fff;border:1px solid var(--line);color:var(--muted);font-size:11.5px;line-height:1.45;flex-shrink:0;overflow-wrap:anywhere}
.edge svg{color:var(--subtle);flex-shrink:0}
.branch-card{width:360px;flex-shrink:0}
.branch-children{display:flex;flex-direction:column;gap:14px;padding-left:12px;border-left:1.5px solid var(--line)}
</style>
