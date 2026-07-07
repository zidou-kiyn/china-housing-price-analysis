import type { TokenResponse, User } from '@/types'
import api from './index'

export function register(payload: { username: string; email: string; password: string }): Promise<User> {
  return api.post('/auth/register', payload)
}

export function login(payload: { username: string; password: string }): Promise<TokenResponse> {
  return api.post('/auth/login', payload)
}

export function fetchMe(): Promise<User> {
  return api.get('/auth/me')
}
