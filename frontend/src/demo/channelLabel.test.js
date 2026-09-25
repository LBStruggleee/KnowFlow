import { describe, expect, it } from 'vitest'
import { formatChannelLabel } from './sourceFormat'

describe('formatChannelLabel', () => {
  it('labels hybrid mode', () => {
    expect(formatChannelLabel({ channels: { mode: 'hybrid', fused_by: 'rrf_k60' } })).toBe('混合检索')
  })

  it('labels single-channel modes', () => {
    expect(formatChannelLabel({ channels: { mode: 'vector' } })).toBe('语义检索')
    expect(formatChannelLabel({ channels: { mode: 'lexical' } })).toBe('词面检索')
  })

  it('marks LIKE fallback', () => {
    expect(formatChannelLabel({ channels: { mode: 'lexical', lexical: { fallback: 'like' } } })).toBe(
      '词面检索（兼容模式）',
    )
  })

  it('returns empty for missing trace', () => {
    expect(formatChannelLabel(null)).toBe('')
    expect(formatChannelLabel({})).toBe('')
    expect(formatChannelLabel({ channels: { mode: 'bogus' } })).toBe('')
  })
})
