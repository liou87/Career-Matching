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

export default api;
