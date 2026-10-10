import { useEffect, useMemo, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { createLiveTourRefresh } from './liveTourRefresh'

export default function useLiveTourDetails({ board, panel, filters, customerSearch, lookupOpen, lookupSearch, selectedCustomerId, selectedCustomerIds = [], enabled = true, authorizationKey = '', readAllowed = true, onCapabilities, onReadDenied }) {
  const onDeniedRef = useRef(onReadDenied)
  onDeniedRef.current = onReadDenied
  const onCapabilitiesRef = useRef(onCapabilities)
  onCapabilitiesRef.current = onCapabilities
  const [page, setPage] = useState(1)
  const [result, setResult] = useState(null)
  const [lookupState, setLookup] = useState({revision:null,rows:[]})
  const [error, setError] = useState('')
  const [lookupError, setLookupError] = useState('')
  const [loading, setLoading] = useState(false)
  const revisionRef = useRef(board.revision)
  revisionRef.current = board.revision
  const refreshRef = useRef(null)
  const lookupRefreshRef = useRef(null)
  const hasBoard = board.revision != null
  const selectedIdsKey = [...new Set([selectedCustomerId, ...selectedCustomerIds].filter(Boolean))].sort().join(',')
  const queryKey = JSON.stringify(panel === 'customers' ? {search:customerSearch} : filters)
  const scopeKey = JSON.stringify([authorizationKey, panel, queryKey])
  const lookupKey = JSON.stringify([lookupSearch, selectedIdsKey])
  useEffect(() => { setPage(1) }, [panel, queryKey])
  useEffect(() => {
    if (!enabled || !readAllowed || !['customers','pending','invoices','reports','history'].includes(panel) || !hasBoard) {setLoading(false);return}
    const reader = createLiveTourRefresh({
      getRevision: () => revisionRef.current,
      read: ({signal}) => veraApi.liveTourCollection(panel, { ...JSON.parse(queryKey), page }, {signal}),
      onData: (value, {loadedRevision}) => {
        onCapabilitiesRef.current?.(value.capabilities || value.data?.capabilities)
        setResult({panel, queryKey, scopeKey, page, value, loadedRevision})
      },
      onError: err => {setResult(null);setError(err.message);if(err.status === 403)onDeniedRef.current?.(panel,err)},
      onLoading: value => {setLoading(value);if(value)setError('')},
    })
    refreshRef.current = reader.schedule
    reader.schedule()
    return () => { reader.dispose(); refreshRef.current = null }
  }, [enabled, readAllowed, panel, queryKey, scopeKey, page, hasBoard])
  useEffect(() => {
    if (!enabled) return
    if (!lookupOpen) {setLookup({revision:null,rows:[]});setLookupError('');return}
    if (!hasBoard) return
    setLookupError('')
    const [search, customerIds] = JSON.parse(lookupKey)
    const reader = createLiveTourRefresh({
      getRevision: () => revisionRef.current,
      read: async ({signal, requestRevision}) => {
        // Wait for both reads, even when one fails, before starting another
        // batch. The shared transport bounds each read with its own deadline.
        const settled = await Promise.allSettled([
          veraApi.liveTourCollection('customers', {search, page_size:100}, {signal}),
          ...(customerIds ? [veraApi.liveTourCollection('customers', {customer_ids:customerIds, page_size:100}, {signal})] : []),
        ])
        const failed = settled.find(item => item.status === 'rejected')
        if (failed) throw failed.reason
        const values = settled.map(item => item.value)
        // Separate customer queries can see different committed snapshots. The
        // batch is only as fresh as its oldest response, including reservations.
        return {revision:Math.min(...values.map(value => value.revision ?? requestRevision)),
          rows:[...new Map(values.flatMap(value => value.data.customers).map(row => [row.id,row])).values()]}
      },
      onData: value => {
        // Retain selected customers while searching within the same snapshot.
        setLookup(old => ({revision:value.revision,rows:[...new Map([
          ...(old.revision===value.revision ? old.rows : []),...value.rows,
        ].map(row => [row.id,row])).values()]}))
        setLookupError('')
      },
      onError: err => setLookupError(err.message),
    })
    lookupRefreshRef.current = reader.schedule
    reader.schedule()
    return () => {reader.dispose();lookupRefreshRef.current = null}
  }, [enabled, lookupOpen, lookupKey, hasBoard, authorizationKey])
  useEffect(() => { refreshRef.current?.();lookupRefreshRef.current?.() }, [board.revision])
  const lookup=useMemo(()=>lookupOpen && lookupState.revision===board.revision ? lookupState.rows : [],[lookupState,board.revision,lookupOpen])
  const value = readAllowed && result?.scopeKey === scopeKey && result?.panel === panel && result.queryKey === queryKey && result.page === page ? result.value : null
  useEffect(() => { setResult(null); setError(''); setLookup({revision:null,rows:[]}); setLookupError('') }, [authorizationKey])
  const data = useMemo(() => {
    const detail=value?.data || {}
    const base = authorizationKey && ['pending', 'invoices', 'reports', 'history'].includes(panel) && !value
      ? { ...board, pending_payments: [], pending: [], invoices: [], reports: {}, report_rows: [], report_totals: {}, pending_changes: [], invoice_changes: [], customer_changes: [], break_events: [], audit: [], history: [], backups: [],
        state: { ...board.state, pending: [], invoices: [], reports: [], audit: [], backups: [] } } : board
    const customers=[...new Map([...(detail.customers || board.customers || []), ...lookup].map(row=>[row.id,row])).values()]
    return {...base,...detail,revision:value ? result.loadedRevision : board.revision,customers,state:{...base.state,...detail.state,customers}}
  },[board,value,result,lookup,authorizationKey,panel])
  return {data,page,setPage,ready:Boolean(value),initialLoading:loading && !value,pages:value?.pages || 1,total:value?.total || 0,loading,error:error || lookupError}
}
