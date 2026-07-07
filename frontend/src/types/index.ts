export interface City {
  id: number
  name: string
  code: string
}

export interface District {
  id: number
  name: string
  code: string
}

export interface TrendPoint {
  year_month: string
  supply_price: number | null
  attention_price: number | null
  value_price: number | null
  sample_count: number | null
}

export interface DistributionItem {
  price_range_low: number
  price_range_high: number
  percentage: number | null
  count: number | null
}

export interface DistrictOverviewItem {
  id: number
  name: string
  code: string
  supply_price: number | null
  attention_price: number | null
  value_price: number | null
}

export type RegionType = 'city' | 'district'
export type PriceType = 'supply_price' | 'attention_price' | 'value_price'

export interface RankItem {
  region_id: number
  region_name: string
  year_month: string | null
  supply_price: number | null
  attention_price: number | null
  value_price: number | null
  yoy_pct: number | null
  mom_pct: number | null
}

export interface RankResponse {
  total: number
  page: number
  page_size: number
  items: RankItem[]
}

export interface ComparePoint {
  year_month: string
  price: number | null
}

export interface CompareRegion {
  region_id: number
  region_name: string
  data: ComparePoint[]
}

export interface CompareResponse {
  price_type: PriceType
  regions: CompareRegion[]
}

export interface MapHeatItem {
  region_id: number
  region_name: string
  price: number | null
}

export interface MapHeatResponse {
  city_code: string
  region_type: RegionType
  data: MapHeatItem[]
}

export interface User {
  id: number
  username: string
  email: string
  role: string
  is_active: boolean
}

export interface UserAdmin extends User {
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface UserListResponse {
  total: number
  page: number
  page_size: number
  items: UserAdmin[]
}

export interface PredictionPoint {
  target_month: string
  predicted_price: number
  confidence_lower: number | null
  confidence_upper: number | null
}

export interface PredictionResponse {
  region_type: RegionType
  region_id: number
  region_name: string
  model_name: string
  model_version: string
  predictions: PredictionPoint[]
}

// ---- 管理端后台任务与数据采集 ----

export interface AdminJob {
  id: number
  kind: 'collect' | 'geo_fetch' | 'train'
  status: 'pending' | 'running' | 'success' | 'failed'
  payload: Record<string, unknown> | null
  progress_done: number
  progress_total: number
  result: Array<Record<string, unknown>> | null
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface AdminJobListResponse {
  total: number
  page: number
  page_size: number
  items: AdminJob[]
}

export interface CityCoverage {
  id: number
  name: string
  code: string
  province: string | null
  district_count: number
  latest_month: string | null
  has_geo: boolean
}

export interface CityCoverageListResponse {
  total: number
  page: number
  page_size: number
  items: CityCoverage[]
}
