import { useEffect, useState } from 'react'
import { toastEmitter, type ToastEvent } from '../lib/toastEmitter'

const DISMISS_MS = 4000

/**
 * Toast notification container + provider.
 *
 * Renders a fixed stack of toast notifications in the bottom-right corner.
 * Subscribes to the module-level `toastEmitter` so the axios interceptor
 * can push toasts without being inside the React tree.
 *
 * Each toast auto-dismisses after 4 seconds and can be dismissed manually.
 */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastEvent[]>([])

  useEffect(() => {
    const unsubscribe = toastEmitter.subscribe((event) => {
      setToasts((prev) => [...prev, event])
      // Auto-dismiss after DISMISS_MS
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== event.id))
      }, DISMISS_MS)
    })
    return unsubscribe
  }, [])

  function dismiss(id: number) {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  return (
    <>
      {children}

      {/* Toast stack — fixed, bottom-right */}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none"
      >
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </div>
    </>
  )
}

// ── ToastItem ──────────────────────────────────────────────────────────────

interface ToastItemProps {
  toast: ToastEvent
  onDismiss: (id: number) => void
}

function ToastItem({ toast, onDismiss }: ToastItemProps) {
  const isError = toast.type === 'error'

  return (
    <div
      role="alert"
      className={`pointer-events-auto flex items-start gap-3 rounded-lg border px-4 py-3 shadow-md text-sm
        ${isError
          ? 'bg-red-50 border-red-200 text-red-800'
          : 'bg-green-50 border-green-200 text-green-800'
        }`}
    >
      {/* Icon */}
      {isError ? (
        <svg
          className="h-4 w-4 mt-0.5 shrink-0 text-red-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"
          />
        </svg>
      ) : (
        <svg
          className="h-4 w-4 mt-0.5 shrink-0 text-green-500"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
        </svg>
      )}

      {/* Message */}
      <span className="flex-1 leading-relaxed">{toast.message}</span>

      {/* Dismiss button */}
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        className={`shrink-0 rounded p-0.5 transition-colors focus:outline-none focus-visible:ring-2
          ${isError
            ? 'text-red-400 hover:text-red-600 hover:bg-red-100 focus-visible:ring-red-400'
            : 'text-green-400 hover:text-green-600 hover:bg-green-100 focus-visible:ring-green-400'
          }`}
        aria-label="Dismiss notification"
      >
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  )
}
