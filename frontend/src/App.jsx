import { Navigate, Route, Routes } from 'react-router-dom'
import RequireAuth from './components/RequireAuth'
import RequireSuperAdmin from './components/RequireSuperAdmin'
import Departments from './screens/Departments'
import EBQ from './screens/EBQ'
import Landing from './screens/Landing'
import Login from './screens/Login'
import MtoMts from './screens/MtoMts'
import MtoMtsChanges from './screens/MtoMtsChanges'
import OEMSales from './screens/OEMSales'
import Operations from './screens/Operations'
import PPC from './screens/PPC'
import PPCDataBrowse from './screens/PPCDataBrowse'
import PPCDataDemand from './screens/PPCDataDemand'
import PPCDataFeeds from './screens/PPCDataFeeds'
import PPCDataHub from './screens/PPCDataHub'
import PPCDataMPS from './screens/PPCDataMPS'
import PPCDataR3SS from './screens/PPCDataR3SS'
import PPCDataUpload from './screens/PPCDataUpload'
import PPCFeasibility from './screens/PPCFeasibility'
import PPCForecast from './screens/PPCForecast'
import PPCMaterial from './screens/PPCMaterial'
import PPCProduction from './screens/PPCProduction'
import Purchase from './screens/Purchase'
import PurchaseDashboard from './screens/PurchaseDashboard'
import PurchasePlanning from './screens/PurchasePlanning'
import RMRequirement from './screens/RMRequirement'
import SAndOP from './screens/SAndOP'
import SopDemandSupply from './screens/SopDemandSupply'
import SopUpload from './screens/SopUpload'
import SuperAdmin from './screens/SuperAdmin'
import SuperAdminActivity from './screens/SuperAdminActivity'
import SuperAdminUserForm from './screens/SuperAdminUserForm'
import SuperAdminUsers from './screens/SuperAdminUsers'
import UploadData from './screens/UploadData'

export default function App() {
  return (
    <>
      <Routes>
        {/* Public: organisation launcher, then sign-in. */}
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />

        {/* Everything past sign-in. */}
        <Route path="/departments" element={<RequireAuth><Departments /></RequireAuth>} />
        <Route path="/purchase" element={<RequireAuth><Purchase /></RequireAuth>} />
        <Route path="/purchase/rm-requirement" element={<RequireAuth><RMRequirement /></RequireAuth>} />
        <Route path="/purchase/ebq" element={<RequireAuth><EBQ /></RequireAuth>} />
        <Route path="/purchase/purchase-planning" element={<RequireAuth><PurchasePlanning /></RequireAuth>} />
        <Route path="/purchase/upload" element={<RequireAuth><UploadData /></RequireAuth>} />
        <Route path="/purchase/dashboard" element={<RequireAuth><PurchaseDashboard /></RequireAuth>} />

        <Route path="/operations" element={<RequireAuth><Operations /></RequireAuth>} />
        <Route path="/oem-sales" element={<RequireAuth><OEMSales /></RequireAuth>} />
        <Route path="/s-and-op" element={<RequireAuth><SAndOP /></RequireAuth>} />
        <Route path="/s-and-op/demand-supply" element={<RequireAuth><SopDemandSupply /></RequireAuth>} />
        <Route path="/s-and-op/demand-supply/upload" element={<RequireAuth><SopUpload /></RequireAuth>} />
        <Route path="/ppc" element={<RequireAuth><PPC /></RequireAuth>} />
        <Route path="/ppc-data" element={<RequireAuth><PPCDataHub /></RequireAuth>} />
        <Route path="/ppc-data/upload" element={<RequireAuth><PPCDataUpload /></RequireAuth>} />
        <Route path="/ppc-data/browse" element={<RequireAuth><PPCDataBrowse /></RequireAuth>} />
        <Route path="/ppc-data/feeds" element={<RequireAuth><PPCDataFeeds /></RequireAuth>} />
        <Route path="/ppc-data/demand" element={<RequireAuth><PPCDataDemand /></RequireAuth>} />
        <Route path="/ppc-data/mps" element={<RequireAuth><PPCDataMPS /></RequireAuth>} />
        <Route path="/ppc-data/r3ss" element={<RequireAuth><PPCDataR3SS /></RequireAuth>} />
        <Route path="/ppc-data/feasibility" element={<RequireAuth><PPCFeasibility /></RequireAuth>} />
        <Route path="/ppc-data/release/:id" element={<RequireAuth><PPCFeasibility /></RequireAuth>} />
        <Route path="/ppc-data/material" element={<RequireAuth><PPCMaterial /></RequireAuth>} />
        <Route path="/ppc-data/production" element={<RequireAuth><PPCProduction /></RequireAuth>} />
        <Route path="/ppc-forecast" element={<RequireAuth><PPCForecast /></RequireAuth>} />
        <Route path="/mto-mts" element={<RequireAuth><MtoMts /></RequireAuth>} />
        <Route path="/mto-mts/changes" element={<RequireAuth><MtoMtsChanges /></RequireAuth>} />

        {/* Super Admin panel — only super_admin role can access. */}
        <Route path="/super-admin" element={<RequireSuperAdmin><SuperAdmin /></RequireSuperAdmin>} />
        <Route path="/super-admin/users" element={<RequireSuperAdmin><SuperAdminUsers /></RequireSuperAdmin>} />
        <Route path="/super-admin/users/new" element={<RequireSuperAdmin><SuperAdminUserForm /></RequireSuperAdmin>} />
        <Route path="/super-admin/users/:id" element={<RequireSuperAdmin><SuperAdminUserForm /></RequireSuperAdmin>} />
        <Route path="/super-admin/activity" element={<RequireSuperAdmin><SuperAdminActivity /></RequireSuperAdmin>} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <div className="footer-note">
        JCPL Enterprise Portal · Purchase modules live on Django · other departments coming soon
      </div>
    </>
  )
}
