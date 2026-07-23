# 项目启动指南

## 环境要求

- Python >= 3.10（虚拟环境: `backend/.venv`）
- Node.js（路径: `/c/nvm4w/nodejs/node`）

## 启动后端 (FastAPI)

```bash
cd backend
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8021 --reload
```

后端运行在: **http://127.0.0.1:8021**

## 启动前端 (Vite + Vue 3)

```bash
# 确保 Node.js 在 PATH 中
export PATH="/c/nvm4w/nodejs:$PATH"
cd frontend
npm run dev
```

前端运行在: **http://localhost:5173**

## 同时启动（一键）

```bash
# 终端1 - 后端
cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8021 --reload

# 终端2 - 前端
export PATH="/c/nvm4w/nodejs:$PATH" && cd frontend && npm run dev
```

## 访问

浏览器打开: **http://localhost:5173**

前端 Vite 已配置代理，`/api` 请求自动转发到后端 8021 端口，无需额外配置。
