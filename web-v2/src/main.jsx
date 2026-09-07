import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import EmployeeProfileLiveEnhancer from './components/EmployeeProfileLiveEnhancer.jsx'
import { startPurchaseReconcileAlertWatcher } from './lib/purchaseReconcileAlerts'
import { registerVeraServiceWorker } from './lib/pushNotifications'
import { startEmployeeProfileUxEnhancements } from './lib/employeeProfileUx'
import { startEmployeeCccdFieldExtract } from './lib/employeeCccdFieldExtract'
import { startEmployeeCccdTabViewer } from './lib/employeeCccdTabViewer'
import { startEmployeeProfileProductionFix } from './lib/employeeProfileProductionFix'
import { startEmployeeProfileSwitchGuard } from './lib/employeeProfileSwitchGuard'
import './styles.css'
import './visibility-cleanup.css'

void registerVeraServiceWorker().catch(() => {})
startPurchaseReconcileAlertWatcher()
startEmployeeProfileUxEnhancements()
startEmployeeCccdFieldExtract()
startEmployeeCccdTabViewer()
startEmployeeProfileProductionFix()
startEmployeeProfileSwitchGuard()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <EmployeeProfileLiveEnhancer />
    <App />
  </React.StrictMode>,
)
