import { describe, expect, it } from 'vitest'
import { getEvidencePanelState } from './evidencePanelState'

describe('evidence panel state', () => {
  it('describes the expanded panel action', () => {
    expect(getEvidencePanelState(true, 3)).toEqual({
      stateClass: 'expanded',
      toggleLabel: '收起回答依据',
      sourceSummary: '3 个来源',
    })
  })

  it('describes the collapsed capsule action', () => {
    expect(getEvidencePanelState(false, 3)).toEqual({
      stateClass: 'collapsed',
      toggleLabel: '展开回答依据',
      sourceSummary: '3 个来源',
    })
  })
})
