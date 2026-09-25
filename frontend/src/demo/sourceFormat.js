export function formatSourceSubtitle(source) {
  const section = (source?.section_path || '').trim() || '未分类'
  const location = (source?.location || '').trim()
  return location ? `${section} · ${location}` : section
}
