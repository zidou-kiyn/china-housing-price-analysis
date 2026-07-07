<script setup lang="ts">
import type { TrendPoint } from '@/types'
import * as echarts from 'echarts'
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  title: string
  data: TrendPoint[]
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function renderChart() {
  if (!chart || !props.data.length) return

  const months = props.data.map((d) => d.year_month)

  chart.setOption({
    title: { text: props.title, left: 'center', textStyle: { fontSize: 16 } },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        let text = params[0].axisValue
        for (const p of params) {
          text += `<br/>${p.marker} ${p.seriesName}：${p.value ?? '-'} 元/㎡`
        }
        return text
      },
    },
    legend: { bottom: 0, data: ['供给价', '价值价'] },
    xAxis: { type: 'category', data: months, axisLabel: { rotate: 45 } },
    yAxis: { type: 'value', name: '元/㎡' },
    series: [
      {
        name: '供给价',
        type: 'line',
        data: props.data.map((d) => d.supply_price),
        smooth: true,
        lineStyle: { width: 2 },
        itemStyle: { color: '#409EFF' },
      },
      {
        name: '价值价',
        type: 'line',
        data: props.data.map((d) => d.value_price),
        smooth: true,
        lineStyle: { width: 2, type: 'dashed' },
        itemStyle: { color: '#67C23A' },
      },
    ],
    grid: { left: 60, right: 20, bottom: 50, top: 50 },
  })
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

watch(() => [props.data, props.title], renderChart, { deep: true })
</script>

<template>
  <div ref="chartRef" style="width: 100%; height: 350px"></div>
</template>
