<script setup>
// 改代码那一步改了哪几行（参照 Claude 改文件时的样子）：加的绿、删的红，左边行号，中间断开的地方一条虚线
defineProps({ diff: Object })
</script>

<template>
  <div class="mini-diff">
    <div v-for="(l, i) in diff.lines" :key="i" :class="l.kind"><span class="ln">{{ l.line || '' }}</span><code>{{ l.kind === 'added' ? '+' : l.kind === 'removed' ? '−' : ' ' }} {{ l.text }}</code></div>
    <p v-if="diff.more" class="more">{{ $t('还有改动没列出来，结果卡上「查看改动」看全部') }}</p>
  </div>
</template>

<style scoped>
.mini-diff{margin:5px 0 2px;border:1px solid var(--line);border-radius:var(--r-tag);overflow:hidden;background:#fff;font:11px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.mini-diff>div{display:flex;min-width:0}
.mini-diff .ln{flex:none;width:34px;padding-right:6px;text-align:right;color:var(--subtle);user-select:none;background:#faf9f5}
.mini-diff code{flex:1;min-width:0;padding:0 8px;white-space:pre;overflow:hidden;text-overflow:ellipsis;color:#4d4a44;font:inherit}
.mini-diff .added{background:#eaf6ec}.mini-diff .added code{color:#1f6b33}
.mini-diff .removed{background:#fbecea}.mini-diff .removed code{color:#9a3a2c}
.mini-diff .gap{height:7px;border-top:1px dashed var(--line);border-bottom:1px dashed var(--line);background:#faf9f5}
.mini-diff .more{margin:0;padding:3px 8px;font:11px/1.6 inherit;color:var(--subtle);background:#faf9f5;font-family:inherit}
</style>
