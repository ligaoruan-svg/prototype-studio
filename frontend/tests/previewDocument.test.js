import test from 'node:test'
import assert from 'node:assert/strict'
import { preparePreviewDocument } from '../src/lib/previewDocument.js'

test('没有 <head> 的页面也能放进路由和展开标记', () => {
  const withHead = preparePreviewDocument('<html><head><title>t</title></head><body></body></html>', { route: '#a', probe: true })
  assert.match(withHead, /<head><script data-pa-seed>.*__paRoute="#a".*__paProbe=true/)
  const noHead = preparePreviewDocument('<html><body><p>x</p></body></html>', { route: '#b' })
  assert.match(noHead, /<html><script data-pa-seed>.*__paRoute="#b"/)
  const bare = preparePreviewDocument('<p>只有片段</p>', { route: '#c' })
  assert.ok(bare.startsWith('<script data-pa-seed>'))
  assert.equal((preparePreviewDocument(withHead, {}).match(/data-pa-seed/g) || []).length, 1, '重复准备不叠加')
})
