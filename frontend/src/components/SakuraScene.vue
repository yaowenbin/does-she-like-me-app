<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

type Petal = {
  x: number
  y: number
  r: number
  vx: number
  vy: number
  rot: number
  vr: number
  scale: number
  alpha: number
  color: string
}

const canvasRef = ref<HTMLCanvasElement | null>(null)
let rafId = 0
let ctx: CanvasRenderingContext2D | null = null
let petals: Petal[] = []
let w = 0
let h = 0
let dpr = 1
let running = true

function rand(min: number, max: number) {
  return Math.random() * (max - min) + min
}

function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false
}

function createPetal(): Petal {
  const palette = ['#ff7fb5', '#ffc1da', '#a98bff']
  return {
    x: rand(0, w),
    y: rand(-h * 0.3, h),
    r: rand(6, 18),
    vx: rand(-0.18, 0.18),
    vy: rand(0.35, 1.2),
    rot: rand(0, Math.PI * 2),
    vr: rand(-0.02, 0.02),
    scale: rand(0.7, 1.15),
    alpha: rand(0.35, 0.75),
    color: palette[Math.floor(rand(0, palette.length))],
  }
}

function resize() {
  const el = canvasRef.value
  if (!el) return
  dpr = window.devicePixelRatio || 1
  w = el.clientWidth
  h = el.clientHeight
  el.width = Math.floor(w * dpr)
  el.height = Math.floor(h * dpr)
  ctx = el.getContext('2d')
  if (ctx) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  }

  const targetCount = Math.max(45, Math.min(120, Math.floor((w * h) / 42000)))
  petals = Array.from({ length: targetCount }, () => createPetal())
}

function drawPetal(p: Petal) {
  if (!ctx) return
  const { x, y, r, rot, scale, alpha, color } = p
  ctx.save()
  ctx.translate(x, y)
  ctx.rotate(rot)

  const grad = ctx.createRadialGradient(0, 0, r * 0.1, 0, 0, r)
  grad.addColorStop(0, `${color}`)
  grad.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.globalAlpha = alpha
  ctx.fillStyle = grad

  // 叶片（对称花瓣）用两个椭圆近似
  ctx.beginPath()
  ctx.ellipse(0, 0, r * 0.55 * scale, r * 0.35 * scale, 0, 0, Math.PI * 2)
  ctx.fill()
  ctx.globalAlpha = alpha * 0.9
  ctx.strokeStyle = 'rgba(255,255,255,0.35)'
  ctx.lineWidth = 1
  ctx.stroke()

  ctx.restore()
}

function tick() {
  if (!running) return
  if (!ctx) return

  ctx.clearRect(0, 0, w, h)

  for (const p of petals) {
    p.x += p.vx
    p.y += p.vy
    p.rot += p.vr

    // 回收：落出底部后回到顶部
    if (p.y > h + p.r) {
      p.x = rand(0, w)
      p.y = rand(-h * 0.2, -10)
      p.vy = rand(0.35, 1.2)
      p.alpha = rand(0.35, 0.75)
      p.scale = rand(0.7, 1.15)
    }

    drawPetal(p)
  }

  rafId = requestAnimationFrame(tick)
}

onMounted(() => {
  const reduce = prefersReducedMotion()
  if (reduce) return

  resize()
  window.addEventListener('resize', resize)
  rafId = requestAnimationFrame(tick)
})

onBeforeUnmount(() => {
  running = false
  cancelAnimationFrame(rafId)
  window.removeEventListener('resize', resize)
})
</script>

<template>
  <div class="sakura-layer" aria-hidden="true">
    <canvas ref="canvasRef" class="sakura-canvas"></canvas>

    <!-- 静态 SVG：用于氛围层（分布在角落的小花） -->
    <svg class="sakura-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
      <g opacity="0.35" fill="none" stroke-linecap="round" stroke-linejoin="round">
        <path
          d="M10,85 C18,70 25,58 36,50 C48,40 63,35 82,34"
          stroke="rgba(169,139,255,0.35)"
          stroke-width="1.6"
        />
        <circle cx="18" cy="78" r="2.6" fill="rgba(255,127,181,0.38)" stroke="rgba(255,127,181,0.25)" />
        <circle cx="32" cy="58" r="2.1" fill="rgba(255,193,218,0.45)" stroke="rgba(255,193,218,0.25)" />
        <circle cx="52" cy="45" r="2.4" fill="rgba(255,127,181,0.35)" stroke="rgba(255,127,181,0.22)" />
        <circle cx="70" cy="38" r="2.0" fill="rgba(169,139,255,0.38)" stroke="rgba(169,139,255,0.22)" />
        <circle cx="84" cy="36" r="2.2" fill="rgba(255,193,218,0.4)" stroke="rgba(255,193,218,0.22)" />
      </g>
    </svg>
  </div>
</template>

