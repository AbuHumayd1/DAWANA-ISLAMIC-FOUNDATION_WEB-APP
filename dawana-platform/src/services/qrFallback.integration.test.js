// Real installed ZXing engines, synthetic pixels and an in-memory canvas adapter.
// No camera, network, Operations API or database calls.
import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import zxing from '@zxing/library'
import { createServer } from 'vite'
const { QRCodeWriter, BarcodeFormat } = zxing
let server, createQrDecoder
before(async () => {
  server = await createServer({ configFile: false, server: { middlewareMode: true, hmr: false, ws: false },
    appType: 'custom', ssr: { noExternal: ['@zxing/browser', '@zxing/library'] } })
  createQrDecoder = (await server.ssrLoadModule('/src/services/qrDecoder.js')).createQrDecoder
})
after(async () => { await server?.close() })

function canvasFor(matrix) {
  return { width: 0, height: 0, getContext() {
    return { drawImage() {}, getImageData: (_x, _y, width, height) => {
      const data = new Uint8ClampedArray(width * height * 4)
      for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
        const dark = matrix?.get(Math.floor(x * matrix.getWidth() / width), Math.floor(y * matrix.getHeight() / height))
        const index = (y * width + x) * 4
        data[index] = data[index + 1] = data[index + 2] = dark ? 0 : 255
        data[index + 3] = 255
      }
      return { data }
    } }
  } }
}

async function usingCanvas(matrix, action) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'document')
  const canvas = canvasFor(matrix)
  Object.defineProperty(globalThis, 'document', { configurable: true, value: {
    createElement(tag) { assert.equal(tag, 'canvas'); return canvas },
  } })
  let decoder
  try {
    // Use the production dynamic import/factory, not an injected mock decoder.
    decoder = await createQrDecoder({ Detector: null })
    await action(decoder, canvas)
  } finally {
    decoder?.destroy()
    if (previous) Object.defineProperty(globalThis, 'document', previous)
    else delete globalThis.document
  }
}

test('installed ZXing fallback decodes a generated camper QR URL through the production loader', async () => {
  const value = `https://camp.example.test/api/v1/dic/ids/verify/#${'A'.repeat(43)}`
  const matrix = new QRCodeWriter().encode(value, BarcodeFormat.QR_CODE, 320, 320, new Map())
  await usingCanvas(matrix, async (decoder, canvas) => {
    const frame = { readyState: 4, videoWidth: 320, videoHeight: 320 }
    assert.equal(await decoder.decode(frame), value)
    decoder.destroy()
    assert.equal(canvas.width, 0); assert.equal(canvas.height, 0)
    assert.equal(await decoder.decode(frame), null)
  })
})

test('installed ZXing no-code exception is treated as an ordinary blank frame', async () => {
  await usingCanvas(null, async decoder => {
    assert.equal(await decoder.decode({ readyState: 4, videoWidth: 320, videoHeight: 320 }), null)
  })
})
