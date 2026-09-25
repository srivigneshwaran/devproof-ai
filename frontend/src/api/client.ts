import axios from 'axios'

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

// Response interceptor — normalise API errors so callers receive a plain Error
// with the backend's `error` field as the message.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message: string =
      error.response?.data?.error ??
      error.response?.data?.detail ??
      error.message ??
      'An unexpected error occurred.'
    return Promise.reject(new Error(message))
  },
)
