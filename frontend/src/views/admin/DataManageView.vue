<script setup lang="ts">
import {
  fetchCityCoverage,
  fetchCollectSchedule,
  fetchCollectSources,
  fetchDataQualityReport,
  fetchJob,
  fetchJobs,
  fetchProxySetting,
  importAnnual,
  importIndex,
  refreshCities,
  saveCollectSchedule,
  saveCollectSource,
  saveProxySetting,
  submitCollect,
  submitGeoFetch,
  testProxy,
} from '@/api/admin'
import { usePolling } from '@/composables/usePolling'
import type {
  AdminJob,
  AnnualImportResult,
  CityCoverage,
  CollectScheduleState,
  CollectSource,
  DataQualityReport,
  DirectionConsistencySection,
  IndexImportStats,
  ProxyTestResult,
} from '@/types'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

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

const hasActiveJob = computed(() => activeJobs.value.length > 0)
const { sync: syncPolling } = usePolling(loadJobs)

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

// ---- 全国年度数据导入 ----
const annualImporting = ref(false)
const annualResult = ref<AnnualImportResult | null>(null)

async function onImportAnnual() {
  annualImporting.value = true
  try {
    annualResult.value = await importAnnual('58')
    ElMessage.success(
      `年度数据导入完成：${annualResult.value.matched} 城 / ${annualResult.value.snapshots} 条快照`,
    )
    await loadCities()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '年度数据导入失败')
  } finally {
    annualImporting.value = false
  }
}

// ---- NBS 70 城指数导入（异步 job，完成后展示统计） ----
const indexImporting = ref(false)
const indexResult = ref<IndexImportStats | null>(null)

async function waitJobFinal(jobId: number, timeoutMs = 300_000): Promise<AdminJob> {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const job = await fetchJob(jobId)
    if (job.status === 'success' || job.status === 'failed') return job
    if (Date.now() > deadline) throw new Error(`任务 #${jobId} 等待超时`)
    await new Promise((resolve) => setTimeout(resolve, 2000))
  }
}

async function onImportIndex() {
  indexImporting.value = true
  indexResult.value = null
  try {
    const job = await importIndex()
    ElMessage.success(`NBS 指数导入任务 #${job.id} 已提交`)
    await loadJobs()
    const final = await waitJobFinal(job.id)
    if (final.status === 'success' && final.result?.length) {
      indexResult.value = final.result[0] as unknown as IndexImportStats
      ElMessage.success(
        `指数导入完成：${indexResult.value.matched} 城 / ${indexResult.value.rows} 行指数`,
      )
    } else {
      ElMessage.error(final.error ?? 'NBS 指数导入失败')
    }
    await loadJobs()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? error.message ?? 'NBS 指数导入失败')
  } finally {
    indexImporting.value = false
  }
}

// ---- 数据质量审计（要点卡：离群数 / 方向一致率 / 模型新鲜度） ----
const quality = ref<DataQualityReport | null>(null)
const qualityLoading = ref(false)

async function loadQuality() {
  qualityLoading.value = true
  try {
    quality.value = await fetchDataQualityReport()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '数据质量报告获取失败')
  } finally {
    qualityLoading.value = false
  }
}

function agreementText(section: DirectionConsistencySection): string {
  if (section.status === 'no index data') return '未导入指数'
  if (section.status !== 'ok' || section.agreement_rate == null) return '无重叠数据'
  return `${section.agreement_rate}%（${section.matches}/${section.compared}）`
}

const FRESHNESS_LABELS: Record<string, string> = {
  fresh: '模型新鲜',
  stale: '建议重训',
  unknown: '新鲜度未知',
}

const freshnessTagType = computed(() => {
  const status = quality.value?.model_freshness.status
  if (status === 'fresh') return 'success'
  if (status === 'stale') return 'warning'
  return 'info'
})

// ---- 采集代理设置 ----
const proxyEnabled = ref(false)
const proxyUrl = ref('') // 仅承载新输入；空 = 未改动
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
      // 输入框为空 = 不改动已存 URL（后端 url 缺省语义）
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

// ---- 定时采集设置 ----
const scheduleEnabled = ref(false)
const scheduleTime = ref('03:30')
const scheduleBatch = ref(5)
const scheduleState = ref<CollectScheduleState | null>(null)
const scheduleSaving = ref(false)

async function loadSchedule() {
  const s = await fetchCollectSchedule()
  scheduleEnabled.value = s.enabled
  scheduleTime.value = s.time
  scheduleBatch.value = s.batch
  scheduleState.value = s.state
}

async function onSaveSchedule() {
  scheduleSaving.value = true
  try {
    const s = await saveCollectSchedule({
      enabled: scheduleEnabled.value,
      time: scheduleTime.value,
      batch: scheduleBatch.value,
    })
    scheduleEnabled.value = s.enabled
    scheduleTime.value = s.time
    scheduleBatch.value = s.batch
    scheduleState.value = s.state
    ElMessage.success(
      s.enabled ? `定时采集已开启（每日 ${s.time}，每批 ${s.batch} 城）` : '定时采集已关闭',
    )
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '保存失败')
  } finally {
    scheduleSaving.value = false
  }
}

