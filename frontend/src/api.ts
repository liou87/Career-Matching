import axios, { type InternalAxiosRequestConfig } from "axios";

// 线上前后端同域，本地由 Vite 把 /api 代理到后端（见 vite.config.ts）
const api = axios.create({ baseURL: "/api" });

// 后端配了 ACCESS_TOKEN 时，所有请求要带口令。口令存在浏览器本地，
// 第一次收到 401 时弹框询问，输入后自动重试原请求。
const TOKEN_KEY = "access_token";

function readToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

function saveToken(token: string) {
  try { localStorage.setItem(TOKEN_KEY, token); } catch { /* 隐私模式下存不了，只在本次会话有效 */ }
}

let memoryToken: string | null = null;
// 页面加载时往往并发好几个请求，共用一次弹框
let asking: Promise<string | null> | null = null;

function askToken(): Promise<string | null> {
  asking ??= Promise.resolve().then(() => {
    const t = window.prompt("请输入访问口令")?.trim() || null;
    if (t) { memoryToken = t; saveToken(t); }
    asking = null;
    return t;
  });
  return asking;
}

api.interceptors.request.use(config => {
  const token = memoryToken ?? readToken();
  // 请求头只能放 ASCII，编码后口令可以含中文，后端会解码
  if (token) config.headers["X-Access-Token"] = encodeURIComponent(token);
  return config;
});

api.interceptors.response.use(undefined, async error => {
  const config = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
  if (error.response?.status === 401 && config && !config._retried) {
    const sentToken = config.headers["X-Access-Token"];
    // 并发请求里别的请求已经拿到新口令，直接用新口令重试，不再弹框
    const current = memoryToken ?? readToken();
    const token = current && encodeURIComponent(current) !== sentToken ? current : await askToken();
    if (token) {
      config._retried = true;
      return api(config);
    }
  }
  return Promise.reject(error);
});

/**
 * 读取 SSE 流式接口（AI 助手）。axios 在浏览器里拿不到流式响应体，这里用 fetch，
 * 口令和 401 重试的规则与上面一致。每解析出一个事件就回调一次。
 */
export async function streamPost<E>(path: string, body: unknown, onEvent: (event: E) => void): Promise<void> {
  const send = (token: string | null) => fetch(`/api${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-Access-Token": encodeURIComponent(token) } : {}),
    },
    body: JSON.stringify(body),
  });

  let res = await send(memoryToken ?? readToken());
  if (res.status === 401) {
    const token = await askToken();
    if (!token) throw new Error("需要访问口令");
    res = await send(token);
  }
  if (!res.ok || !res.body) {
    const detail = await res.json().then(d => d.detail).catch(() => null);
    throw new Error(detail || `请求失败（${res.status}）`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // 事件之间用空行分隔，最后一段可能还没收完，留到下一轮
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.split("\n").find(l => l.startsWith("data: "));
      if (line) onEvent(JSON.parse(line.slice(6)) as E);
    }
  }
}

export default api;
