// One read at a time, including overlapping filter changes and refreshes.
// Remember only the keys already displayed, never cache employee/policy data
// across pages or sessions. Explicit refreshes always read the server again.
export function createLeavePageLoader() {
  const completedKeys = new Map()
  let revision = 0
  let tail = Promise.resolve()
  let loading = false
  let controller = null

  return {
    invalidate() { revision += 1; controller?.abort(); loading = false },
    isLoading() { return loading },
    run(jobs, { onlyChanged = false, onStart, onData, onError, onFinish }) {
      controller?.abort()
      controller = new AbortController()
      const signal = controller.signal
      const currentRevision = ++revision
      const current = () => currentRevision === revision
      const needed = jobs.filter((job) => !onlyChanged || completedKeys.get(job.id) !== job.key)
      // Invalidate at scheduling time: switching away and immediately back
      // must not leave a section marked loading with its refresh skipped.
      for (const job of needed) completedKeys.delete(job.id)
      loading = needed.length > 0
      onStart(needed.map((job) => job.id))
      const result = tail.then(async () => {
        if (!current()) return false
        let successful = true
        try {
          for (const job of needed) {
            if (!current()) return false
            try {
              const data = await job.read({ signal })
              if (!current()) return false
              onData(job.id, data)
              completedKeys.set(job.id, job.key)
            } catch (error) {
              if (!current()) return false
              successful = false
              onError(job.id, error)
            }
          }
          return successful
        } finally {
          if (current()) {
            loading = false
            onFinish()
          }
        }
      })
      tail = result.catch(() => {})
      return result
    },
  }
}
