import test from 'node:test'
import assert from 'node:assert/strict'
import { safeVideoEmbed } from './videoPlayback.js'

test('only canonical approved players pass frontend defense in depth', () => {
  assert.equal(safeVideoEmbed({ provider: 'youtube', embed_url: 'https://www.youtube-nocookie.com/embed/aaaaaaaaaaa?playsinline=1' }), 'https://www.youtube-nocookie.com/embed/aaaaaaaaaaa?playsinline=1')
  assert.equal(safeVideoEmbed({ provider: 'vimeo', embed_url: 'https://player.vimeo.com/video/123456?dnt=1' }), 'https://player.vimeo.com/video/123456?dnt=1')
  for (const source of [null, {}, { provider: 'other', embed_url: 'https://player.vimeo.com/video/123456?dnt=1' }, ...[
    'javascript:alert(1)', 'http://www.youtube-nocookie.com/embed/aaaaaaaaaaa?playsinline=1',
    'https://www.youtube-nocookie.com.evil.invalid/embed/aaaaaaaaaaa?playsinline=1',
    'https://user@www.youtube-nocookie.com/embed/aaaaaaaaaaa?playsinline=1',
    'https://www.youtube-nocookie.com/embed/aaaaaaaaaaa?autoplay=1',
    'https://www.youtube-nocookie.com/embed/aaaaaaaaaaa?playsinline=1#fragment',
    'https://www.youtube-nocookie.com/embed/invalid?playsinline=1',
  ].map(embed_url => ({ provider: 'youtube', embed_url }))]) assert.equal(safeVideoEmbed(source), null)
})
