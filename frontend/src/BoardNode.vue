<script setup>
import { computed } from 'vue'
import { ArrowRight } from 'lucide-vue-next'
import { cardDocument, thumbFrame } from './probeTree.js'
import BoardNode from './BoardNode.vue'
const props = defineProps({ node: Object, styles: Object, frame: Object })
defineEmits(['open'])
const doc = computed(() => cardDocument(props.styles, props.node.html))
const thumb = computed(() => thumbFrame(props.node.box, 248, 196))
</script>
<template>
  <div class="bn">
    <span class="bn-edge" :title="node.label">{{ node.label }}<ArrowRight :size="12" /></span>
    <button type="button" class="board-card" :title="`在预览里打开「${node.title}」`" @click="$emit('open', node)">
      <span class="thumb" :style="{ height: thumb.height + 'px' }">
        <iframe sandbox="" tabindex="-1" aria-hidden="true" loading="lazy" :srcdoc="doc" :style="{ width: frame.w + 'px', height: frame.h + 'px', transform: thumb.transform }"></iframe>
      </span>
      <span class="card-title">{{ node.title }}</span>
    </button>
    <div v-if="node.children.length" class="bn-children">
      <BoardNode v-for="child in node.children" :key="child.id" :node="child" :styles="styles" :frame="frame" @open="$emit('open', $event)" />
    </div>
  </div>
</template>
<style scoped>
.bn{display:flex;align-items:flex-start;gap:10px}
.bn-edge{display:inline-flex;align-items:center;gap:5px;width:max-content;max-width:170px;margin-top:14px;padding:5px 10px;border-radius:12px;background:#fff;border:1px solid var(--line);color:var(--muted);font-size:11.5px;line-height:1.45;flex-shrink:0;overflow-wrap:anywhere}
.bn-edge svg{color:var(--subtle)}
.board-card{display:flex;flex-direction:column;align-items:stretch;gap:8px;width:264px;padding:8px 8px 10px;background:#fff;border:1px solid var(--line);border-radius:12px;text-align:left;box-shadow:0 1px 3px #3722170a;transition:border-color .15s,box-shadow .15s,transform .15s;flex-shrink:0}
.board-card:hover{border-color:var(--primary);box-shadow:0 6px 18px #b8532f1f;transform:translateY(-1px)}
.thumb{display:block;position:relative;overflow:hidden;border-radius:7px;background:var(--quiet)}
.thumb iframe{position:absolute;left:0;top:0;border:0;transform-origin:0 0;pointer-events:none;background:transparent}
.card-title{padding:0 3px;font-size:13px;font-weight:600;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bn-children{display:flex;flex-direction:column;gap:14px;padding-left:12px;border-left:1.5px solid var(--line)}
@media (prefers-reduced-motion: reduce){.board-card{transition:none}.board-card:hover{transform:none}}
</style>
