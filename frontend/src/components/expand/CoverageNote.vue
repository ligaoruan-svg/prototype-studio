<script setup>
import { computed, ref } from 'vue'
import { ChevronDown, ChevronRight, ListChecks } from 'lucide-vue-next'
// 找全了没有：这一页试了多少个按钮、各出了什么结果，哪些没试、为什么。
// 一行总数常显；「没试的」默认收起，点开按原因列出按钮名
const props = defineProps({ coverage: Object })
const emit = defineEmits(['refind'])
const open = ref(false)
const c = computed(() => props.coverage || null)
const n = bucket => (typeof bucket === 'number' ? bucket : bucket?.n || 0)
// 试过的按钮各出了什么
const outcomes = computed(() => {
  const x = c.value
  if (!x) return []
  return [
    { label: '出了视图', n: x.views },
    { label: '跳去别的页', n: x.jumps },
    { label: '切到页签', n: x.links },
    { label: '待补', n: x.dead, warn: true },
    { label: '没反应', n: n(x.none) },
    { label: '和已有的重复', n: x.dup },
    { label: '点不到', n: n(x.fail), warn: true },
  ].filter(o => o.n > 0)
})
// 没试的，按原因分组
const REASONS = {
  nav: ['菜单和页签', '切换业务页面、页签另算，不在这里点'],
  chrome: ['顶栏 / 侧栏', '页面外壳上的按钮（用户、消息、设置）'],
  commit: ['会改数据的', '保存、删除、提交这类不点，免得改了演示数据'],
  noise: ['查询 / 翻页这类', '查询、重置、导出、翻页，点了不会出新的视图'],
  repeat: ['同类只试两个', '每行都有的「查看」只试前两行'],
  limit: ['一页超过 40 个', '按钮太多，后面的没排上'],
}
const skipped = computed(() => {
  const x = c.value
  if (!x) return []
  const rows = Object.entries(x.skipped || {}).filter(([, v]) => v?.n).map(([key, v]) => ({ key, title: REASONS[key]?.[0] || key, why: REASONS[key]?.[1] || '', n: v.n, labels: v.labels || [] }))
  if (n(x.cut)) rows.push({ key: 'cut', title: '弹窗里按钮太多', why: '一个弹窗只往下试前 12 个，子页面前 24 个', n: x.cut.n, labels: x.cut.labels || [] })
  if (n(x.left)) rows.push({ key: 'left', title: '没轮到', why: x.left.why || '试的次数或时间用完了', n: x.left.n, labels: x.left.labels || [], warn: true })
  if (n(x.none)) rows.push({ key: 'none', title: '点了没反应', why: '点了页面没变化，也没弹出东西（不是展示类按钮，所以不算待补）', n: x.none.n, labels: x.none.labels || [], quiet: true })
  if (n(x.fail)) rows.push({ key: 'fail', title: '点不到', why: '按路径找不到这个按钮了，或者原型没响应', n: x.fail.n, labels: x.fail.labels || [], warn: true })
  return rows
})
const skippedTotal = computed(() => skipped.value.filter(r => r.key !== 'none' && r.key !== 'fail').reduce((a, r) => a + r.n, 0))
const incomplete = computed(() => n(c.value?.left) > 0)
const secs = computed(() => (c.value?.ms ? Math.max(1, Math.round(c.value.ms / 1000)) : 0))
</script>
<template>
  <div v-if="c" class="coverage" :class="{ warn: incomplete }">
    <p class="head"><ListChecks :size="13" />试了 <b>{{ c.tried }}</b> 个按钮<small v-if="secs">· 用了 {{ secs >= 60 ? Math.round(secs / 60) + ' 分钟' : secs + ' 秒' }}</small></p>
    <p class="outcomes"><span v-for="o in outcomes" :key="o.label" :class="{ warn: o.warn }">{{ o.label }} {{ o.n }}</span></p>
    <button v-if="skipped.length" type="button" class="toggle" :aria-expanded="open" @click="open = !open">
      <component :is="open ? ChevronDown : ChevronRight" :size="12" />
      <template v-if="incomplete">还有 {{ c.left.n }} 个没轮到</template><template v-else-if="skippedTotal">跳过 {{ skippedTotal }} 个，看为什么</template><template v-else>看明细</template>
    </button>
    <ul v-if="open" class="reasons">
      <li v-for="r in skipped" :key="r.key" :class="{ warn: r.warn, quiet: r.quiet }">
        <strong>{{ r.title }} <span>{{ r.n }}</span></strong>
        <small>{{ r.why }}</small>
        <em v-if="r.labels.length">{{ r.labels.join('、') }}{{ r.n > r.labels.length ? ' …' : '' }}</em>
      </li>
      <li v-if="incomplete" class="again"><button type="button" class="link-btn" @click="emit('refind')">重新查找这一页</button></li>
    </ul>
  </div>
</template>
<style scoped>
.coverage{margin-top:12px;padding:9px 10px;border:1px solid var(--line);border-radius:12px;background:#fff;font-size:12px;color:var(--muted)}
.coverage.warn{border-color:#edd6a6;background:#fffcf5}
.head{display:flex;align-items:center;gap:5px;margin:0;color:var(--ink)}
.head svg{color:var(--subtle)}.head b{font-weight:600}.head small{color:var(--muted);font-size:11px}
.outcomes{display:flex;flex-wrap:wrap;gap:4px 6px;margin:6px 0 0}
.outcomes span{padding:1px 7px;border-radius:20px;background:var(--quiet);font-size:11px;white-space:nowrap}
.outcomes span.warn{background:#fbf1dc;color:#8a5a0b}
.toggle{gap:3px;margin-top:6px;padding:2px 4px 2px 0;font-size:11.5px;color:var(--primary)}
.reasons{margin:6px 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:7px}
.reasons li{padding-top:7px;border-top:1px dashed var(--line)}
.reasons strong{display:block;font-size:11.5px;font-weight:600;color:var(--ink)}
.reasons strong span{font-weight:500;color:var(--muted)}
.reasons li.warn strong{color:#8a5a0b}
.reasons li.quiet strong{color:var(--muted)}
.reasons small{display:block;font-size:11px;line-height:1.5}
.reasons em{display:block;margin-top:2px;font-style:normal;font-size:11px;color:#5f5a50;line-height:1.5;overflow-wrap:anywhere}
.reasons li.again{border-top:0;padding-top:0}
.link-btn{padding:0;font-size:11.5px;color:var(--primary);text-decoration:underline;text-underline-offset:2px}
</style>
