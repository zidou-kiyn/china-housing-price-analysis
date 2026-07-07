<script setup lang="ts">
import { fetchPrediction } from '@/api/predict'
import { fetchTrend } from '@/api/price'
import PredictChart from '@/components/PredictChart.vue'
import type { PredictionResponse, RegionType, TrendPoint } from '@/types'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const history = ref<TrendPoint[]>([])
const prediction = ref<PredictionResponse | null>(null)
const errorMessage = ref('')
const loading = ref(false)

const regionType = computed(() => route.params.regionType as RegionType)
const regionId = computed(() => Number(route.params.id))

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
    <template v-if="prediction">
      <div class="meta-bar">
        <h2>{{ prediction.region_name }} · 未来 {{ prediction.predictions.length }} 个月预测</h2>
        <el-tag size="small" type="info">
          模型：{{ prediction.model_name }} {{ prediction.model_version }}
        </el-tag>
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
