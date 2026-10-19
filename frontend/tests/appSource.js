// App.vue 的逻辑拆到了 src/composables/ 下：检查「整个外壳的逻辑」时拼在一起看
import { readFileSync, readdirSync } from 'node:fs'

export function appSource() {
  const dir = new URL('../src/composables/', import.meta.url)
  return [readFileSync(new URL('../src/App.vue', import.meta.url), 'utf8'),
    ...readdirSync(dir).filter(f => f.endsWith('.js')).sort().map(f => readFileSync(new URL(f, dir), 'utf8'))].join('\n')
}
