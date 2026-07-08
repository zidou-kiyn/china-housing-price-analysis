<script setup lang="ts">
import { fetchPrediction } from '@/api/predict'
import { fetchTrend } from '@/api/price'
import PredictChart from '@/components/PredictChart.vue'
import { useSourceStore } from '@/stores/source'
import type { PredictionResponse, RegionType, TrendPoint } from '@/types'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const source = useSourceStore()

const history = ref<TrendPoint[]>([])
const prediction = ref<PredictionResponse | null>(null)
const errorMessage = ref('')
const loading = ref(false)

const regionType = computed(() => route.params.regionType as RegionType)
const regionId = computed(() => Number(route.params.id))

// 数据口径标注（沿用走势图「年度·挂牌」口径标签的文案风格）
const qualityTag = computed(() => {
  if (prediction.value?.data_quality === 'annual_interp')
    return {
      type: 'warning' as const,
      label: '年度挂牌推算',
      tip: '该区域缺少月度行情数据，预测基于年度挂牌数据校准插值推算，置信区间已放大',
    }
  if (prediction.value?.data_quality === 'mixed')
    return {
      type: 'info' as const,
      label: '混合口径',
      tip: '历史序列由月度行情与年度挂牌校准数据混合构成',
    }
  return null
})

async function load() {
  if (!regionId.value || !['city', 'district'].includes(regionType.value)) {
    errorMessage.value = '无效的区域参数'
    return
  }
  loading.value = true
  errorMessage.value = ''
  prediction.value = null
  try {
    const [trend, pred] = await Promise.all([
      fetchTrend(regionType.value, regionId.value),
      fetchPrediction(regionType.value, regionId.value),
    ])
    history.value = trend
    prediction.value = pred
  } catch (error: any) {
    errorMessage.value = error.response?.data?.detail ?? '加载预测失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => route.params, load)
</script>

<template>
  <div class="predict-page" v-loading="loading">
    <!-- R5：预测仅基于 creprice 实采数据，非 creprice 源下显式说明 -->
    <el-alert
      v-if="!source.isCreprice"
      type="info"
      :closable="false"
      show-icon
      title="预测仅基于 creprice（禧泰月度）实采数据，请将顶栏数据源切回「禧泰 · 月度」查看预测"
      class="src-alert"
    />

    <template v-else-if="prediction">
      <div class="meta-bar">
        <h2>{{ prediction.region_name }} · 未来 {{ prediction.predictions.length }} 个月预测</h2>
        <el-tag size="small" type="info">
          模型：{{ prediction.model_name }} {{ prediction.model_version }}
        </el-tag>
        <el-tooltip v-if="qualityTag" :content="qualityTag.tip" placement="top">
          <el-tag size="small" :type="qualityTag.type">{{ qualityTag.label }}</el-tag>
        </el-tooltip>
      </div>

      <el-card shadow="hover">
        <PredictChart
          :region-name="prediction.region_name"
          :history="history"
          :predictions="prediction.predictions"
        />
      </el-card>

      <el-card shadow="hover" class="table-card">
        <el-table :data="prediction.predictions" stripe>
          <el-table-column prop="target_month" label="预测月份" />
          <el-table-column prop="predicted_price" label="预测均价 (元/㎡)" />
          <el-table-column label="置信区间 (元/㎡)">
            <template #default="{ row }">
              {{ row.confidence_lower ?? '-' }} ~ {{ row.confidence_upper ?? '-' }}
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <el-empty v-else-if="errorMessage && !loading" :description="errorMessage">
      <RouterLink to="/rank">
        <el-button type="primary">返回排行榜</el-button>
      </RouterLink>
    </el-empty>
  </div>
</template>

<style scoped>
.predict-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
}

.src-alert {
  margin-bottom: 16px;
}

.meta-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

h2 {
  margin: 0;
  color: #303133;
  font-size: 20px;
}

.table-card {
  margin-top: 20px;
}
</style>
