import test from 'node:test'
import assert from 'node:assert/strict'
import { hostedVideoThumbnail } from './hostedVideoThumbnail.js'

test('canonical approved YouTube player gives one recognizable thumbnail without API keys', () => {
  assert.equal(
    hostedVideoThumbnail('https://www.youtube-nocookie.com/embed/9y_VVCo5qbE?playsinline=1'),
    'https://i.ytimg.com/vi/9y_VVCo5qbE/hqdefault.jpg'
  )
})

test('invalid URLs and non-deterministic Vimeo video posters fall back safely', () => {
  for (const value of [
    '', 'javascript:alert(1)', 'https://evil.example/embed/9y_VVCo5qbE?playsinline=1',
    'https://www.youtube-nocookie.com.evil.example/embed/9y_VVCo5qbE?playsinline=1',
    'https://user@www.youtube-nocookie.com/embed/9y_VVCo5qbE?playsinline=1',
    'https://www.youtube-nocookie.com/embed/9y_VVCo5qbE?autoplay=1',
    'https://www.youtube-nocookie.com/embed/9y_VVCo5qbE?playsinline=1#x',
    'https://www.youtube-nocookie.com/embed/not-valid?playsinline=1',
    'https://player.vimeo.com/video/123456?dnt=1',
    null
  ]) assert.equal(hostedVideoThumbnail(value), '')
})
