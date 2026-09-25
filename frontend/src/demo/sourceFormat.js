export function formatSourceSubtitle(source) {
  const section = (source?.section_path || '').trim() || '未分类'
  const location = (source?.location || '').trim()
  return location ? `${section} · ${location}` : section
}

const CHANNEL_LABELS = { hybrid: '混合检索', vector: '语义检索', lexical: '词面检索' }

export function formatChannelLabel(trace) {
  const mode = trace?.channels?.mode
  const label = CHANNEL_LABELS[mode] || ''
  if (!label) return ''
  if (mode === 'lexical' && trace.channels.lexical?.fallback) return `${label}（兼容模式）`
  return label
}
