import pino from 'pino'
import type { Logger } from 'pino'

const isDevelopment = process.env.NODE_ENV === 'development'
const loggerStore = globalThis as typeof globalThis & {
  __financialManagerNextLogger?: Logger
}

export const logger = loggerStore.__financialManagerNextLogger ?? pino({
  level: process.env.LOG_LEVEL ?? (isDevelopment ? 'debug' : 'info'),
  base: {
    service: 'frontend-next',
    env: process.env.NODE_ENV,
  },
  ...(isDevelopment
    ? {
        transport: {
          target: 'pino-pretty',
          options: {
            colorize: true,
            translateTime: 'SYS:standard',
          },
        },
      }
    : {}),
})

loggerStore.__financialManagerNextLogger = logger
