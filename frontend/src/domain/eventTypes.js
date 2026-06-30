export function isTopologyStatusEvent(eventType, attributes = {}) {
  const status = eventStatusFromType(eventType);
  if (!status) {
    return false;
  }
  return hasInterfaceStatusHint(eventType, attributes);
}

function eventStatusFromType(eventType) {
  const normalized = String(eventType || '').toUpperCase();
  if (['_UP', '_RECOVERED', '_RECOVERY', '_RESTORED', '_CLEAR', '_CLEARED'].some((suffix) => normalized.endsWith(suffix))) {
    return 'up';
  }
  if (['_DOWN', '_FAILED', '_FAIL', '_LOST'].some((suffix) => normalized.endsWith(suffix))) {
    return 'down';
  }
  return null;
}

function hasInterfaceStatusHint(eventType, attributes) {
  if (['if_name', 'if_index', 'interface', 'if_oper_status', 'oper_status'].some((key) => attributes?.[key])) {
    return true;
  }
  const normalized = String(eventType || '').toUpperCase();
  return normalized.startsWith('INTERFACE_') || normalized.startsWith('IF_');
}
