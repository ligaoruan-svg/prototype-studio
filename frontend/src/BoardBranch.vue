<script setup>
import { ArrowRight, ChevronRight, ChevronDown } from 'lucide-vue-next'
import SceneCard from './SceneCard.vue'
import InlineFocus from './InlineFocus.vue'
import CardExtras from './CardExtras.vue'
import BoardBranch from './BoardBranch.vue'
// 一条按钮链：「新增因子 →」弹窗卡片，后面接着它里面再点开的弹窗。
// 后续默认收起，只展开当前路径（选中的、搜到的、正在编辑的），不然越往右越宽
defineProps({ node: Object, styles: Object, frame: Object, picked: Object, mode: String, open: Object, patch: Object, focus: [Number, null], route: String, focusWidth: Number })
defineEmits(['pick', 'edit', 'play', 'refind', 'toggle', 'close', 'open', 'goto', 'fix'])
</script>
<template>
  <div class="branch">
    <span class="edge" :title="node.label">{{ node.label }}<ArrowRight :size="12" /></span>
    <!-- 正在编辑 / 交互的那张：原地放大，不切屏 -->
    <InlineFocus v-if="focus === node.id" :node="node" :route="route" :styles="styles" :frame="frame" :picked="picked" :mode="mode" :patch="patch" :crumb="node.crumb" :width="focusWidth" @pick="$emit('pick', $event)" @edit="$emit('edit', $event)" @play="$emit('play', $event)" @close="$emit('close')" @open="$emit('open', $event)" @goto="$emit('goto', $event)" />
    <div v-else class="branch-card">
      <SceneCard :node="node" :styles="styles" :frame="frame" :picked="picked" :mode="mode" :crumb="node.crumb" :notes="node.notes" :width="336" :patch="patch" compact @pick="$emit('pick', $event)" @edit="$emit('edit', $event)" @play="$emit('play', $event)" @refind="$emit('refind')" @fix="$emit('fix', $event)" />
      <CardExtras :links="node.links" :dead="node.dead" @goto="$emit('goto', $event)" />
    </div>
    <!-- 收放只有一个开关，永远在卡片右边同一个位置：收着显示「后续 N ▸」，开着显示「▾ 收起」 -->
    <template v-if="node.children.length">
      <button type="button" class="more" :class="{ opened: open.has(node.id) }" :aria-expanded="open.has(node.id)" :title="open.has(node.id) ? '收起后面的视图' : `展开「${node.title}」里还能打开的 ${node.children.length} 个视图`" @click="$emit('toggle', node.id)">
        <template v-if="open.has(node.id)"><ChevronDown :size="13" />收起</template>
        <template v-else>后续 {{ node.children.length }} 个<ChevronRight :size="13" /></template>
      </button>
      <div v-if="open.has(node.id)" class="branch-children">
        <BoardBranch v-for="child in node.children" :key="child.id" :node="child" :styles="styles" :frame="frame" :picked="picked" :mode="mode" :open="open" :patch="patch" :focus="focus" :route="route" :focus-width="focusWidth" @pick="$emit('pick', $event)" @edit="$emit('edit', $event)" @play="$emit('play', $event)" @refind="$emit('refind')" @toggle="$emit('toggle', $event)" @close="$emit('close')" @open="$emit('open', $event)" @goto="$emit('goto', $event)" @fix="$emit('fix', $event)" />
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
.more.opened{color:var(--muted);background:#fff;border:1px solid var(--line)}
.more.opened:hover{color:var(--ink)}
</style>
