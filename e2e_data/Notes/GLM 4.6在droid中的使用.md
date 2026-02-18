---
tags:
  - note
creation date: 2025-12-22 21:17
modification date: Monday 22nd December 2025 21:17:29
owner: area/LLM
---
需要修改`~/.factory/config.json`为
```json
{
  "custom_models": [
    {
      "model_display_name": "GLM 4.6",
      "model": "glm-4.6",
      "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
      "api_key": "4c5f5ccf3b6f4645966f88e63e424073.Y6GsYwT9aL5aWggO",
      "provider": "generic-chat-completion-api",
      "max_tokens": 32000
    }
  ]
}
```