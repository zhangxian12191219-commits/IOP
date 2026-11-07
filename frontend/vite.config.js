import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'
import fs from 'fs'
import crypto from 'crypto'
import { bumpVersion } from './versioning.js'

// 后端地址可通过环境变量覆盖，默认 http://localhost:8000
const API_TARGET = process.env.VITE_API_TARGET || 'http://localhost:8000'

function walkFiles(dir) {
  if (!fs.existsSync(dir)) return []
  const result = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) result.push(...walkFiles(full))
    else if (entry.isFile()) result.push(full)
  }
  return result.sort()
}

/**
 * 每次前端构建自动生成版本信息，写入：
 *   - frontend/dist/version.json（随构建产物发布，Docker/覆盖更新也能带上）
 *   - backend/version.json（本地开发/打包直接读取）
 *   - frontend/version-state.json（构建计数器，下一次构建在此基础上 +1）
 * 展示版本每次构建自动递增一个补丁号，并按五十进制进位：
 *   1.1.0 → ... → 1.1.49 → 1.2.0 → ... → 1.49.49 → 2.0.0
 * 构建时间仍写入版本详情。
 */

function autoVersionPlugin() {
  let outDir = ''
  return {
    name: 'nms-auto-version',
    apply: 'build',
    configResolved(config) {
      outDir = path.resolve(config.root, config.build.outDir)
    },
    closeBundle() {
      try {
        const pkg = JSON.parse(fs.readFileSync(path.resolve(__dirname, 'package.json'), 'utf-8'))
        // 排除构建产物自身的 version.json，避免版本文件参与哈希后自我变化
        const files = walkFiles(outDir).filter((file) => path.basename(file) !== 'version.json')
        const hash = crypto.createHash('sha256')
        for (const file of files) {
          hash.update(path.relative(outDir, file).replace(/\\/g, '/'))
          hash.update(fs.readFileSync(file))
        }
        const now = new Date()
        const pad = (value) => String(value).padStart(2, '0')
        const build = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}.${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
        const baseVersion = String(pkg.version || '1.0.0')
        const stateFile = path.resolve(__dirname, 'version-state.json')
        let previous = {}
        try {
          previous = JSON.parse(fs.readFileSync(stateFile, 'utf-8'))
        } catch {
          previous = {}
        }
        const envBuild = Number(process.env.NMS_BUILD_NUMBER || '')
        let buildNumber = 0
        if (Number.isInteger(envBuild) && envBuild > 0) {
          buildNumber = envBuild
        } else if (previous.base_version === baseVersion) {
          buildNumber = Number(previous.build_number || 0) + 1
        } else {
          buildNumber = 1
        }
        const version = bumpVersion(baseVersion, buildNumber)
        const payload = {
          version,
          display_version: version,
          base_version: baseVersion,
          build_number: buildNumber,
          build,
          build_id: hash.digest('hex').slice(0, 10),
          built_at: now.toISOString(),
          source: 'vite-build',
        }
        const serialized = `${JSON.stringify(payload, null, 2)}\n`
        // 必须先写入 dist：Docker 多阶段构建只会把 dist 带入运行镜像
        fs.writeFileSync(path.join(outDir, 'version.json'), serialized, 'utf-8')
        const backendDir = path.resolve(__dirname, '..', 'backend')
        if (fs.existsSync(backendDir)) {
          fs.writeFileSync(path.join(backendDir, 'version.json'), serialized, 'utf-8')
        }
        fs.writeFileSync(stateFile, `${JSON.stringify({
          base_version: baseVersion,
          build_number: buildNumber,
          version,
          updated_at: now.toISOString(),
        }, null, 2)}\n`, 'utf-8')
        console.log(`[nms-version] v${version} (build #${buildNumber}, ${payload.build})`)
      } catch (error) {
        console.warn('[nms-version] 自动版本生成失败:', error.message)
      }
    },
  }
}

export default defineConfig({
  plugins: [vue(), autoVersionPlugin()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    // 避免与前端路由 /assets 冲突，产物统一放在 /static 下
    assetsDir: 'static',
    chunkSizeWarningLimit: 1500,
  },
})
