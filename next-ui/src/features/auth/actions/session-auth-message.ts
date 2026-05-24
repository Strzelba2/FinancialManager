export function extractSessionAuthMessage(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed.length > 0 ? trimmed : undefined
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const message = extractSessionAuthMessage(item)
      if (message) return message
    }
    return undefined
  }

  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>

    for (const key of ['error', 'detail', 'message', 'non_field_errors']) {
      const message = extractSessionAuthMessage(record[key])
      if (message) return message
    }

    for (const nested of Object.values(record)) {
      const message = extractSessionAuthMessage(nested)
      if (message) return message
    }
  }

  return undefined
}

export async function readSessionAuthMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  const rawBody = await response.text().catch(() => '')

  if (rawBody) {
    try {
      const parsed = JSON.parse(rawBody) as unknown
      return extractSessionAuthMessage(parsed) ?? fallback
    } catch {
      const plainText = rawBody.trim()
      if (plainText && !plainText.startsWith('<')) {
        return plainText
      }
    }
  }

  return fallback
}
