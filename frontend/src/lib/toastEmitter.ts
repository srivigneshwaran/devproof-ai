/**
 * Lightweight module-level event bus for toast notifications.
 *
 * This lets the axios interceptor (which runs outside the React tree) emit
 * toast events that the ToastProvider (inside the React tree) can subscribe to.
 */

export type ToastType = 'error' | 'success'

export interface ToastEvent {
  id: number
  type: ToastType
  message: string
}

type Listener = (event: ToastEvent) => void

let _listeners: Listener[] = []
let _counter = 0

export const toastEmitter = {
  emit(type: ToastType, message: string): void {
    const event: ToastEvent = { id: ++_counter, type, message }
    _listeners.forEach((fn) => fn(event))
  },

  subscribe(fn: Listener): () => void {
    _listeners.push(fn)
    return () => {
      _listeners = _listeners.filter((l) => l !== fn)
    }
  },
}
