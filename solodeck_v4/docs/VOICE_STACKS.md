# SoloDeck v4 — Voice Stack Selection

SoloDeck 语音层 **不替换** v4 分析内核：STT 进 `/api/v4/chat`，TTS 读 verified 行动卡片摘要。

## 三档栈对照

| 栈 ID | 组件 | 延迟目标 | 许可证 | 适用 |
|---|---|---|---|---|
| `livekit` | LiveKit + Deepgram + GPT-4o + Cartesia | **350-500 ms** | 商用 API | 上线 Demo、SIP 电话 |
| `pipecat` | Pipecat + Whisper-streaming + Kokoro | **500-800 ms** | 大体开源 | DIY、自托管、插话控制 |
| `edge` | Whisper.cpp + llama.cpp + Kokoro-ONNX | **离线** | 开源 | 隐私、边缘、数据不出设备 |

## 架构（统一）

```text
Mic → VAD → STT → [confidence gate] → SoloDeck v4 (/api/v4/chat)
     → TTS (读 action card 摘要) → Speaker
     ↑ UPSTREAM cancel (barge-in)
```

## API

```bash
# 列出三档栈与延迟预算
curl http://localhost:8000/api/v4/voice/stacks

# 模拟一轮（文本代替音频，走 v4 多轮）
curl -X POST http://localhost:8000/api/v4/voice/turn \
  -H 'Content-Type: application/json' \
  -d '{"transcript":"小红书痛点标题咨询更多吗","stack":"livekit","session_id":"..."}'
```

## 环境变量（按栈）

**livekit**: `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `DEEPGRAM_API_KEY`, `OPENAI_API_KEY`, `CARTESIA_API_KEY`

**pipecat**: `OPENAI_API_KEY`（+ 自托管 Whisper/Kokoro 路径）

**edge**: 无云端 key；本地 ONNX / llama.cpp 权重

## 与 SoloDeck 分工

| 层 | 负责 |
|---|---|
| 语音 I/O | VAD / STT / TTS / WebRTC |
| 多轮 + 工具 | SoloDeck v4 `run_v4_agent` |
| 数字结论 | v3 Python Skills（LLM 不编数字） |
| 风险因果 | v4 risk_router deep_path + PostWriter |

默认推荐：**先 pipecat 栈联调**，验证通过后再切 **livekit** 压延迟；**edge** 仅在有隐私硬约束时启用。
