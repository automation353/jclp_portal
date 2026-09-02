// Single source of truth for where each role lands after signing in
// (Change instruction 1 — role-based views).
//
// Ops user      → straight to /operations
// OEM Sales user → straight to /oem-sales
// Super Admin / Management / anyone else → the full Departments launcher.

export function homeRouteFor(user) {
  if (!user) return '/login'
  if (user.role === 'super_admin') return '/departments'
  const dept = user.department || ''
  if (dept === 'Operations') return '/operations'
  if (dept === 'OEM Sales') return '/oem-sales'
  return '/departments'
}
