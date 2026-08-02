/** Wraps one async action with its own loading and error state.
 *  Each panel owns an instance, so a failure in one never blanks another. */

import { useCallback, useState } from 'react'

import { ApiError } from '../api/client'

export function useAsync<Args extends unknown[], T>(
  action: (...args: Args) => Promise<T>,
) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(
    async (...args: Args): Promise<T | null> => {
      setLoading(true)
      setError(null)
      try {
        return await action(...args)
      } catch (caught) {
        const message =
          caught instanceof ApiError ? caught.message : 'Something went wrong.'
        setError(message)
        return null
      } finally {
        setLoading(false)
      }
    },
    [action],
  )

  const reset = useCallback(() => {
    setError(null)
  }, [])

  return { run, loading, error, reset }
}
