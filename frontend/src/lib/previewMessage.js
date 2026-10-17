// Vue state contains proxies, which postMessage cannot clone. The preview
// protocol carries JSON data only, so flatten it at the frame boundary.
export function previewMessage(message) {
  return JSON.parse(JSON.stringify(message))
}

export const PREVIEW_SANDBOX = 'allow-scripts allow-modals allow-forms'
