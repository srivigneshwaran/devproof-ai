import axios from 'axios'
import { toastEmitter } from '../lib/toastEmitter'

/**
 * Shared axios instance.
 * Base URL is read from the VITE_API_URL environment variable at build time.
 * Falls back to '/api' for development proxying through Vite.
 */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor — normalise API errors, emit toast notifications, and
// reject with a plain Error so individual callers receive the message string.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status: number | undefined = error.response?.status

    // Pick the most descriptive message from the response body.
    let message: string =
      error.response?.data?.error ??
      error.response?.data?.detail ??
      error.message ??
      'An unexpected error occurred.'

    // ST-14: translate specific status codes to user-friendly messages.
    if (status === 409) {
      message = 'Fix must be approved before running verification.'
    } else if (
      typeof message === 'string' &&
      (message.toLowerCase().includes('llm') ||
        message.toLowerCase().includes('openai') ||
        message.toLowerCase().includes('anthropic') ||
        message.toLowerCase().includes('ai service'))
    ) {
      message = 'AI service unavailable — please retry.'
    }

    // Emit a toast so every page gets error feedback without extra code.
    toastEmitter.emit('error', message)

    return Promise.reject(new Error(message))
  },
)
