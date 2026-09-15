# AI 群聊室

多人同一房间聊天，AI 模型（OpenAI 兼容 API，如 llama-swap）作为群成员。零依赖，Python 3 标准库。

- `@模型名` 或 `@AI` 召唤某个模型回复；可开启"不 @ 也自动回复"
- 多个 AI 可同时被 @，各自流式回复；所有人实时看到（SSE）
- 记录保存在 `history.json`，重启不丢

```bash
API_BASE=http://host:8080/v1 API_KEY=xxx ./start.sh 127.0.0.1 666   # <1024 端口自动 sudo
```
