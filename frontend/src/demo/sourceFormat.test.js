import { describe, expect, it } from 'vitest'
import { formatSourceSubtitle } from './sourceFormat'

describe('formatSourceSubtitle', () => {
  it('combines section path and location', () => {
    expect(formatSourceSubtitle({ section_path: '大数据导论 / 第一章', location: '第 2 个片段' })).toBe(
      '大数据导论 / 第一章 · 第 2 个片段',
    )
  })

  it('falls back to 未分类 when section path is missing', () => {
    expect(formatSourceSubtitle({ location: '第 1 个片段' })).toBe('未分类 · 第 1 个片段')
    expect(formatSourceSubtitle({ section_path: '  ', location: '第 1 个片段' })).toBe(
      '未分类 · 第 1 个片段',
    )
  })

  it('omits the separator when location is missing', () => {
    expect(formatSourceSubtitle({ section_path: '大数据导论 / 第一章' })).toBe('大数据导论 / 第一章')
    expect(formatSourceSubtitle({})).toBe('未分类')
  })
})
