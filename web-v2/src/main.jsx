import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { startPurchaseReconcileAlertWatcher } from './lib/purchaseReconcileAlerts'
import { registerVeraServiceWorker } from './lib/pushNotifications'
import './styles.css'

void registerVeraServiceWorker().catch(() => {})
startPurchaseReconcileAlertWatcher()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
