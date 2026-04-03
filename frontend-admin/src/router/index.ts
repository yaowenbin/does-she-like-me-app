import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import LoginPage from '../pages/LoginPage.vue'
import AdminLayout from '../pages/admin/AdminLayout.vue'
import CodesPage from '../pages/admin/CodesPage.vue'
import FeedbackPage from '../pages/admin/FeedbackPage.vue'
import TuningPage from '../pages/admin/TuningPage.vue'
import QualityPage from '../pages/admin/QualityPage.vue'
import { requireAuthGuard } from './guard'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/admin/codes',
  },
  {
    path: '/login',
    name: 'login',
    component: LoginPage,
  },
  {
    path: '/admin',
    name: 'admin',
    component: AdminLayout,
    meta: { requiresAuth: true },
    children: [
      { path: 'codes', name: 'codes', component: CodesPage },
      { path: 'feedback', name: 'feedback', component: FeedbackPage },
      { path: 'tuning', name: 'tuning', component: TuningPage },
      { path: 'quality', name: 'quality', component: QualityPage },
      { path: '', redirect: '/admin/codes' },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/admin/codes' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  if (to.meta?.requiresAuth) return requireAuthGuard(to, next)
  next()
})
