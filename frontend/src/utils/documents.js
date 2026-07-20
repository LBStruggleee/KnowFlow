export function sumChunkCounts(documents) {
  return documents.reduce((total, document) => {
    const count = Number(document.chunk_count)
    return total + (Number.isFinite(count) && count > 0 ? count : 0)
  }, 0)
}

export function countFinishedDocuments(documents) {
  return documents.filter((document) => document.status === 'finished').length
}
