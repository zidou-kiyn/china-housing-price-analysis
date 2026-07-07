<script setup lang="ts">
import type { CompareRegion } from '@/types'
import * as echarts from 'echarts'
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  regions: CompareRegion[]
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function renderChart() {
  if (!chart || !props.regions.length) return

  const months = [...new Set(props.regions.flatMap((r) => r.data.map((d) => d.year_month)))].sort()

  chart.setOption(
    {
      title: { text: '多区域均价走势对比', left: 'center', textStyle: { fontSize: 16 } },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value: unknown) => (value == null ? '-' : `${value} 元/㎡`),
      },
      legend: { bottom: 0, data: props.regions.map((r) => r.region_name) },
      xAxis: { type: 'category', data: months, axisLabel: { rotate: 45 } },
      yAxis: { type: 'value', name: '元/㎡', scale: true },
      series: props.regions.map((region) => {
        const byMonth = new Map(region.data.map((d) => [d.year_month, d.price]))
        return {
          name: region.region_name,
          type: 'line',
          smooth: true,
          connectNulls: true,
          data: months.map((m) => byMonth.get(m) ?? null),
        }
      }),
      grid: { left: 60, right: 20, bottom: 60, top: 50 },
    },
    { notMerge: true },
  )
}

onMounted(() => {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value)
    renderChart()
    window.addEventListener('resize', () => chart?.resize())
  }
})

onUnmounted(() => {
  chart?.dispose()
  window.removeEventListener('resize', () => chart?.resize())
})

watch(() => props.regions, renderChart, { deep: true })
</script>

<template>
  <div ref="chartRef" style="width: 100%; height: 420px"></div>
</template>
