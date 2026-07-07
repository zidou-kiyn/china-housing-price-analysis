import type {
  AdminJob,
  AdminJobListResponse,
  CityCoverageListResponse,
  UserAdmin,
  UserListResponse,
} from '@/types'
import api from './index'

export interface UserListFilters {
  keyword?: string
  role?: string
  isActive?: boolean
}

export function fetchUsers(
  page = 1,
  pageSize = 20,
  filters: UserListFilters = {},
): Promise<UserListResponse> {
  return api.get('/admin/users', {
    params: {
      page,
      page_size: pageSize,
      keyword: filters.keyword || undefined,
      role: filters.role || undefined,
      is_active: filters.isActive,
    },
  })
}

export function updateUserRole(userId: number, role: string): Promise<UserAdmin> {
  return api.patch(`/admin/users/${userId}/role`, { role })
}

export function updateUserStatus(userId: number, isActive: boolean): Promise<UserAdmin> {
  return api.patch(`/admin/users/${userId}/status`, { is_active: isActive })
}

export function deleteUser(userId: number): Promise<void> {
  return api.delete(`/admin/users/${userId}`)
}

// ---- 数据管理（采集 / 地图 / 任务） ----

export interface CityCoverageFilters {
  keyword?: string
  province?: string
}

export function fetchCityCoverage(
  page = 1,
  pageSize = 20,
  filters: CityCoverageFilters = {},
): Promise<CityCoverageListResponse> {
  return api.get('/admin/collect/cities', {
    params: {
      page,
      page_size: pageSize,
      keyword: filters.keyword || undefined,
      province: filters.province || undefined,
    },
  })
}

export function refreshCities(): Promise<{ total: number }> {
  return api.post('/admin/collect/cities/refresh')
}

export function submitCollect(payload: {
  city_codes?: string[]
  all?: boolean
  all_missing?: boolean
}): Promise<AdminJob> {
  return api.post('/admin/collect', payload)
}

export function submitGeoFetch(payload: {
  city_codes?: string[]
  all_missing?: boolean
}): Promise<AdminJob> {
  return api.post('/admin/geo/fetch', payload)
}

export function fetchJobs(
  kind?: string,
  page = 1,
  pageSize = 20,
): Promise<AdminJobListResponse> {
  return api.get('/admin/jobs', { params: { kind, page, page_size: pageSize } })
}

export function fetchJob(jobId: number): Promise<AdminJob> {
  return api.get(`/admin/jobs/${jobId}`)
}
