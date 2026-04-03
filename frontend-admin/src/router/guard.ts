import type { NavigationGuardNext, RouteLocationNormalized } from 'vue-router'

export function requireAuthGuard(to: RouteLocationNormalized, next: NavigationGuardNext) {
  const tok = sessionStorage.getItem('dslm_admin_token')?.trim() || ''
  if (!tok) {
    next({ name: 'login' })
    return
  }
  next()
}

