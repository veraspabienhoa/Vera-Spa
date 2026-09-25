export async function refreshAfterLiveTourAction(result, load, applyBoard) {
  if (result?.refresh_board) {
    // load reports read errors separately; payment is already confirmed.
    void Promise.resolve().then(() => load(false, true)).catch(() => {})
  } else if (Array.isArray(result?.records) && Array.isArray(result?.columns)) {
    applyBoard(result)
  } else {
    await load(true, true)
  }
}
