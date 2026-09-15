# AI 群聊室（十个 AI 群友）

多人同一房间聊天，AI 模型（OpenAI 兼容 API，如 llama-swap）作为群成员。零依赖，Python 3 标准库。

- 十个人设不同的 AI 群友，都跑在同一个模型上（`MODEL` 环境变量，默认 Qwen3.8-27B），回复串行以省显存
- `@名字` 召唤某个群友，`@AI` 随机一个，`@所有人` 全员轮流回复；可开启"不 @ 也自动回复"
- 多个 AI 可同时被 @，各自流式回复；所有人实时看到（SSE）
- 记录保存在 `history.json`，重启不丢

```bash
API_BASE=http://host:8080/v1 API_KEY=xxx ./start.sh 127.0.0.1 666   # <1024 端口自动 sudo
```
