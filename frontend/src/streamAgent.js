export function responseError(data, fallback = '请求未完成，请重试') {
  const detail = data?.detail ?? data
  const error = new Error(typeof detail === 'string' ? detail : detail?.message || fallback)
  error.code = detail?.code || 'network'
  error.detail = detail?.detail || error.message
  return error
}

export async function consumeAgentStream(response, onEvent) {
  if (!response.ok) throw responseError(await response.json().catch(() => ({})))
  if (!response.body) throw responseError({ code: 'network', message: '连接中断，请重试' })
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let buffer = '', result, complete = false
  function consume(block) {
    const data = block.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
    if (!data) return
    let event
    try { event = JSON.parse(data) } catch { throw responseError({ code: 'network', message: '进度信息不完整，请重试' }) }
    onEvent(event)
    if (event.type === 'error') throw responseError(event.error)
    if (event.type === 'complete') { result = event.result; complete = true }
  }
  try {
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, '\n')
      let boundary
      while ((boundary = buffer.indexOf('\n\n')) >= 0) { consume(buffer.slice(0, boundary)); buffer = buffer.slice(boundary + 2) }
      if (done) { if (buffer.trim()) consume(buffer); break }
    }
    if (!complete) throw responseError({ code: 'network', message: '连接中断，当前文件未改动，请重试' })
    return result
  } finally { reader.releaseLock() }
}
