<script setup>
// 一张小卡片代替一大段字（参照 Claude 粘贴长文时变成附件卡片）：标题 + 一行摘要，点开看清单。
// 「同步到原型」挂在输入框上面时可以 × 拿掉；发出去以后对话里也只显示这张卡片
import { ref } from 'vue'
import { ArrowUpRight, ChevronDown, ChevronRight, X } from 'lucide-vue-next'

defineProps({ title: String, items: { type: Array, default: () => [] }, removable: Boolean })
const emit = defineEmits(['remove'])
const open = ref(false)
</script>

<template>
  <div class="attach-card" :class="{ open }">
    <button type="button" class="attach-main" :aria-expanded="open" @click="open = !open">
      <span class="attach-icon"><ArrowUpRight :size="14" /></span>
      <span class="attach-text"><b>{{ $t(title) }}</b><small>{{ items.length > 1 ? $t('{0} 处 · {1} 等', [items.length, items[0]]) : items[0] }}</small></span>
      <ChevronDown v-if="open" :size="14" class="attach-fold" /><ChevronRight v-else :size="14" class="attach-fold" />
    </button>
    <button v-if="removable" type="button" class="icon-button attach-x" :aria-label="$t('拿掉')" @click="emit('remove')"><X :size="13" /></button>
    <ul v-if="open"><li v-for="(item, i) in items" :key="i">{{ item }}</li></ul>
  </div>
</template>
