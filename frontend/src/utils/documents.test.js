import { describe, expect, it } from 'vitest'

import { countFinishedDocuments, hasProcessingDocuments, sumChunkCounts } from './documents'

describe('document statistics', () => {
  it('sums valid chunk counts without preview-state leakage', () => {
    const documents = [
      { chunk_count: 2 },
      { chunk_count: '3' },
      { chunk_count: null },
      { chunk_count: -1 },
    ]

    expect(sumChunkCounts(documents)).toBe(5)
  })

  it('counts only finished documents', () => {
    expect(
      countFinishedDocuments([
        { status: 'finished' },
        { status: 'failed' },
        { status: 'processing' },
      ]),
    ).toBe(1)
  })

  it('detects whether document status polling is needed', () => {
    expect(hasProcessingDocuments([{ status: 'finished' }, { status: 'processing' }])).toBe(true)
    expect(hasProcessingDocuments([{ status: 'finished' }, { status: 'failed' }])).toBe(false)
  })
})
