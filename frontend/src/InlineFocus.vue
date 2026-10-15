<script setup>
import { ref } from 'vue'
import { ExternalLink, PencilLine, RotateCw, Minimize2, Hand } from 'lucide-vue-next'
import SceneCard from './SceneCard.vue'
import LiveScene from './LiveScene.vue'
// 在树里原地放大的那张卡：编辑（点选 / 拉框）和交互都在这里，不切屏、不跳页。
// 收起就回到原来的小卡，树的位置不动；只有「在预览中打开」会离开展开视图，而且按钮上写明了。
defineProps({ node: Object, route: String, styles: Object, frame: Object, picked: Object, mode: String, patch: Object, crumb: String, width: Number })
defineEmits(['pick', 'edit', 'play', 'close', 'open'])
const live = ref(null)
</script>
<template>
  <article class="inline-focus" :class="{ playing: mode === 'interact' }" :style="{ width: width + 'px' }" :data-node-id="node.id">
    <header class="if-head">
      <div class="if-title"><strong>{{ node.title }}</strong><span v-if="crumb" class="if-crumb">{{ crumb }}</span></div>
      <span class="state-tag" :class="{ live: mode === 'interact' }">{{ mode === 'interact' ? '交互中 · 演示数据不保存' : mode === 'box' ? '编辑中 · 拖动框选' : '编辑中 · 点选要改的地方' }}</span>
      <template v-if="mode === 'interact'">
        <button type="button" class="if-btn" title="重新载入，回到刚打开的样子" @click="live?.restart()"><RotateCw :size="13" />重新开始</button>
        <button type="button" class="if-btn" @click="$emit('edit', node)"><PencilLine :size="13" />改为编辑</button>
      </template>
      <button v-else type="button" class="if-btn" @click="$emit('play', node)"><Hand :size="13" />交互</button>
      <button type="button" class="if-btn quiet" title="离开展开视图，到预览里打开这个视图" @click="$emit('open', node)"><ExternalLink :size="13" />去预览</button>
      <button type="button" class="if-btn close" title="收回成小卡（Esc）" aria-label="收起放大" @click="$emit('close')"><Minimize2 :size="13" />收起</button>
    </header>
    <div class="if-body">
      <LiveScene v-if="mode === 'interact'" ref="live" :key="'live-' + node.id" :node="node" :route="route" :frame="frame" />
      <SceneCard v-else :key="'big-' + node.id" :node="node" :styles="styles" :frame="frame" :picked="picked" :mode="mode" :crumb="crumb" :patch="patch" large @pick="$emit('pick', $event)" />
    </div>
  </article>
</template>
<style scoped>
.inline-focus{flex-shrink:0;max-width:100%;background:#fff;border:1.5px solid #e1c3b4;border-radius:14px;box-shadow:0 10px 30px #3b2a2114;overflow:hidden;scroll-margin:16px}
.inline-focus.playing{border-color:#d8b07a}
.if-head{display:flex;align-items:center;gap:8px;padding:9px 10px 9px 14px;border-bottom:1px solid var(--line);background:#fffdfa;flex-wrap:wrap}
.if-title{display:flex;align-items:baseline;gap:8px;flex:1;min-width:160px}
.if-title strong{font-size:13.5px;white-space:nowrap}
.if-crumb{min-width:0;font-size:11.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.state-tag{flex-shrink:0;font-size:11px;padding:2px 8px;border-radius:20px;background:var(--primary-soft);color:var(--primary)}
.state-tag.live{background:#fbf1dc;color:#8a5a0b}
.if-btn{gap:5px;height:28px;padding:0 9px;border:1px solid var(--line);border-radius:8px;background:#fff;font-size:12px;white-space:nowrap}
.if-btn:hover{border-color:#c9c1b4}
.if-btn.quiet{border-color:transparent;color:var(--muted)}
.if-btn.close{color:var(--ink);background:var(--quiet)}
.if-body{padding:14px;background:#f7f5ef}
</style>
