export const VERSION_RADIX = 100

export function parseSemver(value) {
  const match = /^(\d+)\.(\d+)\.(\d+)/.exec(String(value || '').trim())
  if (!match) return null
  return { major: Number(match[1]), minor: Number(match[2]), patch: Number(match[3]) }
}

/**
 * 按百进制递增：
 * 1.1.0 → ... → 1.1.99 → 1.2.0 → ... → 1.99.99 → 2.0.0
 */
export function bumpVersion(baseVersion, increments) {
  const semver = parseSemver(baseVersion)
  if (!semver) return `${baseVersion}.${increments}`
  const total = semver.minor * VERSION_RADIX + semver.patch + Number(increments || 0)
  const carry = Math.floor(total / (VERSION_RADIX * VERSION_RADIX))
  const minor = Math.floor(total / VERSION_RADIX) % VERSION_RADIX
  const patch = total % VERSION_RADIX
  return `${semver.major + carry}.${minor}.${patch}`
}