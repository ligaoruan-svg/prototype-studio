import test from 'node:test'
import assert from 'node:assert/strict'
import { consumeAgentStream } from '../src/streamAgent.js'
import { PREVIEW_SANDBOX } from '../src/previewMessage.js'
function response(text, chunkSize = 7) {
  const data = new TextEncoder().encode(text)
  return new Response(new ReadableStream({ start(controller) { for (let i = 0; i < data.length; i += chunkSize) controller.enqueue(data.slice(i, i + chunkSize)); controller.close() } }))
}
test('SSE preserves split Chinese characters and ignores heartbeat comments', async () => {
  const events = []
  const result = await consumeAgentStream(response('data: {"type":"step_start","label":"读取页面"}\n\n: heartbeat\n\ndata: {"type":"complete","result":{"changed":true}}\n\n'), e => events.push(e))
  assert.equal(events[0].label, '读取页面')
  assert.equal(result.changed, true)
})
test('SSE error keeps the structured category', async () => {
  await assert.rejects(consumeAgentStream(response('data: {"type":"error","error":{"code":"output_limit","message":"一次没写完"}}\n\n'), () => {}), e => e.code === 'output_limit')
})
test('connection closing without completion is not a success', async () => {
  await assert.rejects(consumeAgentStream(response('data: {"type":"started"}\n\n'), () => {}), e => e.code === 'network')
})
test('preview and candidate share an opaque sandbox with identical permissions', () => {
  assert.equal(PREVIEW_SANDBOX, 'allow-scripts allow-modals allow-forms')
  assert.ok(!PREVIEW_SANDBOX.includes('allow-same-origin'))
})
test('SSE error with a detail field (what the backend really sends) still keeps its category', async () => {
  await assert.rejects(consumeAgentStream(response('data: {"type":"error","error":{"code":"validation","message":"改完页面报错了","detail":"Uncaught TypeError"}}\n\n'), () => {}), e => e.code === 'validation' && e.detail === 'Uncaught TypeError')
  await assert.rejects(consumeAgentStream(response('data: {"type":"error","error":{"code":"stopped","message":"已停止","detail":""}}\n\n'), () => {}), e => e.code === 'stopped')
})
