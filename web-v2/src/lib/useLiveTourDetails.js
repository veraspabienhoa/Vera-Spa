import { useEffect, useMemo, useRef, useState } from 'react'
import { veraApi } from '../lib/api'

export default function useLiveTourDetails({ board, panel, filters, customerSearch, lookupOpen, lookupSearch, selectedCustomerId, enabled = true }) {
  const [page, setPage] = useState(1)
  const [result, setResult] = useState(null)
  const [lookupState, setLookup] = useState({revision:null,rows:[]})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const revisionRef = useRef(board.revision)
  revisionRef.current = board.revision
  const refreshRef = useRef(null)
  const hasBoard = board.revision != null
  const queryKey = JSON.stringify(panel === 'customers' ? {search:customerSearch} : filters)
  useEffect(() => { setPage(1) }, [panel, queryKey])
  useEffect(() => {
    if (!enabled || !['customers','pending','invoices','reports','history'].includes(panel) || !hasBoard) {setLoading(false);return}
    let cancelled = false
    let pending = false
    let timer
    const controller = new AbortController()
    const load = () => {
      if (cancelled || pending) return
      pending = true
      const requestRevision = revisionRef.current
      setLoading(true); setError('')
      veraApi.liveTourCollection(panel, { ...JSON.parse(queryKey), page }, {signal:controller.signal}).then(value => {
        if (!cancelled) setResult({panel, queryKey, page, value, requestRevision})
      }).catch(err => { if (!cancelled) {setResult(null);setError(err.message)} })
        .finally(() => { pending = false; if (!cancelled) setLoading(false) })
    }
    // Revision changes coalesce into the next read; they must not discard a
    // response still loading or start overlapping reads every board poll.
    const schedule = () => {
      if (timer || pending) return
      setLoading(true)
      timer = setTimeout(() => { timer = null; load() }, 180)
    }
    refreshRef.current = schedule
    schedule()
    return () => { cancelled = true; clearTimeout(timer); controller.abort(); refreshRef.current = null }
  }, [enabled, panel, queryKey, page, hasBoard])
  useEffect(() => { refreshRef.current?.() }, [board.revision])
  useEffect(() => {
    if (!enabled) return
    if (!lookupOpen) {setLookup({revision:null,rows:[]});return}
    let cancelled = false
    const controller = new AbortController()
    const timer = setTimeout(() => {
      Promise.all([veraApi.liveTourCollection('customers', { search:lookupSearch, page_size:100 }, {signal:controller.signal}), ...(selectedCustomerId ? [veraApi.liveTourCollection('customers',{customer_id:selectedCustomerId}, {signal:controller.signal})] : [])]).then(values => {
        if (!cancelled) setLookup(old => ({revision:board.revision,rows:[...new Map([...(old.revision===board.revision ? old.rows : []),...values.flatMap(value=>value.data.customers)].map(row=>[row.id,row])).values()]}))
      }).catch(err => {if(!cancelled)setError(err.message)})
    },180)
    return () => {cancelled=true;clearTimeout(timer);controller.abort()}
  }, [enabled, lookupOpen, lookupSearch, selectedCustomerId, board.revision])
  const lookup=useMemo(()=>lookupState.revision===board.revision ? lookupState.rows : [],[lookupState,board.revision])
  const value = result?.panel === panel && result.queryKey === queryKey && result.page === page ? result.value : null
  const data = useMemo(() => {
    const detail=value?.data || {}
    const customers=[...new Map([...(detail.customers || board.customers || []), ...lookup].map(row=>[row.id,row])).values()]
    return {...board,...detail,revision:value?.revision ?? board.revision,customers,state:{...board.state,...detail.state,customers}}
  },[board,value,lookup])
  return {data,page,setPage,ready:Boolean(value),initialLoading:loading && !value,pages:value?.pages || 1,total:value?.total || 0,loading,error}
}
