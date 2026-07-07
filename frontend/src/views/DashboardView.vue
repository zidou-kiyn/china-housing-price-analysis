<script setup lang="ts">
import { fetchMapHeat } from '@/api/analytics'
import { fetchCities, fetchDistribution, fetchOverview, fetchTrend } from '@/api/price'
import CitySelect from '@/components/CitySelect.vue'
import DistrictBar from '@/components/DistrictBar.vue'
import DistributionPie from '@/components/DistributionPie.vue'
import HeatMap from '@/components/HeatMap.vue'
import TrendLine from '@/components/TrendLine.vue'
import type {
  City,
  DistributionItem,
  DistrictOverviewItem,
  MapHeatItem,
  TrendPoint,
} from '@/types'
import { loadGeoJson } from '@/utils/geo'
import { computed, onMounted, ref } from 'vue'

interface SelectedRegion {
  type: 'city' | 'district'
  id: number
  name: string
}

const cities = ref<City[]>([])
const selectedCity = ref<City | null>(null)
const geoMissing = ref(false)
const loading = ref(false)

const heatItems = ref<MapHeatItem[]>([])
const overview = ref<DistrictOverviewItem[]>([])
const selected = ref<SelectedRegion | null>(null)
const trend = ref<TrendPoint[]>([])
const distribution = ref<DistributionItem[]>([])

const selectedDistrictName = computed(() =>
  selected.value?.type === 'district' ? selected.value.name : null,
)

async function loadRegionCharts() {
  if (!selected.value) return
  const { type, id } = selected.value
  const [t, d] = await Promise.all([fetchTrend(type, id, 12), fetchDistribution(type, id)])
  trend.value = t
  distribution.value = d
}

async function onCityChange(city: City) {
  selectedCity.value = city
  selected.value = { type: 'city', id: city.id, name: city.name }
  loading.value = true
  try {
    const hasGeo = await loadGeoJson(city.code)
    geoMissing.value = !hasGeo
    const [heat, ov] = await Promise.all([
      hasGeo ? fetchMapHeat(city.code) : Promise.resolve(null),
      fetchOverview(city.code),
      loadRegionCharts(),
    ])
    heatItems.value = heat?.data ?? []
    overview.value = ov
  } finally {
    loading.value = false
  }
}

function selectDistrict(id: number, name: string) {
  selected.value = { type: 'district', id, name }
  void loadRegionCharts()
}

function onMapSelect(item: MapHeatItem) {
  selectDistrict(item.region_id, item.region_name)
}

function onBarSelect(district: DistrictOverviewItem) {
  selectDistrict(district.id, district.name)
}

function resetToCity() {
  if (!selectedCity.value) return
  const city = selectedCity.value
  selected.value = { type: 'city', id: city.id, name: city.name }
  void loadRegionCharts()
}

onMounted(async () => {
  cities.value = await fetchCities()
  const qz = cities.value.find((c) => c.code === 'qz') ?? cities.value[0]
  if (qz) await onCityChange(qz)
})
</script>

<template>
  <div class="dashboard-page" v-loading="loading">
    <div class="toolbar">
      <CitySelect :cities="cities" :model-value="selectedCity" @update:model-value="onCityChange" />
      <el-tag v-if="selected" :type="selected.type === 'district' ? 'warning' : 'info'" size="large">
        当前区域：{{ selected.name }}
      </el-tag>
      <el-button v-if="selectedDistrictName" size="small" @click="resetToCity">返回全市</el-button>
      <span class="hint">点击地图或柱状图区县，走势与分布同步切换</span>
    </div>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="hover" class="panel">
          <el-alert
            v-if="geoMissing"
            title="该城市暂无地图数据"
            type="info"
            :closable="false"
            show-icon
          />
          <HeatMap
            v-else-if="selectedCity"
            :map-name="selectedCity.code"
            :items="heatItems"
            :title="`${selectedCity.name} 区县均价热力图`"
            :selected-name="selectedDistrictName"
            height="400px"
            @select="onMapSelect"
          />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover" class="panel">
          <DistrictBar :data="overview" :selected-name="selectedDistrictName" @select="onBarSelect" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="second-row">
      <el-col :span="12">
        <el-card shadow="hover" class="panel">
          <TrendLine :title="`${selected?.name ?? ''} 近 12 个月走势`" :data="trend" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover" class="panel">
          <el-empty
            v-if="!distribution.length"
            :description="`${selected?.name ?? ''} 暂无价格分布数据`"
            :image-size="80"
          />
          <DistributionPie v-else :data="distribution" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.dashboard-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.hint {
  color: #909399;
  font-size: 13px;
}

.second-row {
  margin-top: 16px;
}

.panel :deep(.el-card__body) {
  min-height: 400px;
}
</style>
