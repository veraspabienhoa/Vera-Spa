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
import { startEmployeeProfileCompletionAndIssuerFix } from './lib/employeeProfileCompletionAndIssuerFix'
import { startEmployeeDirectoryUx } from './lib/employeeDirectoryUx'
import { startEmployeeProfileHeaderSaveFix } from './lib/employeeProfileHeaderSaveFix'
import { startEmployeeToolbarRecovery } from './lib/employeeToolbarRecovery'
import { startEmployeeMissingProfileFix } from './lib/employeeMissingProfileFix'
import { startLeaveListDateFilterSync } from './lib/leaveListDateFilterSync'
import { startDepartmentSalaryAdvanceTransportGuard } from './lib/departmentSalaryAdvanceTransportGuard'
import { startDepartmentSalaryAdvanceLedger } from './lib/departmentSalaryAdvanceLedger'
import { startAttendanceTimesoftRefreshGuard } from './lib/attendanceTimesoftRefreshGuard'
import './styles.css'
import './visibility-cleanup.css'

void registerVeraServiceWorker().catch(() => {})
startPurchaseReconcileAlertWatcher()
startEmployeeProfileUxEnhancements()
startEmployeeCccdFieldExtract()
startEmployeeCccdTabViewer()
startEmployeeProfileProductionFix()
startEmployeeProfileSwitchGuard()
startEmployeeProfileCompletionAndIssuerFix()
startEmployeeDirectoryUx()
startEmployeeProfileHeaderSaveFix()
startEmployeeToolbarRecovery()
startEmployeeMissingProfileFix()
startLeaveListDateFilterSync()
startDepartmentSalaryAdvanceTransportGuard()
startDepartmentSalaryAdvanceLedger()
startAttendanceTimesoftRefreshGuard()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <EmployeeProfileLiveEnhancer />
    <App />
  </React.StrictMode>,
)
