import test from 'node:test'
import assert from 'node:assert/strict'
import { reactive, ref } from 'vue'
import { previewMessage } from '../src/lib/previewMessage.js'

test('box selection can cross the iframe boundary', () => {
  const bounds = ref({ left: 20, top: 149, right: 414, bottom: 343 })
  const result = structuredClone(previewMessage({ type: 'PA_BOX_RECT', bounds: bounds.value }))
  assert.deepEqual(result.bounds, { left: 20, top: 149, right: 414, bottom: 343 })
})

test('nested annotation targets remain intact and detached from editor state', () => {
  const annotations = reactive([{ selector: 'main', targets: [{ selector: '#one' }], note: '调整这里' }])
  const result = structuredClone(previewMessage({ type: 'PA_RENDER_MARKERS', annotations }))
  annotations[0].targets[0].selector = '#two'
  assert.equal(result.annotations[0].targets[0].selector, '#one')
  assert.equal(result.annotations[0].note, '调整这里')
})
