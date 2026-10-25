<script setup>
// 一个字段画成它本来的控件：下拉带 ▾ 和选项、日期带日历、上传是虚线框、开关是小拨钮……一眼分得出是填、是选还是自动带出
import { computed } from 'vue'
import { Calendar, ChevronDown, Clock, ImagePlus, Upload, User } from 'lucide-vue-next'
import { t } from '../../lib/i18n.js'

const props = defineProps({ f: Object })
const opts = computed(() => props.f.options || [])
const optLine = computed(() => opts.value.slice(0, 4).join(' / ') + (opts.value.length > 4 ? ' …' : ''))
</script>

<template>
  <span v-if="f.locked" class="ac locked">{{ $t('自动带出 🔒') }}</span>
  <span v-else-if="f.type === 'textarea'" class="ac area">{{ $t('请输入') }}</span>
  <span v-else-if="f.type === 'select' || f.type === 'cascade'" class="ac pick" :title="opts.join(' / ')"><b>{{ f.type === 'cascade' ? $t('省 / 市 / 区') : opts.length ? optLine : $t('请选择') }}</b><ChevronDown :size="11" /></span>
  <span v-else-if="f.type === 'multi'" class="ac pick" :title="opts.join(' / ')"><b><i v-for="o in (opts.length ? opts.slice(0, 2) : [t('可多选')])" :key="o" class="chip">{{ o }}</i></b><ChevronDown :size="11" /></span>
  <span v-else-if="f.type === 'radio'" class="ac bare"><i v-for="(o, n) in (opts.length ? opts.slice(0, 4) : [t('选项一'), t('选项二')])" :key="o" class="radio" :class="{ on: n === 0 }">{{ o }}</i></span>
  <span v-else-if="f.type === 'check'" class="ac bare"><i class="box"></i>{{ $t('勾选') }}</span>
  <span v-else-if="f.type === 'switch'" class="ac bare"><i class="switch"></i></span>
  <span v-else-if="f.type === 'date'" class="ac pick"><b>{{ $t('年-月-日') }}</b><Calendar :size="11" /></span>
  <span v-else-if="f.type === 'datetime'" class="ac pick"><b>{{ $t('年-月-日 时:分') }}</b><Calendar :size="11" /></span>
  <span v-else-if="f.type === 'daterange'" class="ac pick"><b>{{ $t('开始 → 结束') }}</b><Calendar :size="11" /></span>
  <span v-else-if="f.type === 'time'" class="ac pick"><b>{{ $t('时:分') }}</b><Clock :size="11" /></span>
  <span v-else-if="f.type === 'number'" class="ac num">0</span>
  <span v-else-if="f.type === 'money'" class="ac num">¥ 0.00</span>
  <span v-else-if="f.type === 'phone'" class="ac">{{ $t('11 位手机号') }}</span>
  <span v-else-if="f.type === 'person'" class="ac pick"><b><User :size="11" />{{ $t('选择人员') }}</b><ChevronDown :size="11" /></span>
  <span v-else-if="f.type === 'upload'" class="ac drop"><Upload :size="11" />{{ $t('上传文件') }}</span>
  <span v-else-if="f.type === 'image'" class="ac drop img"><ImagePlus :size="13" /></span>
  <span v-else-if="f.type === 'note'" class="ac note">{{ $t('一段说明文字，不用填') }}</span>
  <span v-else class="ac">{{ $t('请输入') }}</span>
</template>
