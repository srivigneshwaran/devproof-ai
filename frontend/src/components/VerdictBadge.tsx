import type { Verdict } from '../api/reportApi'

interface Props {
  verdict: Verdict
}

const STYLES: Record<Verdict, string> = {
  PASS:    'bg-green-100 text-green-800 border-green-200',
  FAIL:    'bg-red-100 text-red-800 border-red-200',
  PARTIAL: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  ERROR:   'bg-orange-100 text-orange-800 border-orange-200',
}

/**
 * Colour-coded verdict badge.
 * PASS = green, FAIL = red, PARTIAL = yellow, ERROR = orange.
 */
export function VerdictBadge({ verdict }: Props) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-3 py-1 text-sm font-bold tracking-wide ${STYLES[verdict]}`}
    >
      {verdict}
    </span>
  )
}
