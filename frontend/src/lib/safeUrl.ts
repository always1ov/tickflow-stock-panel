/** 外链 URL 消毒: 仅 http(s)、≤500 字符、拒绝与本站同源(防同源 iframe 借道 sandbox 提权)。 */
export function sanitizeExtUrl(raw: string): string | null {
  const s = (raw ?? '').trim()
  if (!s || s.length > 500) return null
  let u: URL
  try {
    u = new URL(s)
  } catch {
    return null
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return null
  if (typeof window !== 'undefined' && u.origin === window.location.origin) return null
  return u.toString()
}
