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
        formatter: (params: any) => {
          let text = params[0].axisValue
          const month = params[0].axisValue
          for (const p of params) {
            if (p.value == null) continue
            // 该区域该月的数据来源，年度挂牌点标注口径
            const source = props.regions[p.seriesIndex]?.data.find(
              (d) => d.year_month === month,
            )?.source
            const tag = source?.startsWith('listing_annual')
              ? ' <span style="color:#E6A23C">(年度·挂牌)</span>'
              : ''
            text += `<br/>${p.marker} ${p.seriesName}：${p.value} 元/㎡${tag}`
          }
          return text
        },
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
