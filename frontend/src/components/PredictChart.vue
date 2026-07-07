<script setup lang="ts">
import type { PredictionPoint, TrendPoint } from '@/types'
import * as echarts from 'echarts'
import { onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  regionName: string
  history: TrendPoint[]
  predictions: PredictionPoint[]
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function renderChart() {
  if (!chart || !props.history.length || !props.predictions.length) return

  const historyMonths = props.history.map((d) => d.year_month)
  const predictMonths = props.predictions.map((d) => d.target_month)
  const months = [...historyMonths, ...predictMonths]
  const n = historyMonths.length

  const historyLine = [
    ...props.history.map((d) => d.supply_price),
    ...Array(predictMonths.length).fill(null),
  ]
  // 预测虚线：以最后一个历史点衔接
  const predictLine = [
    ...Array(n - 1).fill(null),
    props.history[n - 1].supply_price,
    ...props.predictions.map((d) => d.predicted_price),
  ]
  // 置信区间：stack 两条线（lower + 差值），areaStyle 填充带
  const lowerLine = [
    ...Array(n).fill(null),
    ...props.predictions.map((d) => d.confidence_lower),
  ]
  const bandLine = [
    ...Array(n).fill(null),
    ...props.predictions.map((d) =>
      d.confidence_upper != null && d.confidence_lower != null
        ? d.confidence_upper - d.confidence_lower
        : null,
    ),
  ]

  chart.setOption(
    {
      title: {
        text: `${props.regionName} 均价预测`,
        left: 'center',
        textStyle: { fontSize: 16 },
      },
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value: unknown) =>
          value == null ? '-' : `${Math.round(value as number)} 元/㎡`,
      },
      legend: { bottom: 0, data: ['历史均价', '预测均价'] },
      xAxis: { type: 'category', data: months, axisLabel: { rotate: 45 } },
      yAxis: { type: 'value', name: '元/㎡', scale: true },
      series: [
        {
          name: '历史均价',
          type: 'line',
          data: historyLine,
          smooth: true,
          itemStyle: { color: '#409EFF' },
        },
        {
          name: '预测均价',
          type: 'line',
          data: predictLine,
          smooth: true,
          lineStyle: { type: 'dashed', width: 2 },
          itemStyle: { color: '#E6A23C' },
          markLine: {
            symbol: 'none',
            label: { formatter: '预测起点' },
            lineStyle: { color: '#909399', type: 'dotted' },
            data: [{ xAxis: months[n - 1] }],
          },
        },
        {
          name: '置信下限',
          type: 'line',
          data: lowerLine,
          stack: 'ci',
          lineStyle: { opacity: 0 },
          symbol: 'none',
          tooltip: { show: false },
        },
        {
          name: '置信区间',
          type: 'line',
          data: bandLine,
          stack: 'ci',
          lineStyle: { opacity: 0 },
          symbol: 'none',
          areaStyle: { color: 'rgba(230, 162, 60, 0.2)' },
          tooltip: { show: false },
        },
      ],
      grid: { left: 60, right: 30, bottom: 60, top: 50 },
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

watch(() => [props.history, props.predictions], renderChart, { deep: true })
</script>

<template>
  <div ref="chartRef" style="width: 100%; height: 450px"></div>
</template>
