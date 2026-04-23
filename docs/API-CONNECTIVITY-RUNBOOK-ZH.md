# LLM API 连通性排障手册（StoryVerse）

更新时间：2026-04-22  
适用范围：`frontend` / `api` / `worker` 的聊天、技能抽取、RAG 相关 LLM 调用

---

## 1. 先记住结论

这类问题不要只看前端提示 `LLM失败: llm_unreachable_or_failed`，它只是后端兜底文案。  
真实问题通常在以下三类里：

1. 代理链路错误（容器里访问不到宿主机代理）。
2. 上游 TLS 握手失败（容器到目标域名直连异常）。
3. 返回体/响应头不一致导致解码失败（例如 `content-encoding: gzip` 但 body 不是 gzip）。

---

## 2. 本次事故的真实根因（避免重复踩坑）

本次出现“明明有 key，但聊天始终失败”的组合问题是：

1. 容器直连 `https://open.xiaojingai.com` 出现 `SSLEOFError`（仅该目标异常，其他 HTTPS 正常）。
2. 改为宿主机中继后，初版中继响应头处理不正确，触发了后端 `ContentDecodingError`。
3. 于是 `/api/chat` 落入 fallback，前端显示 `llm_unreachable_or_failed`。

---

## 3. 标准诊断流程（先快后细）

### 步骤 A：看容器是否真的起来

```powershell
docker compose ps
curl.exe -s http://localhost:8000/api/healthz
```

### 步骤 B：看容器里 LLM 配置是否正确

```powershell
docker compose exec api sh -lc "printenv | grep -E '^OPENAI_'"
```

重点检查：

1. `OPENAI_BASE_URL`
2. `OPENAI_API_KEY`
3. `OPENAI_MODEL`

### 步骤 C：从容器内做最小连通性测试

```powershell
docker compose exec api python -c "import requests; s=requests.Session(); s.trust_env=False; r=s.get('https://example.com',timeout=10); print(r.status_code)"
```

如果公网可达，再测目标 API：

```powershell
docker compose exec api python -c "import requests; s=requests.Session(); s.trust_env=False; print(s.get('https://open.xiaojingai.com/v1/models',timeout=12).status_code)"
```

### 步骤 D：用后端自检函数确认最终链路

```powershell
docker compose exec api python -c "from app.services.llm_chat import check_llm_connectivity; print(check_llm_connectivity())"
```

---

## 4. 代理策略（项目默认）

### 目标策略

容器不走 Clash，不读系统代理环境变量，优先直连。

### 当前项目已做

1. `docker-compose.yml` 中 `api/worker` 设定：
   - `HTTP_PROXY=`
   - `HTTPS_PROXY=`
   - `http_proxy=`
   - `https_proxy=`
   - `ALL_PROXY=`
   - `all_proxy=`
2. 代码层强制：
   - `session.trust_env = False`（`requests`）

---

## 5. 当“容器直连目标域名失败”时的 fallback

如果出现“容器访问目标域名 TLS 异常，但宿主机可访问”，使用宿主机中继：

1. 启动中继：

```powershell
python D:\Code\26workpre\agent\tools\llm_relay.py
```

2. `.env` 使用：

```env
OPENAI_BASE_URL=http://host.docker.internal:8787/v1
OPENAI_MODEL=gpt-4o
OPENAI_API_KEY=你的key
```

3. 重启服务：

```powershell
docker compose restart api worker
```

---

## 6. 本次修复的关键代码改动

### 中继脚本

新增：`tools/llm_relay.py`

要点：

1. 只转发到固定上游，不做开放代理。
2. 请求侧 `trust_env=False`，避免受宿主机坏代理环境影响。
3. 响应头移除 `content-encoding`，避免下游二次解压错误。

### 后端请求头兜底

在以下文件中加入 `Accept-Encoding: identity`，规避上游/中继压缩异常：

1. `backend/app/services/llm_chat.py`
2. `backend/app/services/llm_extract.py`

---

## 7. 验证“真的修好了”

### 验证 1：后端直接角色回复函数

```powershell
docker compose exec api python -c "from app.services.llm_chat import request_roleplay_completion; print(request_roleplay_completion(role_name='Narrator',role_style='客观叙述',persona_state='无',session_memory='无',user_message='你好',chapter_index=1,evidence_snippets=['证据'])[:120])"
```

### 验证 2：真实接口 `/api/chat`

```powershell
$body = '{"book_id":"<BOOK_ID>","role_name":"Narrator","message":"我有点难受","chapter_index":21}'
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/chat" -ContentType "application/json" -Body $body
```

通过标准：

1. `llm_used = true`
2. `llm_error = ""`

---

## 8. 快速故障对照表

### 情况 A：`ProxyError` + `127.0.0.1:9`

说明：宿主机环境变量里有坏代理。  
处理：容器继续 `trust_env=False`，且中继进程也要 `trust_env=False`。

### 情况 B：容器 `SSLEOFError`，宿主机可通

说明：容器到特定域名 TLS 链路异常。  
处理：走 `host.docker.internal` 中继。

### 情况 C：`ContentDecodingError`（gzip）

说明：响应头与 body 编码不一致。  
处理：

1. 中继移除 `content-encoding`。
2. 后端加 `Accept-Encoding: identity`。

---

## 9. 建议的防回归动作

1. 把“启动中继 + 启动 compose”做成一个 `start.ps1` 脚本。
2. 在后端加 `/api/llm/healthz`，启动后自动探测并在前端显示“LLM可用/不可用”。
3. 发生 `llm_unreachable_or_failed` 时，把异常原因写入日志（不要只返回统一文案）。

---

## 10. 一句话版本（给未来的自己）

看到 `llm_unreachable_or_failed` 时，先别猜。  
按“容器环境变量 -> 容器最小连通 -> 后端自检 -> 中继回退 -> gzip 头校验”这条线查，10 分钟内能定位。

