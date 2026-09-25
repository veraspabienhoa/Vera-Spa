import { useEffect, useMemo, useState } from 'react'
import { veraApi } from '../lib/api'

export default function useLiveTourDetails({ board, panel, filters, customerSearch, lookupOpen, lookupSearch, selectedCustomerId, enabled = true }) {
  const [page, setPage] = useState(1)
  const [result, setResult] = useState(null)
  const [lookupState, setLookup] = useState({revision:null,rows:[]})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const queryKey = JSON.stringify(panel === 'customers' ? {search:customerSearch} : filters)
  useEffect(() => { setPage(1) }, [panel, queryKey])
  useEffect(() => {
    if (!enabled || !['customers','pending','invoices','reports','history'].includes(panel) || board.revision == null) {setLoading(false);return}
    let cancelled = false
    setLoading(true); setError('')
    const timer = setTimeout(() => {
      veraApi.liveTourCollection(panel, { ...JSON.parse(queryKey), page }).then(value => {
        if (!cancelled) setResult({panel, queryKey, page, value, requestRevision:board.revision})
      }).catch(err => { if (!cancelled) {setResult(null);setError(err.message)} })
        .finally(() => { if (!cancelled) setLoading(false) })
    }, 180)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [enabled, panel, queryKey, page, board.revision])
  useEffect(() => {
    if (!enabled) return
    if (!lookupOpen) {setLookup({revision:null,rows:[]});return}
    let cancelled = false
    const timer = setTimeout(() => {
      Promise.all([veraApi.liveTourCollection('customers', { search:lookupSearch, page_size:100 }), ...(selectedCustomerId ? [veraApi.liveTourCollection('customers',{customer_id:selectedCustomerId})] : [])]).then(values => {
        if (!cancelled) setLookup(old => ({revision:board.revision,rows:[...new Map([...(old.revision===board.revision ? old.rows : []),...values.flatMap(value=>value.data.customers)].map(row=>[row.id,row])).values()]}))
      }).catch(err => {if(!cancelled)setError(err.message)})
    },180)
    return () => {cancelled=true;clearTimeout(timer)}
  }, [enabled, lookupOpen, lookupSearch, selectedCustomerId, board.revision])
  const lookup=useMemo(()=>lookupState.revision===board.revision ? lookupState.rows : [],[lookupState,board.revision])
  const value = result?.requestRevision === board.revision && result?.panel === panel && result.queryKey === queryKey && result.page === page ? result.value : null
  const data = useMemo(() => {
    const detail=value?.data || {}
    const customers=[...new Map([...(detail.customers || board.customers || []), ...lookup].map(row=>[row.id,row])).values()]
    return {...board,...detail,customers,state:{...board.state,...detail.state,customers}}
  },[board,value,lookup])
  return {data,page,setPage,pages:value?.pages || 1,total:value?.total || 0,loading,error}
}
