import type { UserListResponse, UserAdmin } from '@/types'
import api from './index'

export function fetchUsers(page = 1, pageSize = 20): Promise<UserListResponse> {
  return api.get('/admin/users', { params: { page, page_size: pageSize } })
}

export function updateUserRole(userId: number, role: string): Promise<UserAdmin> {
  return api.patch(`/admin/users/${userId}/role`, { role })
}
