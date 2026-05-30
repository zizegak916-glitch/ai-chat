# AI 多模型聊天面板

手机浏览器友好的 AI 聊天界面，支持多个模型 Provider 切换。

## 启动

```bash
python3 app.py 8082
```

访问 `http://localhost:8082`

## 功能

- 🔄 多模型切换（Xiaomi MiMo、DeepSeek、Qwen、自定义）
- 💬 多对话管理
- ✍️ Markdown 渲染 + 代码高亮
- 🔑 API Key 存储在浏览器本地（不上传服务器）
- 📱 移动端深色主题

## 数据存储

所有数据存在浏览器 `localStorage`，无需后端数据库。

API Key 只在客户端使用，Flask 后端仅负责提供静态页面。
