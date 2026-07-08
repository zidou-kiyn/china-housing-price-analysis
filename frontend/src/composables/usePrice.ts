import { ref } from 'vue'
import type { City, DistributionItem, DistrictOverviewItem, TrendSeries } from '@/types'
import { fetchCities, fetchDistribution, fetchOverview, fetchTrendSeries } from '@/api/price'

export function usePrice() {
  const cities = ref<City[]>([])
  const overview = ref<DistrictOverviewItem[]>([])
  // 按源分线的走势序列（源独立存储后，避免跨口径硬连线）
  const cityTrend = ref<TrendSeries[]>([])
  const districtTrend = ref<TrendSeries[]>([])
  const distribution = ref<DistributionItem[]>([])
  const selectedCity = ref<City | null>(null)
  const selectedDistrict = ref<DistrictOverviewItem | null>(null)
  const loading = ref(false)

  async function loadCities() {
    cities.value = await fetchCities()
  }

  async function selectCity(city: City) {
    selectedCity.value = city
    selectedDistrict.value = null
    districtTrend.value = []
    loading.value = true
    try {
      const [ov, trend, dist] = await Promise.all([
        fetchOverview(city.code),
        fetchTrendSeries('city', city.id),
        fetchDistribution('city', city.id),
      ])
      overview.value = ov
      cityTrend.value = trend
      distribution.value = dist
    } finally {
      loading.value = false
    }
  }

  async function selectDistrict(district: DistrictOverviewItem) {
    selectedDistrict.value = district
    loading.value = true
    try {
      districtTrend.value = await fetchTrendSeries('district', district.id)
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
    selectedCity,
    selectedDistrict,
    loading,
    loadCities,
    selectCity,
    selectDistrict,
  }
}
