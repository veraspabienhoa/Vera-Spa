import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import EmployeeProfileLiveEnhancer from './components/EmployeeProfileLiveEnhancer.jsx'
import { startPurchaseReconcileAlertWatcher } from './lib/purchaseReconcileAlerts'
import { registerVeraServiceWorker } from './lib/pushNotifications'
import { startEmployeeProfileUxEnhancements } from './lib/employeeProfileUx'
import { startEmployeeCccdFieldExtract } from './lib/employeeCccdFieldExtract'
import { startEmployeeCccdTabViewer } from './lib/employeeCccdTabViewer'
import './styles.css'
import './visibility-cleanup.css'

void registerVeraServiceWorker().catch(() => {})
startPurchaseReconcileAlertWatcher()
startEmployeeProfileUxEnhancements()
startEmployeeCccdFieldExtract()
startEmployeeCccdTabViewer()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <EmployeeProfileLiveEnhancer />
    <App />
  </React.StrictMode>,
)
