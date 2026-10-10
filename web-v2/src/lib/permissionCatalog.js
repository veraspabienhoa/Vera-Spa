// Keep the Admin editor's effective checks aligned with the API resolver.
// Only policy-v1 date grants add runtime parent checks; unrelated permission
// precedence stays account -> role -> legacy -> role default.
const dateFeaturePattern = /^live_tour_(pending|invoices|reports|history)_date_(all|today|yesterday|week|last_week|month|last_month|custom)$/

export function supportsDateFilterPolicy(source) {
  return source?.date_filter_policy_version === 1
}

export function isDatePermissionFeature(key, source = {}) {
  return Object.hasOwn(source?.date_filter_features || {}, key) || dateFeaturePattern.test(key)
}

export function canEditCatalogFeature(key, source = {}) {
  return !isDatePermissionFeature(key, source) || supportsDateFilterPolicy(source)
}

export function permissionFeatureKeys(source) {
  const pageKeys = (source?.pages || []).flatMap((page) => Object.keys(page?.features || {}))
  return [...new Set(pageKeys.length
    ? pageKeys
    : Object.values(source?.groups || {}).flatMap((items) => Object.keys(items)))].filter((key) => canEditCatalogFeature(key, source))
}

export function catalogFeatureAllowed(key, role, account = '', source = {}) {
  if (!canEditCatalogFeature(key, source)) return false
  if (role === 'admin') return true
  const isDateFeature = Object.hasOwn(source?.date_filter_features || {}, key)
  if (isDateFeature) {
    if (!(source.dependencies?.[key] || []).every((parent) => catalogFeatureAllowed(parent, role, account, source))) return false
    const anyParents = source.date_filter_parent_any?.[key] || []
    if (anyParents.length && !anyParents.some((parent) => catalogFeatureAllowed(parent, role, account, source))) return false
  }
  const accountOverride = source?.account_overrides?.[account] || {}
  const roleOverride = source?.role_overrides?.[role] || {}
  if (Object.hasOwn(accountOverride, key)) return Boolean(accountOverride[key])
  if (Object.hasOwn(roleOverride, key)) return Boolean(roleOverride[key])
  if (isDateFeature) return true
  const legacy = source?.legacy_inheritance?.[key]
  return legacy ? catalogFeatureAllowed(legacy, role, account, source) : (source?.defaults?.[role] || []).includes(key)
}

export function catalogAllowedFeatures(role, account = '', source = {}) {
  return permissionFeatureKeys(source).filter((key) => catalogFeatureAllowed(key, role, account, source))
}

export function hasAnyDateParent(feature, features, source = {}) {
  const parents = source.date_filter_parent_any?.[feature] || []
  return !parents.length || parents.some((parent) => features.includes(parent))
}

// A successful generic permission save is not proof that an older server
// understood date restrictions. Check the write acknowledgement and read-back.
export function datePermissionSaveProblem(result, refreshed) {
  if (!supportsDateFilterPolicy(result)) return 'Máy chủ chưa xác nhận phiên bản quyền lọc ngày 1. Thay đổi có thể đã được lưu nhưng quyền lọc ngày chưa được xác minh. Hãy tải lại sau khi cập nhật máy chủ.'
  if (!refreshed) return 'Máy chủ đã nhận thay đổi nhưng chưa tải lại được phân quyền để xác minh quyền lọc ngày. Hãy Làm mới để kiểm tra.'
  if (!supportsDateFilterPolicy(refreshed)) return 'Phiên bản quyền lọc ngày của máy chủ đã thay đổi. Chưa thể xác minh quyền lọc ngày đã lưu; hãy tải lại sau khi các máy chủ được cập nhật đồng bộ.'
  if (!Number.isInteger(result.revision) || !Number.isInteger(refreshed.revision) || refreshed.revision < result.revision) return 'Dữ liệu phân quyền tải lại chưa xác nhận bản vừa lưu. Hãy Làm mới để kiểm tra quyền lọc ngày.'
  return ''
}
