export function getEvidencePanelState(isOpen, sourceCount) {
  return {
    stateClass: isOpen ? 'expanded' : 'collapsed',
    toggleLabel: isOpen ? '收起回答依据' : '展开回答依据',
    sourceSummary: `${sourceCount} 个来源`,
  }
}
