// Bundled locally and loaded only when native decoding is unavailable/fails.
import { BrowserQRCodeReader } from '@zxing/browser'
import { NotFoundException, ChecksumException, FormatException } from '@zxing/library'
import { createCanvasQrReader } from './qrDecoder.js'

export function createQrFallback({ createCanvas = () => document.createElement('canvas'),
  reader = new BrowserQRCodeReader() } = {}) {
  return createCanvasQrReader(reader, createCanvas(), error => error instanceof NotFoundException
    || error instanceof ChecksumException || error instanceof FormatException)
}
