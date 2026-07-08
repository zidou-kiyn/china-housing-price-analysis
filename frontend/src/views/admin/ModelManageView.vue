<script setup lang="ts">
import { fetchJobs } from '@/api/admin'
import {
  cleanupModelVersions,
  deleteModelVersion,
  fetchModelVersions,
  setActiveModel,
  submitTrain,
} from '@/api/predict'
import { usePolling } from '@/composables/usePolling'
import type { AdminJob, ModelVersion } from '@/types'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

// ---- 模型版本表 ----
const versions = ref<ModelVersion[]>([])
const loading = ref(false)

async function loadVersions() {
  loading.value = true
  try {
    versions.value = await fetchModelVersions()
  } finally {
    loading.value = false
  }
}

async function onSetActive(m: ModelVersion) {
  try {
    await ElMessageBox.confirm(
      `确定将活跃模型切换为 ${m.model_name} ${m.version} 吗？预测接口将立即使用该模型。`,
      '切换活跃模型',
      { type: 'warning', confirmButtonText: '切换', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    versions.value = await setActiveModel(m.model_name, m.version)
    ElMessage.success(`已切换活跃模型为 ${m.model_name} ${m.version}`)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '切换失败')
  }
}

async function onDelete(m: ModelVersion) {
  try {
    await ElMessageBox.confirm(
      `确定删除 ${m.model_name} ${m.version} 吗？模型文件与指标将一并删除，不可恢复。`,
      '删除模型版本',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await deleteModelVersion(m.model_name, m.version)
    ElMessage.success(`已删除 ${m.model_name} ${m.version}`)
    await loadVersions()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '删除失败')
  }
}

// ---- 批量清理旧版本 ----
const CLEANUP_KEEP_LAST = 3

// 与后端 cleanup 同策略的前置估算：每模型保留最近 N 个版本 + 活跃版本（列表已按版本序）
const cleanupCandidates = computed(() => {
  const byModel = new Map<string, ModelVersion[]>()
  for (const v of versions.value) {
    const list = byModel.get(v.model_name) ?? []
    list.push(v)
    byModel.set(v.model_name, list)
  }
  const doomed: ModelVersion[] = []
  for (const list of byModel.values()) {
    const keep = new Set(list.slice(-CLEANUP_KEEP_LAST).map((v) => v.version))
    for (const v of list) {
      if (!keep.has(v.version) && !v.is_active) doomed.push(v)
    }
  }
  return doomed
})

async function onCleanup() {
  const count = cleanupCandidates.value.length
  try {
    await ElMessageBox.confirm(
      `将删除 ${count} 个旧版本（每个模型保留最近 ${CLEANUP_KEEP_LAST} 个版本与活跃版本），不可恢复。是否继续？`,
      '清理旧版本',
      { type: 'warning', confirmButtonText: '清理', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    const result = await cleanupModelVersions(CLEANUP_KEEP_LAST)
    ElMessage.success(
      result.deleted.length ? `已清理 ${result.deleted.length} 个旧版本` : '没有可清理的旧版本',
    )
    await loadVersions()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '清理失败')
  }
}

// ---- 训练表单 ----
const algorithm = ref<'random_forest' | 'xgboost'>('random_forest')

// ---- 训练任务轮询 ----
const activeJob = ref<AdminJob | null>(null)
const training = computed(
  () => !!activeJob.value && ['pending', 'running'].includes(activeJob.value.status),
)

const { sync: syncPolling } = usePolling(loadTrainJob)

async function loadTrainJob() {
  const resp = await fetchJobs('train', 1, 1)
  const latest = resp.items[0] ?? null
  const wasTraining = training.value
  activeJob.value = latest
  if (wasTraining && !training.value) {
    ElMessage.success('训练完成，版本列表已刷新')
    await loadVersions()
  }
  syncPolling(training.value)
}

async function onSubmitTrain() {
  try {
    const job = await submitTrain({
      model_name: algorithm.value,
    })
    ElMessage.success(`训练任务 #${job.id} 已提交`)
    activeJob.value = job
    syncPolling(true)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '训练提交失败')
  }
}

// ---- 展示辅助 ----
function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN')
}

function mape(m: ModelVersion): string {
  const v = m.metrics?.mape
  return v == null ? '-' : `${v}%`
}

onMounted(async () => {
  await Promise.all([
    loadVersions(),
    loadTrainJob(),
  ])
})
</script>

<template>
  <div class="admin-page">
    <div class="page-header">
      <h2>模型管理</h2>
      <el-button
        size="small"
        :disabled="loading || cleanupCandidates.length === 0"
        @click="onCleanup"
      >
        清理旧版本
      </el-button>
    </div>

    <el-table v-loading="loading" :data="versions" stripe>
      <el-table-column prop="model_name" label="算法" min-width="120" />
      <el-table-column prop="version" label="版本" width="80" />
      <el-table-column label="训练时间" min-width="160">
        <template #default="{ row }">{{ formatTime(row.trained_at) }}</template>
      </el-table-column>
      <el-table-column label="MAPE" width="90">
        <template #default="{ row }">{{ mape(row) }}</template>
      </el-table-column>
      <el-table-column prop="training_samples" label="样本数" width="80" />
      <el-table-column label="基线对比" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.beats_baseline === true" type="success" size="small">
            优于基线
          </el-tag>
          <el-tag v-else-if="row.beats_baseline === false" type="danger" size="small">
            未及基线
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <div class="status-tags">
            <el-tag v-if="row.is_active" type="success" size="small">活跃</el-tag>
            <el-tag v-if="row.is_best" type="warning" size="small">最佳</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="170" fixed="right">
        <template #default="{ row }">
          <el-button size="small" :disabled="row.is_active" @click="onSetActive(row)">
            设为活跃
          </el-button>
          <el-button size="small" type="danger" :disabled="row.is_active" @click="onDelete(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <h3>发起训练</h3>
    <el-card class="train-card">
      <div class="train-form">
        <el-select v-model="algorithm" class="algo-select">
          <el-option label="random_forest" value="random_forest" />
          <el-option label="xgboost" value="xgboost" />
        </el-select>
        <el-button type="primary" :disabled="training" @click="onSubmitTrain">
          开始训练
        </el-button>
      </div>

      <div v-if="activeJob && training" class="train-progress">
        <el-tag type="warning" size="small">
          训练任务 #{{ activeJob.id }} {{ activeJob.status === 'pending' ? '等待中' : '训练中' }}…
        </el-tag>
        <el-progress :percentage="100" :indeterminate="true" :show-text="false" :duration="2" />
      </div>
      <div v-else-if="activeJob" class="train-progress">
        <el-tag :type="activeJob.status === 'success' ? 'success' : 'danger'" size="small">
          上次训练任务 #{{ activeJob.id }}：{{ activeJob.status === 'success' ? '成功' : '失败' }}
        </el-tag>
        <span v-if="activeJob.error" class="train-error">{{ activeJob.error }}</span>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.admin-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

h2 {
  margin: 0;
  color: #303133;
}

.status-tags {
  display: flex;
  gap: 4px;
}

h3 {
  margin: 24px 0 12px;
  color: #303133;
}

.train-form {
  display: flex;
  gap: 12px;
  align-items: center;
}

.algo-select {
  width: 170px;
}

.city-select {
  flex: 1;
}

.train-progress {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.train-error {
  color: #f56c6c;
  font-size: 13px;
}
</style>
