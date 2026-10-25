<script setup>
// 右边详情里改字段：一行一个，名字、控件（下拉 / 日期 / 上传……）、必填、自动带出，下拉单选多选再写选项。
// 存回去还是一行字「报修分类*（下拉：给排水/电气照明）」，大纲、交给 AI 的话都照这个写。也可以切到「整段写」一次粘好几个
import { computed, inject, ref } from 'vue'
import { Plus, X } from 'lucide-vue-next'
import { FIELD_TYPES, WITH_OPTIONS, fieldText, guessType, parseField, splitOutside } from '../../lib/archFields.js'
import { t } from '../../lib/i18n.js'

const props = defineProps({ node: Object })
const s = inject('studio')
const bulk = ref(false)
const rows = computed(() => (props.node.fields || []).map(raw => { const f = parseField(raw); return { ...f, type: f.guessed ? '' : f.type } }))
const kinds = Object.entries(FIELD_TYPES).filter(([k]) => k !== 'text')
function save(list) {
  if (list.length) props.node.fields = list; else delete props.node.fields
  s.archDirty()
}
function update(i, patch) {
  const list = rows.value.map(fieldText)
  list[i] = fieldText({ ...rows.value[i], ...patch })
  save(list)
}
function add() { s.archChange(() => { props.node.fields = [...(props.node.fields || []), t('新字段')] }) }
function remove(i) { s.archChange(() => save(rows.value.filter((_, n) => n !== i).map(fieldText))) }
function setBulk(text) { save(text.split('\n').flatMap(line => splitOutside(line)).filter(Boolean)) }
</script>

<template>
  <div class="ad-field afe">
    <div class="afe-head"><span>{{ $t('字段') }}</span><button class="quiet" @click="bulk = !bulk">{{ bulk ? $t('一个个改') : $t('整段写') }}</button></div>
    <template v-if="bulk">
      <textarea rows="6" :value="(node.fields || []).join('\n')" :aria-label="$t('字段')" :placeholder="$t('一行一个：名称*（下拉：选项A/选项B）\n必填加 *，自动带出加 🔒')" @focus="s.archSnapshot()" @change="setBulk($event.target.value)"></textarea>
    </template>
    <template v-else>
      <div v-for="(f, i) in rows" :key="i + '|' + f.name" class="afe-row">
        <input class="afe-name" :value="f.name" :aria-label="$t('字段名')" @focus="s.archSnapshot()" @change="update(i, { name: $event.target.value.trim() || f.name })">
        <select :value="f.type" :aria-label="$t('控件')" @focus="s.archSnapshot()" @change="update(i, { type: $event.target.value })">
          <option value="">{{ $t('{0}（猜的）', [$t(FIELD_TYPES[guessType(f.name)])]) }}</option>
          <option value="text">{{ $t('文本') }}</option>
          <option v-for="[k, label] in kinds" :key="k" :value="k">{{ $t(label) }}</option>
        </select>
        <button class="icon-button" :aria-label="$t('删除')" @click="remove(i)"><X :size="12" /></button>
        <div class="afe-sub">
          <label class="afe-flag" :title="$t('必填')"><input type="checkbox" :checked="f.must" @focus="s.archSnapshot()" @change="update(i, { must: $event.target.checked })">{{ $t('必填') }}</label>
          <label class="afe-flag" :title="$t('自动带出、不用填')"><input type="checkbox" :checked="f.locked" @focus="s.archSnapshot()" @change="update(i, { locked: $event.target.checked })">🔒</label>
          <input v-if="WITH_OPTIONS.includes(f.type || guessType(f.name)) && !f.locked" class="afe-opts" :value="f.options.join(' / ')" :placeholder="$t('选项用 / 分开，比如：一般 / 紧急')" :aria-label="$t('选项')" @focus="s.archSnapshot()" @change="update(i, { type: f.type || guessType(f.name), options: $event.target.value.split(/\s*[/／、,，]\s*/).filter(Boolean) })">
        </div>
      </div>
      <button class="quiet afe-add" @click="add"><Plus :size="12" />{{ $t('加字段') }}</button>
    </template>
  </div>
</template>
