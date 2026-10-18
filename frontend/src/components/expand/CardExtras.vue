<script setup>
import { ref } from 'vue'
import { CornerDownRight, ChevronRight, ChevronDown, CircleDashed } from 'lucide-vue-next'
// 卡片底下的两类小信息，跟着按钮所在的那张卡走（页面、页签、弹窗都一样）：
// · 关联：点了切到同一页另一个页签（整改跟踪 → 异常跟踪），点一下定位到那张页签卡
// · 待补：查看、明细这类展示按钮点了没任何反应，原型里还没接上。默认收起，只显示数量
defineProps({ links: { type: Array, default: () => [] }, dead: { type: Array, default: () => [] } })
defineEmits(['goto'])
const open = ref(false)
const clean = label => String(label || '').replace(/^表格行 · /, '列表行 · ')
</script>
<template>
  <div v-if="links.length || dead.length" class="extras">
    <button v-for="(l, i) in links" :key="'l' + i" type="button" class="link-chip" :disabled="l.target == null" :title="l.target == null ? $t('没找到这个页签的卡片') : $t('定位到这个页签')" @click="$emit('goto', l.target)">
      <CornerDownRight :size="12" />{{ $t('点「{0}」→ 页签「{1}」', [clean(l.label), $t(l.tab)]) }}
    </button>
    <template v-if="dead.length">
      <button type="button" class="dead-toggle" :aria-expanded="open" :title="$t('查看、明细这类按钮点了没有任何反应：原型里还没接上')" @click="open = !open">
        <CircleDashed :size="12" />{{ $t('待补 {0}', [$t(dead.length)]) }}<component :is="open ? ChevronDown : ChevronRight" :size="12" />
      </button>
      <ul v-if="open" class="dead-list"><li v-for="(d, i) in dead" :key="'d' + i">{{ $t(clean(d.label)) }}<small>{{ $t('点了没反应') }}</small></li></ul>
    </template>
  </div>
</template>
<style scoped>
.extras{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:8px}
.link-chip{gap:4px;padding:3px 9px;border:1px solid var(--line);border-radius:20px;background:#fff;font-size:11.5px;color:#4c6a8a}
.link-chip:hover:not(:disabled){border-color:#9db3c9}
.dead-toggle{gap:4px;padding:3px 9px;border:1px dashed #d9b98a;border-radius:20px;background:#fffaf1;font-size:11.5px;color:#8a5a0b}
.dead-toggle:hover{background:#fbf1dc}
.dead-list{flex-basis:100%;margin:2px 0 0;padding:8px 10px 8px 26px;border:1px dashed #e7d3ad;border-radius:10px;background:#fffdf8;font-size:12px}
.dead-list li{margin:2px 0}.dead-list small{margin-left:6px;color:var(--muted);font-size:11px}
</style>
