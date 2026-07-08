import { ref } from 'vue'
import type {
  City,
  DistributionItem,
  DistrictOverviewItem,
  IndexTrendPoint,
  TrendSeries,
} from '@/types'
import {
  fetchCities,
  fetchDistribution,
  fetchIndexTrend,
  fetchOverview,
  fetchTrendSeries,
} from '@/api/price'
import { useSourceStore } from '@/stores/source'

export function usePrice() {
  const source = useSourceStore()

  const cities = ref<City[]>([])
  const overview = ref<DistrictOverviewItem[]>([])
  // 源硬隔离：走势按当前源单线渲染（trend/series 结果过滤到所选源，非跨源混合）
  const cityTrend = ref<TrendSeries[]>([])
  const districtTrend = ref<TrendSeries[]>([])
  const distribution = ref<DistributionItem[]>([])
  // 指数源（nbs）：走势走独立指数序列，overview/distribution 不适用
  const cityIndex = ref<IndexTrendPoint[]>([])
  const districtIndex = ref<IndexTrendPoint[]>([])
  const selectedCity = ref<City | null>(null)
  const selectedDistrict = ref<DistrictOverviewItem | null>(null)
  const loading = ref(false)

  async function loadCities() {
    cities.value = await fetchCities()
  }

  function _resetDistrict() {
    selectedDistrict.value = null
    districtTrend.value = []
    districtIndex.value = []
  }

  async function selectCity(city: City) {
    selectedCity.value = city
    _resetDistrict()
    loading.value = true
    try {
      if (source.isIndexSource) {
        // 指数源：城市指数走势有意义；均价概览/分布口径不适用，置空由视图空态兜底
        cityIndex.value = await fetchIndexTrend('city', city.id)
        overview.value = []
        cityTrend.value = []
        distribution.value = []
        return
      }
      cityIndex.value = []
      const [ov, trend, dist] = await Promise.all([
        fetchOverview(city.code, source.priceSource),
        fetchTrendSeries('city', city.id),
        fetchDistribution('city', city.id, source.priceSource),
      ])
      overview.value = ov
      // 只保留当前源的分线，源硬隔离下不同时展示他源
      cityTrend.value = trend.filter((s) => s.source === source.current)
      distribution.value = dist
    } finally {
      loading.value = false
    }
  }

  async function selectDistrict(district: DistrictOverviewItem) {
    selectedDistrict.value = district
    loading.value = true
    try {
      if (source.isIndexSource) {
        districtIndex.value = await fetchIndexTrend('district', district.id)
        districtTrend.value = []
        return
      }
      districtIndex.value = []
      const trend = await fetchTrendSeries('district', district.id)
      districtTrend.value = trend.filter((s) => s.source === source.current)
    } finally {
      loading.value = false
    }
  }

  return {
    cities,
    overview,
    cityTrend,
    districtTrend,
    distribution,
    cityIndex,
    districtIndex,
    selectedCity,
    selectedDistrict,
    loading,
    loadCities,
    selectCity,
    selectDistrict,
  }
}
