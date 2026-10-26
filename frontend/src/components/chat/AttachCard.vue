<script setup>
// 一张小卡片代替一大段字（参照 Claude 粘贴长文时变成附件卡片）：标题 + 一行摘要，点开看清单。
// 「同步到原型」挂在输入框上面时可以 × 拿掉；发出去以后对话里也只显示这张卡片。
// 程序替你发的话（按这个改、自动修、自检、选了哪个）也用它，kind 决定图标
import { ref } from 'vue'
import { computed } from 'vue'
import { ArrowUpRight, ChevronDown, ChevronRight, ListChecks, MessageCircle, Sparkles, Wrench, X } from 'lucide-vue-next'

const props = defineProps({ title: String, items: { type: Array, default: () => [] }, removable: Boolean, kind: { type: String, default: 'sync' } })
const icon = computed(() => ({ apply: Sparkles, fix: Wrench, check: ListChecks, choice: MessageCircle }[props.kind] || ArrowUpRight))
// 只有一项、标题里已经写了：摘要那行不重复
const summary = computed(() => props.items.length > 1 ? null : props.items[0] && !props.title?.includes(props.items[0]) ? props.items[0] : '')
const emit = defineEmits(['remove'])
const open = ref(false)
</script>

<template>
  <div class="attach-card" :class="{ open }">
    <button type="button" class="attach-main" :aria-expanded="open" @click="open = !open">
      <span class="attach-icon"><component :is="icon" :size="14" /></span>
      <span class="attach-text"><b>{{ $t(title) }}</b><small v-if="summary !== ''">{{ summary === null ? $t('{0} 处 · {1} 等', [items.length, items[0]]) : summary }}</small></span>
      <template v-if="items.length > 1 || summary"><ChevronDown v-if="open" :size="14" class="attach-fold" /><ChevronRight v-else :size="14" class="attach-fold" /></template>
    </button>
    <button v-if="removable" type="button" class="icon-button attach-x" :aria-label="$t('拿掉')" @click="emit('remove')"><X :size="13" /></button>
    <ul v-if="open"><li v-for="(item, i) in items" :key="i">{{ item }}</li></ul>
  </div>
</template>
