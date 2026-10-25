<script setup>
// 卡片里的字段：收起时一行摘要（几个字段、几个必填、确认后怎样），展开后画成它本来的样子——
// 弹窗 / 向导是一张小表单（两列、必填红星、带 🔒 的是自动带出、底部取消 / 确认），抽屉是只读的「字段：值」，
// 表格是一条表头加两行占位，区块（筛选、信息卡）是一排输入框
import { computed, ref, watch } from 'vue'
import { ChevronDown, ChevronRight } from 'lucide-vue-next'
import { t } from '../../lib/i18n.js'

const props = defineProps({ node: Object, open: Boolean })
const emit = defineEmits(['edit'])
const shown = ref(props.open)
watch(() => props.open, v => { shown.value = v })
const isTable = computed(() => props.node.type === 'table')
const list = computed(() => (isTable.value ? props.node.cols : props.node.fields) || [])
// 「维修工*」必填，「工单编号🔒」或写着「自动」的是自动带出、不用填
const items = computed(() => list.value.map(raw => {
  const must = /\*\s*$/.test(raw), locked = /🔒|（自动|\(自动|自动带出/.test(raw)
  const name = raw.replace(/\*\s*$/, '').replace(/🔒/g, '').replace(/[（(]自动[^）)]*[）)]/, '').trim()
  return { name, must, locked, wide: /备注|说明|描述|内容|原因|意见/.test(name) }
}))
const must = computed(() => items.value.filter(i => i.must).length)
const summary = computed(() => {
  if (!items.value.length) return ''
  const names = items.value.slice(0, 4).map(i => i.name + (i.must ? '*' : '')).join(' · ') + (items.value.length > 4 ? ' …' : '')
  if (isTable.value) return t('{0} 列：{1}', [items.value.length, names])
  if (props.node.type === 'drawer') return t('只读 · {0} 项：{1}', [items.value.length, names])
  return (must.value ? t('{0} 个字段（{1} 必填）：{2}', [items.value.length, must.value, names]) : t('{0} 个字段：{1}', [items.value.length, names]))
})
const style = computed(() => isTable.value ? 'table' : props.node.type === 'drawer' ? 'drawer' : props.node.type === 'block' ? 'block' : 'form')
const confirmText = computed(() => props.node.type === 'wizard' ? t('完成') : /^(新增|新建|添加)/.test(props.node.name) ? t('保存') : t('确定'))
</script>

<template>
  <div class="af" :class="[style, { shown }]">
    <button v-if="items.length" class="af-sum" :aria-expanded="shown" @click="shown = !shown"><ChevronDown v-if="shown" :size="12" /><ChevronRight v-else :size="12" /><span>{{ summary }}</span></button>
    <button v-else class="af-empty" @click="emit('edit')">{{ isTable ? $t('还没写列 · 去补') : $t('还没写字段 · 去补') }}</button>
    <template v-if="shown && items.length">
      <!-- 弹窗、向导：小表单 -->
      <div v-if="style === 'form'" class="af-form">
        <div v-for="f in items" :key="f.name" class="af-f" :class="{ wide: f.wide }"><label>{{ f.name }}<i v-if="f.must">*</i></label><span :class="{ locked: f.locked, area: f.wide }">{{ f.locked ? $t('自动带出 🔒') : '' }}</span></div>
      </div>
      <!-- 抽屉：只读 -->
      <div v-else-if="style === 'drawer'" class="af-kv"><template v-for="f in items" :key="f.name"><span>{{ f.name }}</span><em></em></template></div>
      <!-- 表格：表头 + 两行占位 -->
      <div v-else-if="style === 'table'" class="af-table"><div class="af-tr head"><span v-for="c in items" :key="c.name">{{ c.name }}</span></div><div v-for="r in 2" :key="r" class="af-tr"><span v-for="c in items" :key="c.name"></span></div></div>
      <!-- 区块：一排输入框（筛选、信息卡） -->
      <div v-else class="af-block"><span v-for="f in items" :key="f.name"><label>{{ f.name }}<i v-if="f.must">*</i></label><em :class="{ locked: f.locked }"></em></span></div>
    </template>
    <p v-if="node.after" class="af-after">{{ $t('确认后：{0}', [node.after]) }}</p>
    <div v-if="shown && style === 'form' && items.length" class="af-foot"><span>{{ $t('取消') }}</span><span class="p">{{ confirmText }}</span></div>
  </div>
</template>
