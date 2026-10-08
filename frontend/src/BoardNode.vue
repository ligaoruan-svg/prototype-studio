<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowRight, ExternalLink } from 'lucide-vue-next'
import { cardDocument, thumbFrame } from './probeTree.js'
import BoardNode from './BoardNode.vue'
const props = defineProps({ node: Object, styles: Object, frame: Object, cardWidth: Number, picked: Object })
const emit = defineEmits(['open', 'pick'])
const iframe = ref(null)
const doc = computed(() => cardDocument(props.styles, props.node.html, { pickable: true }))
// 卡片越大越好点：中、大档时允许放大到 0.9，小档保持缩略图
const thumb = computed(() => thumbFrame(props.node.box, props.cardWidth, Math.round(props.cardWidth * 1.15), props.cardWidth > 300 ? 0.9 : 0.6))
const rels = computed(() => props.picked?.nodeId === props.node.id ? props.picked.rels : [])
function show() { iframe.value?.contentWindow?.postMessage({ type: 'CARD_SHOW', rels: [...rels.value] }, '*') }
watch(rels, show)
function listen(event) {
  if (event.source !== iframe.value?.contentWindow || event.data?.source !== 'pa-card') return
  if (event.data.type === 'CARD_PICK') emit('pick', { node: props.node, items: event.data.items })
}
onMounted(() => window.addEventListener('message', listen))
onUnmounted(() => window.removeEventListener('message', listen))
</script>
<template>
  <div class="bn">
    <span class="bn-edge" :title="node.label">{{ node.label }}<ArrowRight :size="12" /></span>
    <div class="board-card" :class="{ picked: rels.length }" :style="{ width: cardWidth + 16 + 'px' }">
      <span class="thumb" :style="{ height: thumb.height + 'px' }">
        <iframe ref="iframe" sandbox="allow-scripts" :title="`${node.title} · 点选要改的地方`" :srcdoc="doc" :style="{ width: frame.w + 'px', height: frame.h + 'px', transform: thumb.transform }" @load="show"></iframe>
      </span>
      <div class="card-foot">
        <span class="card-title">{{ node.title }}</span>
        <button type="button" class="card-open" :title="`在预览里打开「${node.title}」，可以真的点一点`" @click="$emit('open', node)"><ExternalLink :size="13" />预览里打开</button>
      </div>
    </div>
    <div v-if="node.children.length" class="bn-children">
      <BoardNode v-for="child in node.children" :key="child.id" :node="child" :styles="styles" :frame="frame" :card-width="cardWidth" :picked="picked" @open="$emit('open', $event)" @pick="$emit('pick', $event)" />
    </div>
  </div>
</template>
<style scoped>
.bn{display:flex;align-items:flex-start;gap:10px}
.bn-edge{display:inline-flex;align-items:center;gap:5px;width:max-content;max-width:170px;margin-top:14px;padding:5px 10px;border-radius:12px;background:#fff;border:1px solid var(--line);color:var(--muted);font-size:11.5px;line-height:1.45;flex-shrink:0;overflow-wrap:anywhere}
.bn-edge svg{color:var(--subtle)}
.board-card{display:flex;flex-direction:column;gap:8px;padding:8px 8px 8px;background:#fff;border:1px solid var(--line);border-radius:12px;box-shadow:0 1px 3px #3722170a;transition:border-color .15s,box-shadow .15s;flex-shrink:0}
.board-card:hover{border-color:#d9cfc6;box-shadow:0 6px 18px #3722170f}
.board-card.picked{border-color:var(--primary);box-shadow:0 0 0 3px #b8532f1a}
.thumb{display:block;position:relative;overflow:hidden;border-radius:7px;background:var(--quiet)}
.thumb iframe{position:absolute;left:0;top:0;border:0;transform-origin:0 0;background:transparent}
.card-foot{display:flex;align-items:center;gap:8px;min-width:0;padding:0 2px 0 3px}
.card-title{flex:1;min-width:0;font-size:13px;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card-open{gap:4px;padding:4px 7px;border-radius:8px;font-size:11.5px;color:var(--muted)}
.card-open:hover{background:var(--quiet);color:var(--primary)}
.bn-children{display:flex;flex-direction:column;gap:14px;padding-left:12px;border-left:1.5px solid var(--line)}
@media (prefers-reduced-motion: reduce){.board-card{transition:none}}
</style>
