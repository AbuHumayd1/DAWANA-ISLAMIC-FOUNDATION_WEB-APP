// Camera ownership stays with CamperScanner. Decoding never calls an operational API.
export async function createQrDecoder({
  Detector = globalThis.BarcodeDetector,
  loadFallback = async () => (await import('./qrFallback.js')).createQrFallback(),
} = {}) {
  let native = null, fallback = null, loading = null, disposed = false
  const unavailable = () => Object.assign(new Error('QR reader could not load. Retry or use manual lookup.'), { name: 'QrDecoderUnavailable' })
  async function software() {
    if (disposed) throw unavailable()
    if (!loading) loading = Promise.resolve().then(loadFallback).then(reader => {
      if (disposed) { reader.destroy(); throw unavailable() }
      fallback = reader
      return reader
    }).catch(() => { throw unavailable() })
    return loading
  }
  try {
    if (Detector && typeof Detector.getSupportedFormats === 'function'
        && (await Detector.getSupportedFormats()).includes('qr_code')) {
      native = new Detector({ formats: ['qr_code'] })
    }
  } catch { /* Partial/disabled native implementations use the software reader. */ }
  if (!native) await software()
  return {
    async decode(video) {
      if (disposed || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return null
      if (native) {
        try { return (await native.detect(video))[0]?.rawValue || null }
        catch { native = null } // Do not loop forever on a broken native decoder.
      }
      return (await software()).decode(video)
    },
    destroy() { disposed = true; native = null; fallback?.destroy(); fallback = null },
  }
}

export function cameraErrorMessage(error) {
  if (error?.name === 'NotAllowedError' || error?.name === 'SecurityError') return 'Camera permission was denied. Allow access in your browser, or use manual lookup.'
  if (error?.name === 'NotFoundError' || error?.name === 'OverconstrainedError') return 'The selected camera is unavailable. Choose another camera or use manual lookup.'
  if (error?.name === 'NotReadableError') return 'The camera is busy or could not start. Close other camera apps or choose another device.'
  if (error?.name === 'QrDecoderUnavailable') return 'QR reader could not load. Retry or use manual lookup.'
  return 'Camera scanning failed. Try another camera, retry, or use manual lookup.'
}

export function createCanvasQrReader(reader, canvas, isEmptyFrame) {
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) throw new Error('QR canvas unavailable.')
  let disposed = false
  return {
    decode(video) {
      if (disposed) return null
      const scale = Math.min(1, 960 / Math.max(video.videoWidth, video.videoHeight))
      canvas.width = Math.max(1, Math.round(video.videoWidth * scale))
      canvas.height = Math.max(1, Math.round(video.videoHeight * scale))
      context.drawImage(video, 0, 0, canvas.width, canvas.height)
      try { return reader.decodeFromCanvas(canvas).getText() }
      catch (error) {
        if (isEmptyFrame(error)) return null
        throw Object.assign(new Error('QR frame could not be read.'), { name: 'QrDecoderUnavailable' })
      }
    },
    destroy() { disposed = true; canvas.width = 0; canvas.height = 0 },
  }
}
