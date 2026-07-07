import type { CompareResponse, MapHeatResponse, PriceType, RankResponse, RegionType } from '@/types'
import api from './index'

export function fetchRank(params: {
  region_type: RegionType
  city_code?: string
  sort_by?: PriceType
  sort_order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}): Promise<RankResponse> {
  return api.get('/rank', { params })
}

export function fetchCompare(params: {
  region_type: RegionType
  region_ids: string
  months?: number
  price_type?: PriceType
}): Promise<CompareResponse> {
  return api.get('/compare', { params })
}

export function fetchMapHeat(cityCode: string): Promise<MapHeatResponse> {
  return api.get('/map/heat', { params: { city_code: cityCode } })
}
