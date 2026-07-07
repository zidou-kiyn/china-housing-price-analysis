<script setup lang="ts">
import {
  fetchCityCoverage,
  fetchJobs,
  refreshCities,
  submitCollect,
  submitGeoFetch,
} from '@/api/admin'
import type { AdminJob, CityCoverage } from '@/types'
import { ElMessage } from 'element-plus'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

// ---- 城市覆盖表 ----
const cities = ref<CityCoverage[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const keyword = ref('')
const province = ref('')
const selection = ref<CityCoverage[]>([])

async function loadCities() {
  loading.value = true
  try {
    const resp = await fetchCityCoverage(page.value, pageSize.value, {
      keyword: keyword.value.trim(),
      province: province.value.trim(),
    })
    cities.value = resp.items
    total.value = resp.total
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  if (page.value === 1) {
    loadCities()
  } else {
    page.value = 1
  }
}

// ---- 任务区 ----
const activeJobs = ref<AdminJob[]>([])
const historyJobs = ref<AdminJob[]>([])
const historyTotal = ref(0)
const historyPage = ref(1)
const historyPageSize = 10
let pollTimer: number | null = null

const hasActiveJob = computed(() => activeJobs.value.length > 0)

async function loadJobs() {
  const resp = await fetchJobs(undefined, historyPage.value, historyPageSize)
  historyJobs.value = resp.items
  historyTotal.value = resp.total
  const running = resp.items.filter((j) => j.status === 'pending' || j.status === 'running')
  // 第一页未覆盖的进行中任务不影响互斥展示（后端才是唯一约束）
  const finishedNow = activeJobs.value.some(
    (a) => !running.some((r) => r.id === a.id),
  )
  activeJobs.value = running
  if (finishedNow) {
    await loadCities() // 任务完成后刷新覆盖状态
  }
  syncPolling()
}

function syncPolling() {
  if (hasActiveJob.value && pollTimer === null) {
    pollTimer = window.setInterval(loadJobs, 3000)
  } else if (!hasActiveJob.value && pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

// ---- 操作 ----
const refreshing = ref(false)

async function onRefreshCities() {
  refreshing.value = true
  try {
    const resp = await refreshCities()
    ElMessage.success(`城市列表已刷新，共 ${resp.total} 个城市`)
    await loadCities()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '刷新失败')
  } finally {
    refreshing.value = false
  }
}

async function submitJob(fn: () => Promise<AdminJob>, label: string) {
  try {
    const job = await fn()
    ElMessage.success(`${label}任务 #${job.id} 已提交（${job.progress_total} 个城市）`)
    await loadJobs()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? `${label}任务提交失败`)
  }
}

const selectedCodes = computed(() => selection.value.map((c) => c.code))

function onCollectSelected() {
  if (!selectedCodes.value.length) return
  submitJob(() => submitCollect({ city_codes: selectedCodes.value }), '采集')
}

function onGeoSelected() {
  if (!selectedCodes.value.length) return
  submitJob(() => submitGeoFetch({ city_codes: selectedCodes.value }), '地图爬取')
}

function onCollectAllMissing() {
  submitJob(() => submitCollect({ all_missing: true }), '采集缺数据城市')
}

function onGeoAllMissing() {
  submitJob(() => submitGeoFetch({ all_missing: true }), '补齐缺图')
}

// ---- 展示辅助 ----
const KIND_LABELS: Record<string, string> = {
  collect: '数据采集',
  geo_fetch: '地图爬取',
  train: '模型训练',
}

const STATUS_LABELS: Record<string, string> = {
  pending: '等待中',
  running: '进行中',
  success: '成功',
  failed: '失败',
}

function statusTagType(status: string): 'success' | 'danger' | 'warning' | 'info' {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}

function jobPercent(job: AdminJob): number {
  if (!job.progress_total) return 0
  return Math.round((job.progress_done / job.progress_total) * 100)
}

function jobDuration(job: AdminJob): string {
  if (!job.started_at || !job.finished_at) return '-'
  const secs = (new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000
  return secs >= 60 ? `${Math.round(secs / 60)} 分钟` : `${Math.round(secs)} 秒`
}

function jobSummary(job: AdminJob): string {
  const result = job.result ?? []
  const failed = result.filter((r) => !r.ok)
  if (job.error) return job.error
  if (!result.length) return '-'
  if (!failed.length) return `${result.length} 个城市全部成功`
  return `${result.length - failed.length} 成功 / ${failed.length} 失败（${failed
    .slice(0, 5)
    .map((r) => r.city)
    .join('、')}）`
}

function formatTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString('zh-CN') : '-'
}

onMounted(async () => {
  await Promise.all([loadCities(), loadJobs()])
})
onUnmounted(() => {
  if (pollTimer !== null) window.clearInterval(pollTimer)
})
watch([page, pageSize], loadCities)
watch(historyPage, loadJobs)
</script>

<template>
  <div class="admin-page">
    <h2>数据管理</h2>

    <div class="filter-bar">
      <el-input
        v-model="keyword"
        placeholder="搜索城市名/代码"
        clearable
        class="filter-keyword"
        @keyup.enter="onFilterChange"
        @clear="onFilterChange"
      >
        <template #append>
          <el-button @click="onFilterChange">搜索</el-button>
        </template>
      </el-input>
      <el-input
        v-model="province"
        placeholder="省份"
        clearable
        class="filter-province"
        @keyup.enter="onFilterChange"
        @clear="onFilterChange"
      />
      <div class="spacer" />
      <el-button :loading="refreshing" :disabled="hasActiveJob" @click="onRefreshCities">
        刷新城市列表
      </el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="cities"
      stripe
      @selection-change="(rows: CityCoverage[]) => (selection = rows)"
    >
      <el-table-column type="selection" width="44" />
      <el-table-column prop="name" label="城市" min-width="100" />
      <el-table-column prop="code" label="代码" width="90" />
      <el-table-column prop="province" label="省份" min-width="90">
        <template #default="{ row }">{{ row.province ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="district_count" label="区县数" width="80" />
      <el-table-column label="最新数据月份" width="120">
        <template #default="{ row }">
          <el-tag v-if="row.latest_month" type="success" size="small">{{ row.latest_month }}</el-tag>
          <el-tag v-else type="info" size="small">无数据</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="地图" width="80">
        <template #default="{ row }">
          <el-tag :type="row.has_geo ? 'success' : 'info'" size="small">
            {{ row.has_geo ? '有' : '无' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <div class="table-footer">
      <div class="batch-actions">
        <el-button
          type="primary"
          :disabled="hasActiveJob || !selection.length"
          @click="onCollectSelected"
        >
          采集所选（{{ selection.length }}）
        </el-button>
        <el-button :disabled="hasActiveJob || !selection.length" @click="onGeoSelected">
          爬取所选地图
        </el-button>
        <el-button :disabled="hasActiveJob" @click="onCollectAllMissing">
          采集全部缺数据城市
        </el-button>
        <el-button :disabled="hasActiveJob" @click="onGeoAllMissing">补齐全部缺图</el-button>
      </div>
      <el-pagination
        v-if="total > pageSize"
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
      />
    </div>

    <h3>进行中任务</h3>
    <template v-if="activeJobs.length">
      <el-card v-for="job in activeJobs" :key="job.id" class="job-card">
        <div class="job-card-head">
          <span>
            #{{ job.id }} {{ KIND_LABELS[job.kind] ?? job.kind }}
            <el-tag :type="statusTagType(job.status)" size="small">
              {{ STATUS_LABELS[job.status] }}
            </el-tag>
          </span>
          <span class="job-progress-text">
            {{ job.progress_done }} / {{ job.progress_total }}
          </span>
        </div>
        <el-progress :percentage="jobPercent(job)" :striped="true" :striped-flow="true" />
      </el-card>
    </template>
    <el-empty v-else description="当前没有进行中的任务" :image-size="60" />

    <h3>历史任务</h3>
    <el-table :data="historyJobs" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column label="类型" width="110">
        <template #default="{ row }">{{ KIND_LABELS[row.kind] ?? row.kind }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ STATUS_LABELS[row.status] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="90">
        <template #default="{ row }">{{ row.progress_done }}/{{ row.progress_total }}</template>
      </el-table-column>
      <el-table-column label="提交时间" min-width="150">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="耗时" width="90">
        <template #default="{ row }">{{ jobDuration(row) }}</template>
      </el-table-column>
      <el-table-column label="结果" min-width="220">
        <template #default="{ row }">{{ jobSummary(row) }}</template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-if="historyTotal > historyPageSize"
      v-model:current-page="historyPage"
      :page-size="historyPageSize"
      :total="historyTotal"
      layout="total, prev, pager, next"
      class="pagination"
    />
  </div>
</template>

<style scoped>
.admin-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 20px;
}

h2 {
  margin: 0 0 16px;
  color: #303133;
}

h3 {
  margin: 24px 0 12px;
  color: #303133;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: center;
}

.filter-keyword {
  width: 260px;
}

.filter-province {
  width: 140px;
}

.spacer {
  flex: 1;
}

.table-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  gap: 12px;
  flex-wrap: wrap;
}

.job-card {
  margin-bottom: 8px;
}

.job-card-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.job-progress-text {
  color: #909399;
  font-size: 13px;
}

.pagination {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
