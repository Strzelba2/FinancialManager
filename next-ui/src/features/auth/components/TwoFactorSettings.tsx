'use client'

import { createElement, useActionState } from 'react'
import { Loader2, QrCode, ShieldCheck, ShieldOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  disableTwoFactorAction,
  enableTwoFactorAction,
  setupTwoFactorAction,
} from '@/features/auth/actions/two-factor'

interface Props {
  initialEnabled: boolean
}

function QrCodeImage({ image }: { image: string }) {
  // QR arrives as a session-generated data URI and should not go through Next image optimization.
  return createElement('img', {
    src: `data:image/svg+xml;base64,${image}`,
    alt: 'Kod QR 2FA',
    width: 192,
    height: 192,
    className: 'h-48 w-48',
  })
}

export function TwoFactorSettings({ initialEnabled }: Props) {
  const [setupState, setupAction, setupPending] = useActionState(setupTwoFactorAction, undefined)
  const [enableState, enableAction, enablePending] = useActionState(enableTwoFactorAction, undefined)
  const [disableState, disableAction, disablePending] = useActionState(disableTwoFactorAction, undefined)
  const enabled = disableState?.success ? false : enableState?.success ? true : initialEnabled
  const qrImage = enabled ? undefined : setupState?.image

  return (
    <section className="rounded-lg border border-white/10 bg-white/5 p-5 text-white shadow-xl">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Uwierzytelnianie dwuskładnikowe</h2>
          <p className="mt-1 text-sm text-white/60">
            Status: {enabled ? 'aktywne' : 'nieaktywne'}
          </p>
        </div>
        <div className={`inline-flex w-fit items-center gap-2 rounded-md px-3 py-1.5 text-sm ${
          enabled ? 'bg-emerald-500/15 text-emerald-200' : 'bg-white/10 text-white/70'
        }`}
        >
          {enabled ? <ShieldCheck className="h-4 w-4" /> : <ShieldOff className="h-4 w-4" />}
          {enabled ? 'Chronione' : 'Wyłączone'}
        </div>
      </div>

      {!enabled && (
        <div className="mt-5 space-y-4">
          <form action={setupAction}>
            <Button
              type="submit"
              className="bg-emerald-500 hover:bg-emerald-400 text-white"
              disabled={setupPending}
            >
              {setupPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Generowanie…
                </>
              ) : (
                <>
                  <QrCode className="mr-2 h-4 w-4" />
                  Wygeneruj kod QR
                </>
              )}
            </Button>
          </form>

          {setupState?.message && (
            <p className="text-sm text-red-300">{setupState.message}</p>
          )}

          {qrImage && (
            <div className="grid gap-5 md:grid-cols-[220px_1fr] md:items-start">
              <div className="rounded-lg border border-white/10 bg-white p-3">
                <QrCodeImage image={qrImage} />
              </div>

              <form action={enableAction} className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="enable-token" className="text-white/80">Kod 2FA</Label>
                  <Input
                    id="enable-token"
                    name="token"
                    inputMode="numeric"
                    maxLength={6}
                    pattern="[0-9]*"
                    autoComplete="one-time-code"
                    className="max-w-xs bg-white/10 border-white/20 text-white placeholder:text-white/50"
                    placeholder="000000"
                  />
                  {enableState?.errors?.token && (
                    <p className="text-sm text-red-300">{enableState.errors.token[0]}</p>
                  )}
                </div>

                {enableState?.message && (
                  <p className={enableState.success ? 'text-sm text-emerald-200' : 'text-sm text-red-300'}>
                    {enableState.message}
                  </p>
                )}

                <Button
                  type="submit"
                  className="bg-emerald-500 hover:bg-emerald-400 text-white"
                  disabled={enablePending}
                >
                  {enablePending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Włączanie…
                    </>
                  ) : (
                    'Włącz 2FA'
                  )}
                </Button>
              </form>
            </div>
          )}
        </div>
      )}

      {enabled && (
        <form action={disableAction} className="mt-5 max-w-sm space-y-3">
          <div className="space-y-2">
            <Label htmlFor="disable-token" className="text-white/80">Kod 2FA</Label>
            <Input
              id="disable-token"
              name="token"
              inputMode="numeric"
              maxLength={6}
              pattern="[0-9]*"
              autoComplete="one-time-code"
              className="bg-white/10 border-white/20 text-white placeholder:text-white/50"
              placeholder="000000"
            />
            {disableState?.errors?.token && (
              <p className="text-sm text-red-300">{disableState.errors.token[0]}</p>
            )}
          </div>

          {disableState?.message && (
            <p className={disableState.success ? 'text-sm text-emerald-200' : 'text-sm text-red-300'}>
              {disableState.message}
            </p>
          )}

          <Button
            type="submit"
            variant="destructive"
            disabled={disablePending}
          >
            {disablePending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Wyłączanie…
              </>
            ) : (
              'Wyłącz 2FA'
            )}
          </Button>
        </form>
      )}
    </section>
  )
}
