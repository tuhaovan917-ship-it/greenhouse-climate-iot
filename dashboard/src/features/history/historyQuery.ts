import type { Bucket } from '../../types/api'

export type HistoryRange = '15m' | '1h' | '6h' | '24h'

export interface HistoryQuery {
  bucket: Bucket
  range: HistoryRange
}

export const defaultHistoryQuery: HistoryQuery = {
  bucket: '5m',
  range: '24h',
}

const rangeDurationMs: Record<HistoryRange, number> = {
  '15m': 15 * 60 * 1_000,
  '1h': 60 * 60 * 1_000,
  '6h': 6 * 60 * 60 * 1_000,
  '24h': 24 * 60 * 60 * 1_000,
}

const allowedBucketsByRange: Record<HistoryRange, Bucket[]> = {
  '15m': ['raw', '1m', '5m', '1h'],
  '1h': ['1m', '5m', '1h'],
  '6h': ['1m', '5m', '1h'],
  '24h': ['5m', '1h'],
}

const fallbackBucketByRange: Record<HistoryRange, Bucket> = {
  '15m': 'raw',
  '1h': '1m',
  '6h': '1m',
  '24h': '5m',
}

export function getHistoryBounds(range: HistoryRange, nowMs = Date.now()) {
  return {
    from: new Date(nowMs - rangeDurationMs[range]).toISOString(),
    to: new Date(nowMs).toISOString(),
  }
}

export function isBucketAllowed(range: HistoryRange, bucket: Bucket) {
  return allowedBucketsByRange[range].includes(bucket)
}

export function normalizeHistoryQuery(query: HistoryQuery): HistoryQuery {
  if (isBucketAllowed(query.range, query.bucket)) {
    return query
  }

  return {
    ...query,
    bucket: fallbackBucketByRange[query.range],
  }
}
