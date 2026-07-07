<script setup lang="ts">
import { fetchMapHeat } from '@/api/analytics'
import { fetchCities, fetchTrend } from '@/api/price'
import CitySelect from '@/components/CitySelect.vue'
import HeatMap from '@/components/HeatMap.vue'
import TrendLine from '@/components/TrendLine.vue'
import type { City, MapHeatItem, TrendPoint } from '@/types'
import { loadGeoJson } from '@/utils/geo'
import { onMounted, ref } from 'vue'

const cities = ref<City[]>([])
const selectedCity = ref<City | null>(null)
const heatItems = ref<MapHeatItem[]>([])
const geoMissing = ref(false)
const loading = ref(false)

const dialogVisible = ref(false)
const dialogDistrict = ref<MapHeatItem | null>(null)
const dialogTrend = ref<TrendPoint[]>([])

async function onCityChange(city: City) {
  selectedCity.value = city
  loading.value = true
  try {
    const hasGeo = await loadGeoJson(city.code)
    geoMissing.value = !hasGeo
    if (!hasGeo) return
    heatItems.value = (await fetchMapHeat(city.code)).data
  } finally {
    loading.value = false
  }
}

async function onRegionSelect(item: MapHeatItem) {
  dialogDistrict.value = item
  dialogTrend.value = await fetchTrend('district', item.region_id, 12)
  dialogVisible.value = true
}

function onDialogOpened() {
  window.dispatchEvent(new Event('resize'))
}

onMounted(async () => {
  cities.value = await fetchCities()
  const qz = cities.value.find((c) => c.code === 'qz') ?? cities.value[0]
  if (qz) await onCityChange(qz)
})
</script>

<template>
  <div class="map-page">
    <div class="toolbar">
      <CitySelect :cities="cities" :model-value="selectedCity" @update:model-value="onCityChange" />
      <span class="hint">点击已着色区县查看走势</span>
    </div>

    <el-alert
      v-if="geoMissing"
      title="该城市暂无地图数据"
      type="info"
      :closable="false"
      show-icon
      class="geo-alert"
    />

    <el-card v-show="!geoMissing" v-loading="loading" shadow="hover">
      <HeatMap
        v-if="selectedCity && !geoMissing"
        :map-name="selectedCity.code"
        :items="heatItems"
        :title="`${selectedCity.name} 区县均价热力图`"
        @select="onRegionSelect"
      />
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="`${dialogDistrict?.region_name ?? ''} 近 12 个月走势`"
      width="720px"
      destroy-on-close
      @opened="onDialogOpened"
    >
      <TrendLine
        v-if="dialogDistrict"
        :title="dialogDistrict.region_name"
        :data="dialogTrend"
      />
    </el-dialog>
  </div>
</template>

<style scoped>
.map-page {
  max-width: 1200px;
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

.geo-alert {
  margin-bottom: 16px;
}
</style>
