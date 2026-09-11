import { describe, expect, it } from 'vitest'
import { courses, navItems, sources, taskModes } from './mockData'

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
})
