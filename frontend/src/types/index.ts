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
