<script setup lang="ts">
import {
  fetchCityCoverage,
  fetchJob,
  fetchJobs,
  fetchProxySetting,
  refreshCities,
  saveProxySetting,
  submitCollect,
  testProxy,
} from '@/api/admin'
import { usePolling } from '@/composables/usePolling'
import type { AdminJob, CityCoverage, ProxyTestResult } from '@/types'
import { ElMessage } from 'element-plus'
import { computed, nextTick, onMounted, ref, watch } from 'vue'

// ---- 城市数据 ----
const allCities = ref<CityCoverage[]>([])
const loading = ref(false)
const searchKeyword = ref('')
const tableRef = ref<any>(null)

interface ProvinceRow {
  id: string
  name: string
  cityCount: number
  isProvince: true
  children: CityRow[]
}

interface CityRow {
  id: string
  name: string
  code: string
  province: string | null
  districtCount: number
  latestMonth: string | null
  isProvince?: false
}

type TreeRow = ProvinceRow | CityRow

async function loadCities() {
  loading.value = true
  try {
    const resp = await fetchCityCoverage()
    allCities.value = resp.items
  } finally {
    loading.value = false
  }
}

const treeData = computed<ProvinceRow[]>(() => {
  const grouped = new Map<string, CityRow[]>()
  for (const city of allCities.value) {
    const p = city.province || '未知'
    if (!grouped.has(p)) grouped.set(p, [])
    grouped.get(p)!.push({
      id: `city:${city.code}`,
      name: city.name,
      code: city.code,
      province: city.province,
      districtCount: city.district_count,
      latestMonth: city.latest_month,
    })
  }
  return Array.from(grouped, ([province, cities]) => ({
    id: `province:${province}`,
    name: province,
    cityCount: cities.length,
    isProvince: true as const,
    children: cities,
  }))
})

const filteredTreeData = computed<ProvinceRow[]>(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return treeData.value
  return treeData.value
    .map((province) => {
      if (province.name.toLowerCase().includes(kw)) return province
      const filtered = province.children.filter(
        (c) => c.name.toLowerCase().includes(kw) || c.code.toLowerCase().includes(kw),
      )
      if (!filtered.length) return null
      return { ...province, children: filtered, cityCount: filtered.length }
    })
    .filter(Boolean) as ProvinceRow[]
})

// 搜索时自动展开匹配的省份
watch(searchKeyword, async () => {
  await nextTick()
  if (!tableRef.value || !searchKeyword.value.trim()) return
  const kw = searchKeyword.value.trim().toLowerCase()
  for (const province of filteredTreeData.value) {
    const hasCityMatch = province.children.some(
      (c) => c.name.toLowerCase().includes(kw) || c.code.toLowerCase().includes(kw),
    )
    if (hasCityMatch) {
      tableRef.value.toggleRowExpansion(province, true)
    }
  }
})

// ---- 选择逻辑 ----
const selectedCities = ref<CityRow[]>([])

function onSelect(selection: TreeRow[], row: TreeRow) {
  if ('isProvince' in row && row.isProvince) {
    const province = row as ProvinceRow
    const isSelected = selection.some((s) => s.id === province.id)
    for (const child of province.children) {
      tableRef.value?.toggleRowSelection(child, isSelected)
    }
  }
  updateSelectedCities()
}

function onSelectAll(selection: TreeRow[]) {
  // el-table select-all only toggles top-level rows; we need to also toggle children
  const allSelected = selection.length > 0
  for (const province of filteredTreeData.value) {
    for (const child of province.children) {
      tableRef.value?.toggleRowSelection(child, allSelected)
    }
  }
  updateSelectedCities()
}

function updateSelectedCities() {
  if (!tableRef.value) return
  const selected = tableRef.value.getSelectionRows() as TreeRow[]
  selectedCities.value = selected.filter(
    (r): r is CityRow => !('isProvince' in r && r.isProvince),
  )
}

function onInvertSelection() {
  for (const province of filteredTreeData.value) {
    for (const child of province.children) {
      const isSelected = selectedCities.value.some((s) => s.id === child.id)
      tableRef.value?.toggleRowSelection(child, !isSelected)
    }
  }
  updateSelectedCities()
}

const selectedCodes = computed(() => selectedCities.value.map((c) => c.code))

// ---- 任务区 ----
const activeJobs = ref<AdminJob[]>([])
const historyJobs = ref<AdminJob[]>([])
const historyTotal = ref(0)
const historyPage = ref(1)
const historyPageSize = 10

const hasActiveJob = computed(() => activeJobs.value.length > 0)
const { sync: syncPolling } = usePolling(loadJobs)

async function loadJobs() {
  const resp = await fetchJobs(undefined, historyPage.value, historyPageSize)
  historyJobs.value = resp.items
  historyTotal.value = resp.total
  const running = resp.items.filter((j) => j.status === 'pending' || j.status === 'running')
  const finishedNow = activeJobs.value.some((a) => !running.some((r) => r.id === a.id))
  activeJobs.value = running
  if (finishedNow) {
    await loadCities()
  }
  syncPolling(hasActiveJob.value)
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

async function onCollectSelected() {
  if (!selectedCodes.value.length) return
  try {
    const job = await submitCollect({ city_codes: selectedCodes.value })
    ElMessage.success(`采集任务 #${job.id} 已提交（${job.progress_total} 个城市）`)
    await loadJobs()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '采集任务提交失败')
  }
}

// ---- 采集代理设置 ----
const proxyEnabled = ref(false)
const proxyUrl = ref('')
const proxyMasked = ref<string | null>(null)
const proxyHasUrl = ref(false)
const proxySaving = ref(false)
const proxyTesting = ref(false)
const proxyTestResult = ref<ProxyTestResult | null>(null)

