import { readonly, ref } from 'vue';

const alerts = ref([]);
let nextAlertId = 1;

const ALERT_LIFETIME_MS = 6000;

export function useAlerts() {
  function pushAlert(payload) {
    const alert = normalizeAlert(payload);
    alerts.value = [alert, ...alerts.value].slice(0, 4);

    if (alert.autoClose && typeof window !== 'undefined') {
      window.setTimeout(() => dismissAlert(alert.id), alert.durationMs);
    }
    return alert.id;
  }

  function dismissAlert(id) {
    alerts.value = alerts.value.filter((alert) => alert.id !== id);
  }

  function clearAlerts() {
    alerts.value = [];
  }

  return {
    alerts: readonly(alerts),
    pushAlert,
    dismissAlert,
    clearAlerts,
  };
}

export function normalizeErrorAlert(err, fallbackTitle = '操作失败') {
  const rawMessage = normalizeErrorMessage(err);
  const providerError = parseLlmProviderError(rawMessage);

  if (providerError?.code === 'insufficient_quota') {
    return {
      type: 'warning',
      title: '大模型 API 额度不足',
      message: '当前 API Key 没有可用额度或未开通 API 计费。请检查 OpenAI Platform 的 Billing、Usage 和 Project。',
      detail: providerError.message,
      autoClose: false,
    };
  }

  if (rawMessage.includes('HTTP 429')) {
    return {
      type: 'warning',
      title: '大模型请求被限流',
      message: '模型服务返回 429，请检查额度、速率限制或稍后重试。',
      detail: rawMessage,
      autoClose: false,
    };
  }

  if (rawMessage.includes('Large model is not configured')) {
    return {
      type: 'info',
      title: '大模型未配置',
      message: '请在右上角设置弹窗的“模型接入”中填写 Base URL、Model 和 API Key。',
      detail: rawMessage,
    };
  }

  if (rawMessage.includes('Cannot connect to LLM provider')) {
    return {
      type: 'error',
      title: '无法连接大模型服务',
      message: '请检查 Base URL、网络连通性和模型服务地址。',
      detail: rawMessage,
      autoClose: false,
    };
  }

  return {
    type: 'error',
    title: fallbackTitle,
    message: rawMessage,
    autoClose: false,
  };
}

function normalizeAlert(payload) {
  const type = ['success', 'info', 'warning', 'error'].includes(payload?.type) ? payload.type : 'info';
  return {
    id: nextAlertId++,
    type,
    title: payload?.title || defaultTitle(type),
    message: payload?.message || '',
    detail: payload?.detail || '',
    autoClose: payload?.autoClose ?? type !== 'error',
    durationMs: payload?.durationMs || ALERT_LIFETIME_MS,
  };
}

function defaultTitle(type) {
  if (type === 'success') {
    return '操作成功';
  }
  if (type === 'warning') {
    return '需要处理';
  }
  if (type === 'error') {
    return '操作失败';
  }
  return '提示';
}

function normalizeErrorMessage(err) {
  if (!err) {
    return '未知错误';
  }
  const text = err.message || String(err);
  try {
    const parsed = JSON.parse(text);
    return stringifyMessage(parsed.detail || parsed.message || text);
  } catch {
    return stringifyMessage(text);
  }
}

function stringifyMessage(value) {
  if (typeof value === 'string') {
    return value;
  }
  if (value == null) {
    return '未知错误';
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function parseLlmProviderError(message) {
  const marker = 'LLM provider returned HTTP';
  if (!message.includes(marker)) {
    return null;
  }
  const jsonStart = message.indexOf('{');
  if (jsonStart < 0) {
    return null;
  }
  try {
    const payload = JSON.parse(message.slice(jsonStart));
    return payload?.error || null;
  } catch {
    return null;
  }
}
