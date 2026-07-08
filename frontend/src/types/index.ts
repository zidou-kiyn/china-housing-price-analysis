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
  /** 该点数据来源（price_snapshot.source），用于标注口径（如年度·挂牌） */
  source: string | null
}

export interface TrendSeries {
  source: string
  granularity: 'monthly' | 'annual' | string
  basis: 'listing' | 'transaction' | string
  points: TrendPoint[]
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
  /** 最新值的数据来源，口径标注用（如年度·挂牌） */
  source: string | null
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
  /** 该点数据来源（口径标注用） */
  source?: string | null
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

// 预测依据序列的口径：真实月度 | 年度挂牌插值 | 混合
export type PredictDataQuality = 'monthly' | 'annual_interp' | 'mixed'

export interface PredictionResponse {
  region_type: RegionType
  region_id: number
  region_name: string
  model_name: string
  model_version: string
  data_quality: PredictDataQuality
  predictions: PredictionPoint[]
}

// ---- 管理端后台任务与数据采集 ----

export interface AdminJob {
  id: number
  kind: 'collect' | 'geo_fetch' | 'train' | 'import_index'
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

export interface ModelVersion {
  model_name: string
  version: string
  trained_at: string
  metrics: Record<string, number>
  training_samples: number
  is_active: boolean
  is_best: boolean
  beats_baseline: boolean | null
  baseline_mape: number | null
}

export interface ModelCleanupResult {
  keep_last: number
  deleted: { model_name: string; version: string }[]
}

export interface ProxySetting {
  enabled: boolean
  url_masked: string | null
  has_url: boolean
}

export interface ProxyTestResult {
  ok: boolean
  status_code: number | null
  elapsed_ms: number | null
  error: string | null
}

export interface CollectSource {
  name: string
  capabilities: string[]
  price_unit: string
}

export interface CollectScheduleState {
  last_run_date?: string
  last_run_at?: string
  last_job_id?: number
  last_error?: string
  expand_cursor?: number
  last_result?: {
    submitted: number
    ok?: number
    failed?: number
    circuit_broken?: boolean
    skipped?: string[]
    note?: string
  }
}

export interface CollectScheduleSetting {
  enabled: boolean
  time: string
  batch: number
  state: CollectScheduleState | null
}

export interface CollectSourcesResponse {
  current: string
  items: CollectSource[]
}

export interface AnnualImportResult {
  source: string
  matched: number
  skipped_count: number
  skipped_cities: string[]
  snapshots: number
  /** snapshot_validator 计数：值域/格式拦截、批内跳变标记 */
  rejected?: number
  flagged?: number
}

// NBS 指数导入统计（import_index 任务 result[0]）
export interface IndexImportStats {
  ok: boolean
  source: string
  matched: number
  skipped: string[]
  rows: number
  months_range: [string, string] | null
}

// ---- 数据质量审计报告（GET /admin/data-quality/report） ----

export interface DirectionConsistencySection {
  /** ok | no overlap | "no index data"（指数未导入降级） */
  status: string
  regions: number
  compared: number
  matches: number
  agreement_rate: number | null
  flat_excluded: number
  skipped_missing_index: number
  note: string | null
}

export interface SourceCoverage {
  source: string
  kind: 'snapshot' | 'index'
  granularity: string | null
  basis: string | null
  regions: number
  rows: number
  latest_month: string
  months_behind: number
}

export interface ModelFreshness {
  status: 'fresh' | 'stale' | 'unknown'
  model_name: string | null
  model_version: string | null
  trained_at: string | null
  model_fingerprint: string | null
  data_fingerprint: string | null
  note: string | null
}

export interface DataQualityReport {
  generated_at: string
  overlap_ratio: {
    pairs: number
    outliers_total: number
    outliers: Array<Record<string, unknown>>
    ratio_median: number | null
  }
  creprice_vs_index: DirectionConsistencySection
  annual_vs_index: DirectionConsistencySection
  coverage: SourceCoverage[]
  model_freshness: ModelFreshness
}
