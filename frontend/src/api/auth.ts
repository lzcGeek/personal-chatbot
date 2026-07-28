import { api } from './chat'


export interface AuthUser {
  id: string
  username: string
  display_name: string
}

interface AuthResponse {
  user: AuthUser
}

export async function getCurrentUser(): Promise<AuthUser> {
  const response = await api.get<AuthResponse>('/auth/me')
  return response.data.user
}

export async function login(username: string, password: string): Promise<AuthUser> {
  const response = await api.post<AuthResponse>('/auth/login', { username, password })
  return response.data.user
}

export async function register(username: string, password: string): Promise<AuthUser> {
  const response = await api.post<AuthResponse>('/auth/register', { username, password })
  return response.data.user
}

export async function logout(): Promise<void> {
  await api.post('/auth/logout')
}
