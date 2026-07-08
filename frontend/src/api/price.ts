import type {
  City,
  District,
  DistributionItem,
  DistrictOverviewItem,
  IndexTrendPoint,
  TrendPoint,
  TrendSeries,
} from '@/types'
import api from './index'

export function fetchCities(): Promise<City[]> {
  return api.get('/cities')
}

export function fetchDistricts(cityCode: string): Promise<District[]> {
  return api.get(`/cities/${cityCode}/districts`)
}

export function fetchTrend(
  regionType: string,
  regionId: number,
  months?: number,
  source?: string,
): Promise<TrendPoint[]> {
  const params: Record<string, string | number> = { region_type: regionType, region_id: regionId }
  if (months) params.months = months
  if (source) params.source = source
  return api.get('/prices/trend', { params })
}

export function fetchTrendSeries(regionType: string, regionId: number): Promise<TrendSeries[]> {
  return api.get('/prices/trend/series', {
    params: { region_type: regionType, region_id: regionId },
  })
}

/** NBS 房价指数走势（二手房环比，单位=指数非价格）。切换器选「官方指数」源时用。 */
export function fetchIndexTrend(regionType: string, regionId: number): Promise<IndexTrendPoint[]> {
  return api.get('/prices/index/trend', {
    params: { region_type: regionType, region_id: regionId },
  })
}

export function fetchDistribution(
  regionType: string,
  regionId: number,
  source?: string,
): Promise<DistributionItem[]> {
  const params: Record<string, string | number> = { region_type: regionType, region_id: regionId }
  if (source) params.source = source
  return api.get('/prices/distribution', { params })
}

export function fetchOverview(cityCode: string, source?: string): Promise<DistrictOverviewItem[]> {
  const params: Record<string, string> = { city_code: cityCode }
  if (source) params.source = source
  return api.get('/prices/overview', { params })
}
