'use client'

import { useMemo, useState } from 'react'
import * as Popover from '@radix-ui/react-popover'
import {
  addMonths,
  endOfMonth,
  endOfWeek,
  format,
  getHours,
  getMinutes,
  isSameDay,
  isSameMonth,
  isToday,
  parse,
  setHours,
  setMinutes,
  startOfMonth,
  startOfWeek,
  subMonths,
} from 'date-fns'
import { pl } from 'date-fns/locale'
import { CalendarDays, ChevronLeft, ChevronRight, Clock3, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

type Props = {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  variant?: 'field' | 'inline'
  className?: string
}

const WEEK_DAYS = ['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'Sb', 'Nd']

function parseLocalDateTime(value: string): Date | null {
  if (!value) return null
  const parsed = parse(value, "yyyy-MM-dd'T'HH:mm", new Date())
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function toLocalDateTimeString(date: Date): string {
  return format(date, "yyyy-MM-dd'T'HH:mm")
}

export function DateTimePicker({
  value,
  onChange,
  placeholder = 'Wybierz datę',
  variant = 'field',
  className,
}: Props) {
  const selectedDate = parseLocalDateTime(value)
  const [open, setOpen] = useState(false)
  const [month, setMonth] = useState<Date>(selectedDate ?? new Date())

  const calendarDays = useMemo(() => {
    const start = startOfWeek(startOfMonth(month), { weekStartsOn: 1 })
    const end = endOfWeek(endOfMonth(month), { weekStartsOn: 1 })
    const days: Date[] = []
    let cursor = start

    while (cursor <= end) {
      days.push(cursor)
      cursor = new Date(cursor)
      cursor.setDate(cursor.getDate() + 1)
    }

    return days
  }, [month])

  const hour = selectedDate ? String(getHours(selectedDate)).padStart(2, '0') : '12'
  const minute = selectedDate ? String(getMinutes(selectedDate)).padStart(2, '0') : '00'

  function updateDate(nextDate: Date) {
    const base = selectedDate ?? new Date()
    const withHour = setHours(nextDate, getHours(base))
    const withMinute = setMinutes(withHour, getMinutes(base))
    onChange(toLocalDateTimeString(withMinute))
  }

  function updateTime(nextHour: string, nextMinute: string) {
    const base = selectedDate ?? new Date()
    let next = setHours(base, Number(nextHour))
    next = setMinutes(next, Number(nextMinute))
    onChange(toLocalDateTimeString(next))
  }

  const triggerClassName = variant === 'field'
    ? 'h-9 w-full justify-between rounded-lg border border-white/10 bg-slate-800/90 px-3 text-sm text-white hover:bg-slate-700/90'
    : 'h-7 w-full justify-between rounded-md border border-transparent bg-transparent px-1 text-xs text-white hover:border-white/8 hover:bg-slate-700/25'

  return (
    <Popover.Root
      open={open}
      onOpenChange={(next) => {
        if (next) setMonth(selectedDate ?? new Date())
        setOpen(next)
      }}
    >
      <Popover.Trigger asChild>
        <Button type="button" variant="ghost" className={cn(triggerClassName, className)}>
          <span className="truncate">
            {selectedDate ? format(selectedDate, 'dd.MM.yyyy, HH:mm') : placeholder}
          </span>
          <CalendarDays className="w-4 h-4 text-white/55" />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          sideOffset={8}
          align="start"
          className="z-[70] w-[320px] rounded-2xl border border-white/10 bg-slate-900/98 p-3 text-white shadow-2xl backdrop-blur-md"
        >
          <div className="flex items-center justify-between mb-3">
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => setMonth((current) => subMonths(current, 1))}
              className="text-white/60 hover:text-white hover:bg-white/10"
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <p className="text-sm font-medium capitalize">
              {format(month, 'LLLL yyyy', { locale: pl })}
            </p>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => setMonth((current) => addMonths(current, 1))}
              className="text-white/60 hover:text-white hover:bg-white/10"
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>

          <div className="grid grid-cols-7 gap-1 mb-2">
            {WEEK_DAYS.map((day) => (
              <div key={day} className="text-center text-[11px] text-white/40 py-1">
                {day}
              </div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-1">
            {calendarDays.map((day) => {
              const isSelected = selectedDate ? isSameDay(day, selectedDate) : false
              const isOutsideMonth = !isSameMonth(day, month)
              const today = isToday(day)

              return (
                <button
                  key={day.toISOString()}
                  type="button"
                  onClick={() => updateDate(day)}
                  className={cn(
                    'h-9 rounded-xl text-sm transition-colors',
                    isOutsideMonth && 'text-white/25',
                    !isOutsideMonth && 'text-white/80',
                    today && !isSelected && 'border border-sky-400/35',
                    isSelected
                      ? 'bg-sky-500 text-white shadow-[0_0_0_1px_rgba(125,211,252,0.32)]'
                      : 'hover:bg-white/8',
                  )}
                >
                  {format(day, 'd')}
                </button>
              )
            })}
          </div>

          <div className="mt-3 rounded-xl border border-white/10 bg-slate-800/60 p-3">
            <div className="flex items-center gap-2 mb-2">
              <Clock3 className="w-4 h-4 text-white/50" />
              <span className="text-xs text-white/55 uppercase tracking-wide">Godzina</span>
            </div>
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
              <input
                type="number"
                min={0}
                max={23}
                value={hour}
                onChange={(e) => {
                  const nextHour = e.target.value === '' ? '00' : e.target.value.padStart(2, '0')
                  updateTime(nextHour, minute)
                }}
                className="h-9 rounded-lg border border-white/10 bg-slate-900/70 px-3 text-center text-sm text-white outline-none focus:border-sky-400/40"
              />
              <span className="text-white/45">:</span>
              <input
                type="number"
                min={0}
                max={59}
                value={minute}
                onChange={(e) => {
                  const nextMinute = e.target.value === '' ? '00' : e.target.value.padStart(2, '0')
                  updateTime(hour, nextMinute)
                }}
                className="h-9 rounded-lg border border-white/10 bg-slate-900/70 px-3 text-center text-sm text-white outline-none focus:border-sky-400/40"
              />
            </div>
          </div>

          <div className="mt-3 flex items-center justify-between">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onChange('')}
              className="text-white/50 hover:text-white hover:bg-white/10 gap-1"
            >
              <X className="w-3.5 h-3.5" /> Wyczyść
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={() => {
                const now = new Date()
                onChange(toLocalDateTimeString(now))
                setMonth(now)
              }}
              className="bg-sky-700 hover:bg-sky-600 text-white"
            >
              Teraz
            </Button>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
