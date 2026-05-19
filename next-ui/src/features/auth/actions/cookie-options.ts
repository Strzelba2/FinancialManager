export function shouldUseSecureAuthCookies(): boolean {
  const explicit = process.env.AUTH_COOKIE_SECURE?.trim().toLowerCase()
  if (explicit) {
    return !['0', 'false', 'no', 'off'].includes(explicit)
  }

  const publicAppUrl = process.env.NEXT_PUBLIC_APP_URL ?? ''
  return process.env.NODE_ENV === 'production' || publicAppUrl.startsWith('https://')
}

export function sessionAuthReferer(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const nextUiDomain = process.env.NEXT_UI_DOMAIN?.trim()
  const publicAppUrl = process.env.NEXT_PUBLIC_APP_URL?.trim()

  if (nextUiDomain) {
    if (/^https?:\/\//i.test(nextUiDomain)) {
      return new URL(normalizedPath, nextUiDomain).toString()
    }

    let protocol = (process.env.APP_PROTOCOL ?? '').replace(/:$/, '')
    if (!protocol && publicAppUrl) {
      try {
        const publicUrl = new URL(publicAppUrl)
        const publicHost = publicUrl.host.toLowerCase().split(':')[0]
        const nextHost = nextUiDomain.toLowerCase().split(':')[0]
        if (publicHost === nextHost) {
          protocol = publicUrl.protocol.replace(/:$/, '')
        }
      } catch {
        // Fall back to HTTP below for malformed optional public URLs.
      }
    }

    return `${protocol || 'http'}://${nextUiDomain}${normalizedPath}`
  }

  if (publicAppUrl) {
    try {
      return new URL(normalizedPath, publicAppUrl).toString()
    } catch {
      // Fall back to the local Next host for malformed optional public URLs.
    }
  }

  const protocol = (process.env.APP_PROTOCOL ?? 'http').replace(/:$/, '')
  return `${protocol}://next.localhost${normalizedPath}`
}
