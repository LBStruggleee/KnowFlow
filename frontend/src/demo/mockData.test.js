import { describe, expect, it } from 'vitest'
import {
  courses,
  documents,
  learningRecords,
  navItems,
  providerOptions,
  sources,
  taskModes,
} from './mockData'

describe('KnowFlow demo data', () => {
  it('covers every primary product area', () => {
    expect(navItems.map((item) => item.id)).toEqual([
      'assistant',
      'knowledge',
      'records',
      'settings',
    ])
  })

  it('provides a complete evidence-backed learning example', () => {
    expect(courses.length).toBeGreaterThanOrEqual(3)
    expect(taskModes).toContain('练习生成')
    expect(sources).toHaveLength(3)
    expect(sources.every((source) => source.location && source.excerpt)).toBe(true)
  })

  it('covers the simulated knowledge ingestion states', () => {
    expect(new Set(documents.map((document) => document.status))).toEqual(
      new Set(['ready', 'processing', 'failed']),
    )
    expect(documents.every((document) => document.name && document.type && document.tags)).toBe(true)
    expect(documents.filter((document) => document.status === 'ready').every((document) => document.chunks > 0)).toBe(true)
  })

  it('provides representative learning records and provider roles', () => {
    expect(new Set(learningRecords.map((record) => record.type))).toEqual(
      new Set(['conversation', 'note', 'exercise', 'mistake']),
    )
    expect(providerOptions.map((provider) => provider.role)).toEqual([
      '回答模型',
      'Embedding',
      '相关性重排',
    ])
    expect(providerOptions.every((provider) => provider.location && provider.status === '可用')).toBe(true)
  })
})
