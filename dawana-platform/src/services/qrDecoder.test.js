import test from 'node:test'
import assert from 'node:assert/strict'
import { createQrDecoder, createCanvasQrReader, cameraErrorMessage } from './qrDecoder.js'

const frame = { readyState: 4, videoWidth: 1920, videoHeight: 1080 }
test('healthy native QR reader is preferred without loading the fallback', async () => {
  let loads = 0
  class Native {
    static async getSupportedFormats() { return ['qr_code'] }
    constructor(options) { assert.deepEqual(options, { formats: ['qr_code'] }) }
    async detect(video) { assert.equal(video, frame); return [{ rawValue: 'synthetic QR' }] }
  }
  const decoder = await createQrDecoder({ Detector: Native, loadFallback: () => { loads++; throw Error() } })
  assert.equal(await decoder.decode(frame), 'synthetic QR'); assert.equal(loads, 0)
  decoder.destroy(); assert.equal(await decoder.decode(frame), null)
})

test('absent, partial, rejected capability check and failed construction select the software fallback', async () => {
  for (const Detector of [null, class {},
    class { static async getSupportedFormats() { return ['code_128'] } },
    class { static async getSupportedFormats() { throw Error() } },
    class { static async getSupportedFormats() { return ['qr_code'] } constructor() { throw Error() } }]) {
    let loads = 0, closed = 0
    const decoder = await createQrDecoder({ Detector, loadFallback: async () => {
      loads++; return { decode: () => 'software result', destroy() { closed++ } }
    } })
    assert.equal(await decoder.decode(frame), 'software result'); assert.equal(loads, 1)
    decoder.destroy(); assert.equal(closed, 1)
  }
})

test('native runtime rejection switches to software once instead of swallowing errors forever', async () => {
  let loads = 0, nativeCalls = 0
  class Native {
    static async getSupportedFormats() { return ['qr_code'] }
    async detect() { nativeCalls++; throw Error() }
  }
  const decoder = await createQrDecoder({ Detector: Native, loadFallback: async () => {
    loads++; return { decode: () => 'fallback', destroy() {} }
  } })
  assert.equal(await decoder.decode(frame), 'fallback'); assert.equal(await decoder.decode(frame), 'fallback')
  assert.equal(loads, 1); assert.equal(nativeCalls, 1)
  decoder.destroy()
})

test('unready video and native no-code frames do not report a scan or load software', async () => {
  let scans = 0
  class Native {
    static async getSupportedFormats() { return ['qr_code'] }
    async detect() { scans++; return [] }
  }
  const decoder = await createQrDecoder({ Detector: Native, loadFallback: () => { throw Error('unexpected') } })
  assert.equal(await decoder.decode({ ...frame, readyState: 1 }), null)
  assert.equal(await decoder.decode({ ...frame, videoWidth: 0 }), null)
  assert.equal(scans, 0); assert.equal(await decoder.decode(frame), null)
  decoder.destroy()
})

test('stop during asynchronous fallback loading disposes late resources and suppresses decoding', async () => {
  let release, destroyed = 0, decoded = 0
  class Native { static async getSupportedFormats() { return ['qr_code'] } async detect() { throw Error() } }
  const decoder = await createQrDecoder({ Detector: Native, loadFallback: () => new Promise(resolve => { release = resolve }) })
  const pending = decoder.decode(frame)
  await new Promise(resolve => setImmediate(resolve))
  decoder.destroy()
  release({ destroy() { destroyed++ }, decode() { decoded++ } })
  await assert.rejects(pending, { name: 'QrDecoderUnavailable' })
  assert.equal(destroyed, 1); assert.equal(decoded, 0)
})

test('fallback load errors never expose a token or underlying error details', async () => {
  await assert.rejects(createQrDecoder({ Detector: null, loadFallback: () => { throw Error('sensitive value') } }),
    error => error.name === 'QrDecoderUnavailable' && !error.message.includes('sensitive'))
})

test('software adapter bounds video frames, returns decoded text, and clears canvas on stop', () => {
  let drawn, reads = 0
  const canvas = { getContext: () => ({ drawImage(...args) { drawn = args } }) }
  const decoder = createCanvasQrReader({ decodeFromCanvas(input) { assert.equal(input, canvas); reads++; return { getText: () => 'synthetic' } } }, canvas, () => false)
  assert.equal(decoder.decode(frame), 'synthetic')
  assert.equal(canvas.width, 960); assert.equal(canvas.height, 540)
  assert.deepEqual(drawn, [frame, 0, 0, 960, 540])
  decoder.destroy(); assert.equal(canvas.width, 0); assert.equal(canvas.height, 0)
  assert.equal(decoder.decode(frame), null); assert.equal(reads, 1)
})

test('software ordinary blank/checksum frames continue and unexpected failures are sanitized', () => {
  const canvas = { getContext: () => ({ drawImage() {} }) }
  const empty = new Error('no code')
  const decoder = createCanvasQrReader({ decodeFromCanvas() { throw empty } }, canvas, error => error === empty)
  assert.equal(decoder.decode(frame), null)
  const broken = createCanvasQrReader({ decodeFromCanvas() { throw Error('sensitive') } }, canvas, () => false)
  assert.throws(() => broken.decode(frame), error => error.name === 'QrDecoderUnavailable' && !error.message.includes('sensitive'))
  assert.throws(() => createCanvasQrReader({}, { getContext: () => null }, () => false))
})

test('camera error guidance distinguishes denied, missing and busy devices without echoing values', () => {
  assert.match(cameraErrorMessage({ name: 'NotAllowedError' }), /permission was denied/)
  assert.match(cameraErrorMessage({ name: 'NotFoundError' }), /unavailable/)
  assert.match(cameraErrorMessage({ name: 'OverconstrainedError' }), /unavailable/)
  assert.match(cameraErrorMessage({ name: 'NotReadableError' }), /busy/)
  assert.match(cameraErrorMessage({ name: 'QrDecoderUnavailable' }), /reader could not load/)
  assert.doesNotMatch(cameraErrorMessage(new Error('secret')), /secret/)
})