const scheduleLastRunText = computed(() => {
  const st = scheduleState.value
  if (!st?.last_run_at) return null
  const parts = [`上次运行 ${formatTime(st.last_run_at)}`]
  if (st.last_job_id != null) parts.push(`任务 #${st.last_job_id}`)
  const r = st.last_result
  if (r) {
    if (r.note) {
      parts.push(r.note)
    } else {
      parts.push(`提交 ${r.submitted} 城`)
      if (r.ok != null) parts.push(`成功 ${r.ok} / 失败 ${r.failed ?? 0}`)
    }
  }
  return parts.join(' · ')
})

// ---- 数据源切换 ----
const sources = ref<CollectSource[]>([])
const currentSource = ref('')
const sourceSaving = ref(false)

const CAPABILITY_LABELS: Record<string, string> = {
  cities: '城市',
  districts: '区县',
  price_timeline: '均价走势',
  price_distribution: '价格分布',
}

const PRICE_UNIT_LABELS: Record<string, string> = {
  cny_per_sqm: '元/㎡',
  index: '价格指数',
}

const currentSourceMeta = computed(() =>
  sources.value.find((s) => s.name === currentSource.value),
)

async function loadSources() {
  const resp = await fetchCollectSources()
  sources.value = resp.items
  currentSource.value = resp.current
}

async function onChangeSource(name: string) {
  sourceSaving.value = true
  try {
    const resp = await saveCollectSource(name)
    sources.value = resp.items
    currentSource.value = resp.current
    ElMessage.success(`当前数据源已切换为 ${name}`)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail ?? '切换失败')
    await loadSources() // 回滚到后端真实值
  } finally {
    sourceSaving.value = false
  }
}

// ---- 展示辅助 ----
const KIND_LABELS: Record<string, string> = {
  collect: '数据采集',
  geo_fetch: '地图爬取',
  train: '模型训练',
  import_index: 'NBS 指数导入',
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
  if (job.kind === 'import_index') {
    const r = result[0] as unknown as IndexImportStats
    return `${r.matched} 城 / ${r.rows} 行指数（跳过 ${r.skipped?.length ?? 0} 城）`
  }
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
  // 质量报告即时计算耗时秒级，独立加载不阻塞其余区块
  loadQuality()
  await Promise.all([loadCities(), loadJobs(), loadProxy(), loadSources(), loadSchedule()])
})
watch([page, pageSize], loadCities)
watch(historyPage, loadJobs)
</script>

