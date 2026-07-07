import { ref } from 'vue'
import type { City, DistributionItem, DistrictOverviewItem, TrendPoint } from '@/types'
import { fetchCities, fetchDistribution, fetchOverview, fetchTrend } from '@/api/price'

export function usePrice() {
  const cities = ref<City[]>([])
  const overview = ref<DistrictOverviewItem[]>([])
  const cityTrend = ref<TrendPoint[]>([])
  const districtTrend = ref<TrendPoint[]>([])
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
        fetchTrend('city', city.id),
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
      districtTrend.value = await fetchTrend('district', district.id)
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
