<script setup lang="ts">
import { NConfigProvider, darkTheme, type GlobalThemeOverrides } from 'naive-ui'

/** ui-ux-pro-max: OLED 暗色 + 品牌粉 accent（让后台不突兀） */
const adminThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#f472b6',
    primaryColorHover: '#f9a8d4',
    primaryColorPressed: '#ec4899',
    primaryColorSuppl: '#fbcfe8',
    borderRadius: '12px',
    borderRadiusSmall: '8px',
  },
}
</script>

<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="adminThemeOverrides">
    <div class="adminShell">
      <div class="adminMesh" aria-hidden="true" />
      <div class="adminNoise" aria-hidden="true" />
      <div class="adminLayout">
        <router-view />
      </div>
    </div>
  </n-config-provider>
</template>

<style>
.adminShell {
  position: relative;
  min-height: 100vh;
  color: #e2e8f0;
  padding: 1.25rem 1rem 4rem;
}

@media (min-width: 768px) {
  .adminShell {
    padding: 1.5rem 1.75rem 4.5rem;
  }
}

.adminMesh {
  pointer-events: none;
  position: fixed;
  inset: 0;
  z-index: 0;
  background:
    radial-gradient(1200px 600px at 80% -10%, rgba(244, 114, 182, 0.14), transparent 55%),
    radial-gradient(900px 500px at 10% 20%, rgba(99, 102, 241, 0.12), transparent 50%),
    linear-gradient(180deg, #05060a 0%, #080a11 45%, #05060a 100%);
}

.adminNoise {
  pointer-events: none;
  position: fixed;
  inset: 0;
  z-index: 0;
  opacity: 0.035;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}

.adminLayout {
  position: relative;
  z-index: 1;
  max-width: 1280px;
  margin: 0 auto;
  width: 100%;
}

.adminNav {
  position: sticky;
  top: 1rem;
  z-index: 20;
  margin-bottom: 1rem;
}

.adminNavInner {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.25rem;
  padding: 0.95rem 1.15rem;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(10, 12, 18, 0.72);
  backdrop-filter: blur(18px) saturate(1.2);
  -webkit-backdrop-filter: blur(18px) saturate(1.2);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.04) inset,
    0 24px 48px rgba(0, 0, 0, 0.35);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.adminEyebrow {
  margin: 0 0 0.35rem;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(244, 114, 182, 0.85);
}

.adminTitle {
  margin: 0;
  font-size: clamp(1.35rem, 3vw, 1.75rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
  color: #f8fafc;
}

.adminSubtitle {
  margin: 0.5rem 0 0;
  max-width: 42rem;
  font-size: 13px;
  line-height: 1.55;
  color: rgba(148, 163, 184, 0.92);
}

.auth {
  display: grid;
  gap: 8px;
  align-content: start;
  min-width: min(420px, 92vw);
}

.adminBody {
  background: transparent;
}

.adminSider {
  background: rgba(8, 10, 14, 0.35);
}

.adminContent {
  padding: 0.15rem 0.65rem 1.2rem;
}

.sectionWrap {
  padding-top: 0.6rem;
}

.sectionCard {
  border-radius: 16px;
  background: rgba(10, 12, 18, 0.55);
  border: 1px solid rgba(148, 163, 184, 0.12);
  backdrop-filter: blur(12px) saturate(1.1);
  -webkit-backdrop-filter: blur(12px) saturate(1.1);
}

.innerCard {
  margin-top: 10px;
}

.opsRow {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.opsCol {
  display: grid;
  gap: 8px;
}

.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin: 10px 0;
}

.line {
  display: grid;
  grid-template-columns: auto auto auto 1fr;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px dashed rgba(148, 163, 184, 0.25);
}

.mutedText {
  color: rgba(148, 163, 184, 0.95);
}

.loginCard {
  border-radius: 16px !important;
}

.loginCardInner {
  padding: 1.75rem 1.5rem 2rem;
}

@media (max-width: 900px) {
  .stats {
    grid-template-columns: repeat(2, 1fr);
  }
  .line {
    grid-template-columns: 1fr;
  }
}
</style>