async function loadProxy() {
  const s = await fetchProxySetting()
  proxyEnabled.value = s.enabled
  proxyMasked.value = s.url_masked
  proxyHasUrl.value = s.has_url
}

async function onSaveProxy() {
  proxySaving.value = true
  try {
    const s = await saveProxySetting({
      enabled: proxyEnabled.value,
      ...(proxyUrl.value.trim() ? { url: proxyUrl.value.trim() } : {}),
    })
    proxyEnabled.value = s.enabled
    proxyMasked.value = s.url_masked
    proxyHasUrl.value = s.has_url
    proxyUrl.value = ''
    ElMessage.success('代理设置已保存')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '保存失败')
  } finally {
    proxySaving.value = false
  }
}

async function onClearProxy() {
  proxySaving.value = true
  try {
    const s = await saveProxySetting({ enabled: false, url: '' })
    proxyEnabled.value = s.enabled
    proxyMasked.value = s.url_masked
    proxyHasUrl.value = s.has_url
    proxyUrl.value = ''
    proxyTestResult.value = null
    ElMessage.success('代理配置已清除')
  } finally {
    proxySaving.value = false
  }
}

async function onTestProxy() {
  proxyTesting.value = true
  proxyTestResult.value = null
  try {
    proxyTestResult.value = await testProxy(proxyUrl.value.trim() || undefined)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '测试请求失败')
  } finally {
    proxyTesting.value = false
  }
}

// ---- 展示辅助 ----
const KIND_LABELS: Record<string, string> = {
  collect: '数据采集',
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
  await Promise.all([loadCities(), loadJobs(), loadProxy()])
})
watch(historyPage, loadJobs)
</script>

<template>
  <div class="admin-page">
    <h2>数据管理</h2>

    <el-card class="proxy-card">
      <div class="proxy-row">
        <span class="proxy-label">采集代理</span>
        <el-switch v-model="proxyEnabled" active-text="启用" />
        <el-input
          v-model="proxyUrl"
          class="proxy-input"
          show-password
          clearable
          :placeholder="proxyMasked ?? 'http://user:pass@host:port（国内 IP 代理）'"
        />
        <el-button :loading="proxyTesting" @click="onTestProxy">测试连通</el-button>
        <el-button type="primary" :loading="proxySaving" @click="onSaveProxy">保存</el-button>
        <el-button v-if="proxyHasUrl" :loading="proxySaving" @click="onClearProxy">清除</el-button>
      </div>
      <div v-if="proxyTestResult" class="proxy-test-result">
        <el-tag :type="proxyTestResult.ok ? 'success' : 'danger'" size="small">
          {{ proxyTestResult.ok ? '可用' : '不可用' }}
        </el-tag>
        <span v-if="proxyTestResult.status_code">HTTP {{ proxyTestResult.status_code }}</span>
        <span v-if="proxyTestResult.elapsed_ms != null">{{ proxyTestResult.elapsed_ms }}ms</span>
        <span v-if="proxyTestResult.error" class="proxy-error">{{ proxyTestResult.error }}</span>
      </div>
      <div class="proxy-hint">代理仅作用于数据采集（creprice）。</div>
    </el-card>

    <div class="filter-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索省份或城市..."
        clearable
        class="filter-keyword"
      />
      <div class="spacer" />
      <el-button :loading="refreshing" :disabled="hasActiveJob" @click="onRefreshCities">
        刷新城市列表
      </el-button>
      <el-button @click="onInvertSelection">反选</el-button>
      <el-button
        type="primary"
        :disabled="hasActiveJob || !selectedCities.length"
        @click="onCollectSelected"
      >
        采集所选（{{ selectedCities.length }}）
      </el-button>
    </div>

    <el-table
      ref="tableRef"
      v-loading="loading"
      :data="filteredTreeData"
      row-key="id"
      :tree-props="{ children: 'children' }"
      :default-expand-all="false"
      stripe
      @select="onSelect"
      @select-all="onSelectAll"
    >
      <el-table-column type="selection" width="44" />
      <el-table-column label="名称" min-width="180">
        <template #default="{ row }">
          <template v-if="row.isProvince">
            <strong>{{ row.name }}</strong>
            <span class="province-count">（{{ row.cityCount }}）</span>
          </template>
          <template v-else>{{ row.name }}</template>
        </template>
      </el-table-column>
      <el-table-column label="代码" width="90">
        <template #default="{ row }">{{ row.isProvince ? '' : row.code }}</template>
      </el-table-column>
      <el-table-column label="区县数" width="80">
        <template #default="{ row }">{{ row.isProvince ? '' : row.districtCount }}</template>
      </el-table-column>
      <el-table-column label="最新数据月份" width="130">
        <template #default="{ row }">
          <template v-if="!row.isProvince">
            <el-tag v-if="row.latestMonth" type="success" size="small">{{ row.latestMonth }}</el-tag>
            <el-tag v-else type="info" size="small">无数据</el-tag>
          </template>
        </template>
      </el-table-column>
    </el-table>

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
      <el-table-column label="类型" width="130">
        <template #default="{ row }">
          {{ KIND_LABELS[row.kind] ?? row.kind }}
        </template>
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

.proxy-card {
  margin-bottom: 16px;
}

.proxy-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.proxy-label {
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
}

.proxy-input {
  flex: 1;
}

.proxy-test-result {
  margin-top: 10px;
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 13px;
  color: #606266;
}

.proxy-error {
  color: #f56c6c;
}

.proxy-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: center;
}

.filter-keyword {
  width: 280px;
}

.spacer {
  flex: 1;
}

.province-count {
  color: #909399;
  font-weight: normal;
  margin-left: 4px;
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
