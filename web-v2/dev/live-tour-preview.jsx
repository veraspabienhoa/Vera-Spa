import React from 'react'
import { createRoot } from 'react-dom/client'
import LiveTourPage from '../src/pages/LiveTourPage'
import { veraApi } from '../src/lib/api'
import '../src/styles.css'

const viewer = new URLSearchParams(window.location.search).get('role') === 'viewer'
const fixtures = await (await fetch('/preview-fixtures.json')).json()
const blocked = async () => { throw new Error('Dữ liệu mẫu chỉ đọc: chưa lưu hoặc xuất dữ liệu.') }
// Override every API entry before rendering. No credentials or production requests.
for (const key of Object.keys(veraApi)) veraApi[key] = blocked
veraApi.liveTour = async () => structuredClone(fixtures[viewer ? 'viewer' : 'admin'])
sessionStorage.removeItem('vera-live-tour-cache:preview-only')
const user = { employee_username: 'preview-only', role: viewer ? 'staff' : 'admin', permissions: {} }
createRoot(document.getElementById('root')).render(<React.StrictMode>
  <div className="topbar"><strong>LIVE TOUR · DỮ LIỆU MẪU CHỈ ĐỌC</strong></div>
  <main className="main-content"><LiveTourPage user={user}/></main>
</React.StrictMode>)
