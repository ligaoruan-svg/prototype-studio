<script setup>
// 页面结构里的一行：区块、表格、按钮、弹窗……下面的子项缩进排在它下面，和页面从上到下的样子对得上。
// 按钮写着点了打开哪个弹窗（点一下就跳到那个弹窗），弹窗写着有哪些字段、确认后数据怎么变
import { computed, inject, nextTick, ref, watch } from 'vue'
import { ChevronDown, ChevronUp, CornerDownRight, Plus, Trash2 } from 'lucide-vue-next'
import ArchBlock from './ArchBlock.vue'
import ArchFields from './ArchFields.vue'
import { ACTIONS, CHILD_TYPES, NODE_TYPES } from '../../lib/architecture.js'

const props = defineProps({ node: Object })
const emit = defineEmits(['goto'])
const s = inject('studio')
const { archSelected, archRenaming, archIssues } = s
const selected = computed(() => archSelected.value?.kind === 'node' && archSelected.value.id === props.node.id)
const kids = computed(() => props.node.children || [])
const childTypes = computed(() => CHILD_TYPES[props.node.type] || [])
const warn = computed(() => archIssues.value.filter(i => i.node === props.node.id))
const renaming = computed(() => archRenaming.value === props.node.id)
const nameInput = ref(null)
watch(renaming, on => { if (on) nextTick(() => { nameInput.value?.focus(); nameInput.value?.select() }) }, { immediate: true })
function commitName(event) { if (renaming.value) s.renameNode(props.node.id, event.target.value) }
function addChild(event) { const type = event.target.value; event.target.value = ''; if (type) s.archAdd(props.node.id, type) }
</script>

<template>
  <div class="ab" :class="node.type" :data-node="node.id">
    <div class="ab-row" :class="{ selected, warn: warn.length }" @click.stop="s.archSelect('node', node.id)" @dblclick.stop="archRenaming = node.id">
      <span class="an-type">{{ $t(NODE_TYPES[node.type].short) }}</span>
      <input v-if="renaming" ref="nameInput" class="an-rename" :value="node.name" :aria-label="$t('名称')" @click.stop @keydown.enter.prevent="commitName" @keydown.esc.stop.prevent="archRenaming = ''" @blur="commitName">
      <b v-else class="ab-name">{{ node.name }}</b>
      <!-- 按钮：点了怎样 -->
      <button v-if="node.action" class="ab-act" :class="node.action" :disabled="!['open', 'jump'].includes(node.action) || !node.target" @click.stop="emit('goto', node.target)"><CornerDownRight :size="12" />{{ $t(ACTIONS[node.action]) }}<span v-if="node.target">「{{ node.target }}」</span></button>
      <span v-else-if="node.type === 'button'" class="ab-todo">{{ $t('点了以后还没定') }}</span>
      <span v-if="node.when" class="ab-when">{{ $t('出现：{0}', [node.when]) }}</span>
      <span v-if="node.desc" class="ab-desc">{{ node.desc }}</span>
      <span v-if="warn.length" class="an-warn ab-warn" :title="warn.map(w => w.text).join('\n')">⚠ {{ warn.length }}</span>
      <div v-if="selected" class="an-tools ab-tools" @click.stop>
        <label v-if="childTypes.length" class="an-add"><Plus :size="12" />{{ $t('子项') }}<select :aria-label="$t('加子项')" @change="addChild"><option value="">{{ $t('加什么') }}</option><option v-for="t in childTypes" :key="t" :value="t">{{ $t(NODE_TYPES[t].label) }}</option></select></label>
        <button @click="s.archSibling(node.id)"><Plus :size="12" />{{ $t('同级') }}</button>
        <button :title="$t('上移')" :aria-label="$t('上移')" @click="s.archMove(node.id, -1)"><ChevronUp :size="13" /></button>
        <button :title="$t('下移')" :aria-label="$t('下移')" @click="s.archMove(node.id, 1)"><ChevronDown :size="13" /></button>
        <button class="danger" @click="s.archRemove(node.id)"><Trash2 :size="12" />{{ $t('删除') }}</button>
      </div>
    </div>
    <!-- 弹窗、区块的字段，表格的列：一个个小标签排开 -->
    <div v-if="['modal', 'drawer', 'wizard', 'block', 'table'].includes(node.type)" class="ab-detail" @click.stop>
      <ArchFields :node="node" :open="true" @edit="s.archSelect('node', node.id)" />
    </div>
    <div v-if="kids.length" class="ab-kids"><ArchBlock v-for="child in kids" :key="child.id" :node="child" @goto="emit('goto', $event)" /></div>
  </div>
</template>
