import type { CompareResponse, MapHeatResponse, PriceType, RankResponse, RegionType } from '@/types'
import api from './index'

export function fetchRank(params: {
  region_type: RegionType
  city_code?: string
  sort_by?: PriceType
  sort_order?: 'asc' | 'desc'
  page?: number
  page_size?: number
  source?: string
}): Promise<RankResponse> {
  return api.get('/rank', { params })
}

export function fetchCompare(params: {
  region_type: RegionType
  region_ids: string
  months?: number
  price_type?: PriceType
  source?: string
}): Promise<CompareResponse> {
  return api.get('/compare', { params })
}

export function fetchMapHeat(cityCode: string, source?: string): Promise<MapHeatResponse> {
  const params: Record<string, string> = { city_code: cityCode }
  if (source) params.source = source
  return api.get('/map/heat', { params })
}
