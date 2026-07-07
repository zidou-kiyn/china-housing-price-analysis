import type { City, District, DistributionItem, DistrictOverviewItem, TrendPoint } from '@/types'
import api from './index'

export function fetchCities(): Promise<City[]> {
  return api.get('/cities')
}

export function fetchDistricts(cityCode: string): Promise<District[]> {
  return api.get(`/cities/${cityCode}/districts`)
}

export function fetchTrend(regionType: string, regionId: number, months?: number): Promise<TrendPoint[]> {
  const params: Record<string, string | number> = { region_type: regionType, region_id: regionId }
  if (months) params.months = months
  return api.get('/prices/trend', { params })
}

export function fetchDistribution(regionType: string, regionId: number): Promise<DistributionItem[]> {
  return api.get('/prices/distribution', { params: { region_type: regionType, region_id: regionId } })
}

export function fetchOverview(cityCode: string): Promise<DistrictOverviewItem[]> {
  return api.get('/prices/overview', { params: { city_code: cityCode } })
}