<template>
  <div class="admin-page">
    <h2>数据管理</h2>

    <el-card class="source-card">
      <div class="source-row">
        <span class="source-label">采集数据源</span>
        <el-select
          v-model="currentSource"
          class="source-select"
          :loading="sourceSaving"
          :disabled="hasActiveJob"
          @change="onChangeSource"
        >
          <el-option
            v-for="s in sources"
            :key="s.name"
            :label="s.name"
            :value="s.name"
          />
        </el-select>
        <div v-if="currentSourceMeta" class="source-caps">
          <el-tag size="small" type="info">
            {{ PRICE_UNIT_LABELS[currentSourceMeta.price_unit] ?? currentSourceMeta.price_unit }}
          </el-tag>
          <el-tag
            v-for="cap in currentSourceMeta.capabilities"
            :key="cap"
            size="small"
            type="success"
          >
            {{ CAPABILITY_LABELS[cap] ?? cap }}
          </el-tag>
        </div>
      </div>
      <div class="source-hint">
        采集与「刷新城市列表」默认使用此数据源；进行中任务时不可切换。各源能力不同，编排会按能力自适应。
      </div>
    </el-card>

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
      <div class="proxy-hint">
        代理仅作用于数据采集（creprice）；采集源屏蔽境外 IP，请使用国内出口代理。地图（DataV）始终直连。
      </div>
    </el-card>

    <el-card class="schedule-card">
      <div class="schedule-row">
        <span class="schedule-label">定时采集</span>
        <el-switch v-model="scheduleEnabled" active-text="启用" />
        <span class="schedule-field-label">每日</span>
        <el-time-select
          v-model="scheduleTime"
          class="schedule-time"
          start="00:00"
          step="00:30"
          end="23:30"
          :clearable="false"
        />
        <span class="schedule-field-label">每批</span>
        <el-input-number v-model="scheduleBatch" :min="1" :max="20" class="schedule-batch" />
        <span class="schedule-field-label">城</span>
        <el-button type="primary" :loading="scheduleSaving" @click="onSaveSchedule">
          保存
        </el-button>
      </div>
      <div v-if="scheduleLastRunText || scheduleState?.last_error" class="schedule-state">
        <span v-if="scheduleLastRunText">{{ scheduleLastRunText }}</span>
        <el-tag
          v-if="scheduleState?.last_result?.circuit_broken"
          type="warning"
          size="small"
        >
          限流熔断，剩余城市顺延下批
        </el-tag>
        <span v-if="scheduleState?.last_error" class="schedule-error">
          {{ scheduleState.last_error }}
        </span>
      </div>
      <div class="schedule-hint">
        每日到点自动采集一批 creprice 城市：缺当月数据的续采优先（最旧在前），余量按城市顺序轮换扩展新城市。
        时刻按后端服务器时区（当前容器为 UTC，北京时间 = UTC+8）。城市间随机间隔 10~20s，连续 3 城失败自动熔断，避免触发源站限流。
        保存后约 1 分钟内生效，无需重启服务。
      </div>
    </el-card>

    <el-card class="quality-card">
      <div class="quality-row">
        <span class="quality-label">数据质量</span>
        <template v-if="quality">
          <el-tag
            :type="quality.overlap_ratio.outliers_total ? 'warning' : 'success'"
            size="small"
          >
            跨源离群 {{ quality.overlap_ratio.outliers_total }} 对
            <template v-if="quality.overlap_ratio.pairs">
              / 重叠 {{ quality.overlap_ratio.pairs }}
            </template>
          </el-tag>
          <span class="quality-item">
            creprice×指数环比一致 {{ agreementText(quality.creprice_vs_index) }}
          </span>
          <span class="quality-item">
            年度×指数同比一致 {{ agreementText(quality.annual_vs_index) }}
          </span>
          <el-tag :type="freshnessTagType" size="small">
            {{ FRESHNESS_LABELS[quality.model_freshness.status] ?? quality.model_freshness.status }}
            <template v-if="quality.model_freshness.model_version">
              （{{ quality.model_freshness.model_name }}
              {{ quality.model_freshness.model_version }}）
            </template>
          </el-tag>
        </template>
        <span v-else-if="qualityLoading" class="quality-item">报告计算中…</span>
        <div class="spacer" />
        <el-button size="small" :loading="qualityLoading" @click="loadQuality">刷新</el-button>
      </div>
      <div class="quality-hint">
        跨源审计要点：多源重叠月价格比值离群（域 [0.5, 2.0]）、creprice 环比 / 58 年度同比与
        NBS 指数方向一致率（平不计入分母）、活跃模型训练数据指纹 vs 当前库。明细见
        /admin/data-quality/report。
      </div>
    </el-card>

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
      <el-button :loading="annualImporting" :disabled="hasActiveJob" @click="onImportAnnual">
        导入全国年度数据
      </el-button>
      <el-button :loading="indexImporting" :disabled="hasActiveJob" @click="onImportIndex">
        导入 NBS 70 城指数
      </el-button>
      <el-button :loading="refreshing" :disabled="hasActiveJob" @click="onRefreshCities">
        刷新城市列表
      </el-button>
    </div>

    <el-alert
      v-if="annualResult"
      type="success"
      :closable="true"
      class="annual-alert"
      @close="annualResult = null"
    >
      <template #title>
        年度挂牌数据（{{ annualResult.source }}）：匹配 {{ annualResult.matched }} 城、写入
        {{ annualResult.snapshots }} 条年度快照；{{ annualResult.skipped_count }} 城名未匹配跳过
        <template v-if="annualResult.skipped_count">
          （{{ annualResult.skipped_cities.slice(0, 8).join('、')
          }}{{ annualResult.skipped_count > 8 ? ' 等' : '' }}）
        </template>
      </template>
    </el-alert>

    <el-alert
      v-if="indexResult"
      type="success"
      :closable="true"
      class="annual-alert"
      @close="indexResult = null"
    >
      <template #title>
        NBS 70 城月度指数（{{ indexResult.source }}）：匹配 {{ indexResult.matched }} 城、写入
        {{ indexResult.rows }} 行指数
        <template v-if="indexResult.months_range">
          （{{ indexResult.months_range[0] }} ~ {{ indexResult.months_range[1] }}）
        </template>
        ；{{ indexResult.skipped.length }} 城名未匹配跳过
        <template v-if="indexResult.skipped.length">
          （{{ indexResult.skipped.slice(0, 8).join('、')
          }}{{ indexResult.skipped.length > 8 ? ' 等' : '' }}）
        </template>
      </template>
    </el-alert>

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
      <el-table-column label="类型" width="130">
        <template #default="{ row }">
          {{ KIND_LABELS[row.kind] ?? row.kind }}
          <el-tag v-if="row.payload?.trigger === 'schedule'" size="small" type="info">
            定时
          </el-tag>
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

.source-card {
  margin-bottom: 16px;
}

.source-row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.source-label {
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
}

.source-select {
  width: 200px;
}

.source-caps {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}

.source-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
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

.schedule-card {
  margin-bottom: 16px;
}

.schedule-row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.schedule-label {
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
}

.schedule-field-label {
  color: #606266;
  font-size: 13px;
  white-space: nowrap;
}

.schedule-time {
  width: 120px;
}

.schedule-batch {
  width: 120px;
}

.schedule-state {
  margin-top: 10px;
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 13px;
  color: #606266;
}

.schedule-error {
  color: #f56c6c;
}

.schedule-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.quality-card {
  margin-bottom: 16px;
}

.quality-row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.quality-label {
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
}

.quality-item {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
}

.quality-hint {
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

.annual-alert {
  margin-bottom: 16px;
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
