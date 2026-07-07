<script setup lang="ts">
import type { DistrictOverviewItem } from '@/types'
import * as echarts from 'echarts'
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  data: DistrictOverviewItem[]
}>()

const emit = defineEmits<{
  select: [district: DistrictOverviewItem]
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function renderChart() {
  if (!chart || !props.data.length) return

  const names = props.data.map((d) => d.name)
  const prices = props.data.map((d) => d.supply_price ?? 0)

  chart.setOption({
    title: { text: '区县均价对比', left: 'center', textStyle: { fontSize: 16 } },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const p = params[0]
        return `${p.name}<br/>均价：${p.value} 元/㎡`
      },
    },
    xAxis: { type: 'category', data: names, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value', name: '元/㎡' },
    series: [
      {
        type: 'bar',
        data: prices,
        itemStyle: { color: '#409EFF', borderRadius: [4, 4, 0, 0] },
        emphasis: { itemStyle: { color: '#337ecc' } },
      },
    ],
    grid: { left: 60, right: 20, bottom: 60, top: 50 },
  })
}

onMounted(() => {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    chart.on('click', (params) => {
      const district = props.data[params.dataIndex]
      if (district) emit('select', district)
    })
    renderChart()
    window.addEventListener('resize', () => chart?.resize())
  }
})

onUnmounted(() => {
  chart?.dispose()
  window.removeEventListener('resize', () => chart?.resize())
})

watch(() => props.data, renderChart, { deep: true })
</script>

<template>
  <div ref="chartRef" style="width: 100%; height: 350px"></div>
</template>
