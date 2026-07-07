import type { UserListResponse, UserAdmin } from '@/types'
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
