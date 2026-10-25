<script setup>
// 大纲：手动编架构最快的办法。缩进是层级，方括号是类型，冒号后面是介绍；和页面树、数据、流程是同一份东西。
// 右边可以粘 Excel 里复制的功能清单（几列：模块、菜单、功能、说明、编号），合并单元格空着的格子沿用上一行
import { computed, inject, ref } from 'vue'
import { ClipboardPaste, Check } from 'lucide-vue-next'

const s = inject('studio')
const { archOutline, archOutlineDirty, archBusy } = s
const paste = ref(''), pasteMode = ref('append')
const lines = computed(() => archOutline.value.split('\n').length)
const EXAMPLE = `系统：设备管理平台
角色：管理员

【页面】
设备管理 [模块]：管设备的定义、档案和巡检
  设备定义 [菜单页]：设备模板 | 数据：设备定义
    新增 / 编辑定义 [弹窗]
  设备巡检计划 [菜单页]：配点位、路线、计划
    巡检点 [页签]：在哪打卡、查什么 | 数据：巡检点
    路线配置 [页签]：有序的一串巡检点 | 数据：路线
      路线详情 [抽屉]：只读

【数据】
设备定义 DF-xxx [模板]
  定义编码 🔑
巡检点 PT-xxx [配置]
  关联设备 → 设备定义
路线 RT-xxx [配置]
  巡检点 → 巡检点：多个，有顺序
  巡检点数 = 点的个数

【流程】
泳道：管理员（电脑）、巡检执行 [不做]（手机端）
管理员 · 配巡检点 | 下一步：配路线
管理员 · 配路线`
function edit(event) { archOutline.value = event.target.value; archOutlineDirty.value = true }
function reset() { s.loadArch(true) }
async function doImport() { if (await s.importText(paste.value, pasteMode.value)) paste.value = '' }
// Tab 在大纲里是缩进两格，不是跳到下一个输入框
function tab(event) {
  const el = event.target, start = el.selectionStart, end = el.selectionEnd, value = el.value
  if (event.shiftKey) {
    const lineStart = value.lastIndexOf('\n', start - 1) + 1
    if (value.slice(lineStart, lineStart + 2) === '  ') { el.value = value.slice(0, lineStart) + value.slice(lineStart + 2); el.selectionStart = el.selectionEnd = Math.max(lineStart, start - 2) }
  } else { el.value = value.slice(0, start) + '  ' + value.slice(end); el.selectionStart = el.selectionEnd = start + 2 }
  edit(event)
}
</script>

<template>
  <div class="ao-wrap" @click.stop>
    <section class="ao-main">
      <header><b>{{ $t('大纲') }}</b><span class="arch-muted">{{ $t('缩进是层级，[类型] 写在名字后面，冒号后面是介绍，| 隔开数据、地址、入口这些') }}</span></header>
      <textarea class="ao-text" :value="archOutline" :placeholder="EXAMPLE" spellcheck="false" :rows="Math.max(18, lines + 2)" @input="edit" @keydown.tab.prevent="tab" @keydown.meta.s.prevent="s.applyOutline(archOutline)" @keydown.ctrl.s.prevent="s.applyOutline(archOutline)"></textarea>
      <footer><span class="arch-muted">{{ archOutlineDirty ? $t('改了还没应用 · ⌘S 应用') : $t('和页面树是同一份，在哪边改都行') }}</span>
        <button v-if="archOutlineDirty" class="quiet" @click="reset">{{ $t('放弃修改') }}</button>
        <button class="primary" :disabled="!archOutlineDirty || archBusy === 'draft'" @click="s.applyOutline(archOutline)"><Check :size="14" />{{ $t('应用到架构') }}</button></footer>
    </section>
    <aside class="ao-side">
      <b><ClipboardPaste :size="14" />{{ $t('粘贴功能清单') }}</b>
      <p class="arch-muted">{{ $t('从 Excel 选中几列复制过来（模块、菜单、功能、说明、编号都行，有没有表头都行），合并单元格空着的会沿用上一行。也可以粘一段大纲。') }}</p>
      <textarea v-model="paste" rows="10" :placeholder="$t('编号	模块	菜单	功能	说明\n85	设备管理	设备定义	新增定义	定义参数模板\n86		设备录入	批量导入	下载模板、校验、导入')"></textarea>
      <div class="ao-mode"><label><input v-model="pasteMode" type="radio" value="append">{{ $t('加进现在的架构（同名的并到一起）') }}</label><label><input v-model="pasteMode" type="radio" value="replace">{{ $t('替换页面树') }}</label></div>
      <button class="primary" :disabled="!paste.trim()" @click="doImport">{{ $t('导入') }}</button>
    </aside>
  </div>
</template>
