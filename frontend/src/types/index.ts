export interface City {
  id: number
  name: string
  code: string
  province: string
}

export interface District {
  id: number
  city_id: number
  name: string
  code: string
}

export interface PriceInfo {
  region_type: string
  region_id: number
  region_name: string
  year_month: string
  supply_price: number
  attention_price: number | null
  value_price: number
}

export interface TrendPoint {
  year_month: string
  price: number
}

export interface TrendData {
  region_type: string
  region_id: number
  region_name: string
  price_type: string
  data: TrendPoint[]
}
