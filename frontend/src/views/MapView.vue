<script setup lang="ts">
import { fetchMapHeat } from '@/api/analytics'
import { fetchCities, fetchTrend } from '@/api/price'
import CitySelect from '@/components/CitySelect.vue'
import TrendLine from '@/components/TrendLine.vue'
import type { City, MapHeatItem, TrendPoint } from '@/types'
import * as echarts from 'echarts'
import { onMounted, onUnmounted, ref } from 'vue'

const cities = ref<City[]>([])
const selectedCity = ref<City | null>(null)
const heatItems = ref<MapHeatItem[]>([])
const geoMissing = ref(false)
const loading = ref(false)

const dialogVisible = ref(false)
const dialogDistrict = ref<MapHeatItem | null>(null)
const dialogTrend = ref<TrendPoint[]>([])

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null
const registeredMaps = new Set<string>()

async function loadGeoJson(cityCode: string): Promise<boolean> {
  if (registeredMaps.has(cityCode)) return true
  try {
    const resp = await fetch(`/geo/${cityCode}.json`)
    if (!resp.ok) return false
    const geoJson = await resp.json()
    if (!geoJson.features) return false
    echarts.registerMap(cityCode, geoJson)
    registeredMaps.add(cityCode)
    return true
  } catch {
    return false
  }
}

function renderChart(cityCode: string) {
  if (!chart) return

  const values = heatItems.value
    .filter((i) => i.price != null)
    .map((i) => ({ name: i.region_name, value: i.price as number }))
  const prices = values.map((v) => v.value)

  chart.setOption(
    {
      title: {
        text: `${selectedCity.value?.name ?? ''} 区县均价热力图`,
        left: 'center',
        textStyle: { fontSize: 16 },
      },
      tooltip: {
        trigger: 'item',
        formatter: (params: any) =>
          Number.isFinite(params.value) ? `${params.name}<br/>均价：${params.value} 元/㎡` : `${params.name}<br/>暂无数据`,
      },
      visualMap: {
        type: 'continuous',
        min: Math.min(...prices),
        max: Math.max(...prices),
        left: 20,
        bottom: 20,
        text: ['高', '低'],
        inRange: { color: ['#67C23A', '#E6A23C', '#F56C6C'] },
        calculable: true,
      },
      series: [
        {
          type: 'map',
          map: cityCode,
          label: { show: true, fontSize: 11 },
          emphasis: { label: { show: true }, itemStyle: { areaColor: '#409EFF' } },
          data: values,
        },
      ],
    },
    { notMerge: true },
  )
}

async function onCityChange(city: City) {
  selectedCity.value = city
  loading.value = true
  try {
    const hasGeo = await loadGeoJson(city.code)
    geoMissing.value = !hasGeo
    if (!hasGeo) return
    heatItems.value = (await fetchMapHeat(city.code)).data
    renderChart(city.code)
  } finally {
    loading.value = false
  }
}

async function onRegionClick(regionName: string) {
  const item = heatItems.value.find((i) => i.region_name === regionName)
  if (!item) return
  dialogDistrict.value = item
  dialogTrend.value = await fetchTrend('district', item.region_id, 12)
  dialogVisible.value = true
}

function onDialogOpened() {
  window.dispatchEvent(new Event('resize'))
}

onMounted(async () => {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    chart.on('click', (params) => {
      void onRegionClick(params.name)
    })
    window.addEventListener('resize', () => chart?.resize())
  }
  cities.value = await fetchCities()
  const qz = cities.value.find((c) => c.code === 'qz') ?? cities.value[0]
  if (qz) await onCityChange(qz)
})

onUnmounted(() => {
  chart?.dispose()
  window.removeEventListener('resize', () => chart?.resize())
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
      <div ref="chartRef" style="width: 100%; height: 560px"></div>
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
