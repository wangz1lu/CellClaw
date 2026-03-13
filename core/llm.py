"""
OmicsClaw LLM Client — Native Function Calling
================================================
Uses OpenAI-compatible native function calling (tools parameter),
NOT prompt-engineering hacks. DeepSeek, OpenAI, Qwen all support this.

Native function calling:
  - Model outputs {"tool_calls": [...]} in the assistant message
  - We append {"role": "tool", "tool_call_id": ..., "content": result}
  - Model continues planning based on results
  - This is what the model was fine-tuned for — 10x better multi-step reasoning

Env vars:
    OMICS_LLM_BASE_URL   — API base URL (default: https://api.deepseek.com/v1)
    OMICS_LLM_API_KEY    — API key
    OMICS_LLM_MODEL      — Model name (default: deepseek-chat)
    OMICS_LLM_MAX_TOKENS — Max response tokens (default: 4096)
    OMICS_LLM_PROXY      — HTTP proxy
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional, Callable, Awaitable, Any

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL  = "https://api.deepseek.com/v1"
_DEFAULT_MODEL     = "deepseek-chat"
_DEFAULT_MAX_TOKENS = 8192
_DEFAULT_TIMEOUT   = 120

# ── Tool Schemas (OpenAI function calling format) ─────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "在远程服务器执行 bash 命令。用于文件操作、查看目录、运行脚本、管理 conda 环境、提交 SLURM 任务等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {
                        "type": "string",
                        "description": "要执行的 bash 命令。可用 && 连接多个命令一次执行。"
                    }
                },
                "required": ["cmd"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "python",
            "description": "在指定 conda 环境中执行 Python 代码片段。用于数据探索、快速计算、调用 scanpy/seurat 等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的 Python 代码"
                    },
                    "conda_env": {
                        "type": "string",
                        "description": "conda 环境名称，默认使用当前激活的环境"
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取远程服务器上的文件内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的绝对或相对路径"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "在远程服务器上创建或覆盖写入文件。用于上传R脚本、Python脚本、配置文件等。必须同时提供 path 和 content 两个参数，缺一不可。path 应使用当前工作目录（见会话上下文中的'当前工作目录'），例如 path='/sdd/bgi/wangzilu/04.OmicsClaw/analyze.R'",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "远程服务器上的完整文件路径。使用当前工作目录作为基础，例如：{workdir}/analyze.R。如不确定，直接用 /tmp/omics_script.R"
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入文件的完整内容，例如完整的R脚本或Python脚本代码"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出远程服务器目录的内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径，默认为当前工作目录"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill",
            "description": "读取本地 Skill 知识库（SKILL.md）或参考模板。在执行生信分析前必须先读取相关 Skill 了解标准流程。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_id": {
                        "type": "string",
                        "description": "Skill 的 ID，如 ccc_cellchat。留空则列出所有可用 Skill。"
                    },
                    "template": {
                        "type": "string",
                        "description": "（可选）参考模板文件名，如 01_single_dataset_CCC.R。不提供则读取完整知识库 SKILL.md。"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "将重要信息永久写入用户的长期记忆。用于记录项目信息、分析步骤、解决方案、用户偏好等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "要记录的内容，简洁明了"
                    },
                    "section": {
                        "type": "string",
                        "description": "（可选）分类标题，如 '项目信息'、'分析流程'、'踩坑记录'"
                    }
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "switch_env",
            "description": "切换当前 conda 分析环境。当用户说'切换到xxx环境'、'用R-4.3.3分析'、'换个环境'等，调用此工具更新会话状态。之后所有命令都会在新环境中执行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "env_name": {
                        "type": "string",
                        "description": "conda 环境名称，如 R-4.3.3、scanpy、pytorch_env"
                    }
                },
                "required": ["env_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_job",
            "description": "将已写好的脚本文件提交为后台长任务（nohup）。适合耗时较长的生信分析（>30秒）。提交后立即返回任务ID，用户可用 /job status 查看进度。**写好脚本后必须用这个工具提交，不要用 shell 工具直接跑脚本。**",
            "parameters": {
                "type": "object",
                "properties": {
                    "script_path": {
                        "type": "string",
                        "description": "要执行的脚本绝对路径，如 /data/analyze.R 或 /data/run.py"
                    },
                    "description": {
                        "type": "string",
                        "description": "任务描述，用于展示给用户，如 'CellChat F7.rds 可视化分析'"
                    }
                },
                "required": ["script_path", "description"]
            }
        }
    }
]

# ── System Prompt (lean — no tool descriptions since they're in schemas) ───

BASE_SYSTEM_PROMPT = """你是 OmicsClaw 🧬，一名专业的 AI 生物信息学工程师，驻扎在 Discord 中。

你可以通过工具直接操控远程 Linux 服务器（HPC/工作站），执行真实命令、读写文件、运行分析。

## 工作原则
- 直接行动，不描述步骤——用户要"分析数据"，就真的去执行，不要说"你可以用xxx命令"
- 遇到生信分析任务，先调用 read_skill 了解标准流程，再根据用户实际数据编写定制代码
- 多步任务按顺序执行：探索数据 → 理解结构 → 编写脚本 → 执行 → 解读结果
- 出错时分析原因并自动修复，不要中途放弃
- 重要信息用 remember 工具记录，方便下次继续
- 回复用用户相同语言（中文/英文）
- 最终回复要简洁，重点说结论和用户需要知道的内容

## ⚠️ 路径规则 — 最高优先级，任何情况不得违反
- **所有文件操作必须使用绝对路径**，禁止使用相对路径（禁止 `./file.rds`、`../data`、`'F7.rds'`）
- 会话上下文中的"当前工作目录"是你的路径基准，每次引用文件都要拼完整路径
  - 示例：工作目录是 `/sdd/bgi/wangzilu/04.OmicsClaw`，文件是 `F7.rds` → 必须写 `/sdd/bgi/wangzilu/04.OmicsClaw/F7.rds`
- 写R/Python脚本时，脚本内部**第一行就要 `setwd('/绝对路径')`**，所有 readRDS/read.csv/write.csv 等都用绝对路径
- 写 shell 命令时，**cd 到绝对路径**再执行，不依赖当前目录
- 如果不确定某个文件的绝对路径，先用 `shell` 执行 `find /path -name 'filename' 2>/dev/null` 找到后再操作
- **检查清单**（写完脚本后自我检查）：脚本里有没有任何不含 `/` 开头的文件路径？有就改掉

## ⚠️ 任务执行规则 — 长任务必须走 submit_job
- **写完脚本后**（write_file 成功），必须调用 `submit_job` 提交后台执行，**禁止** 用 `shell` 工具直接跑脚本
- `submit_job` 会用 nohup 后台运行，立即返回任务 ID
- 用户可用 `/job status <id>` 查看进度，`/job log <id>` 看实时日志
- 只有极短的命令（<5秒）才可以用 `shell` 工具直接执行

## ⚠️ Conda 环境重要规则
- 系统已自动将命令包装在正确的 conda 环境中运行，**不要在命令里写 `conda activate` 或 `source activate`**
- 直接写 `Rscript -e "..."` 或 `python script.py`，不要加任何环境激活前缀
- 错误示例：`conda activate R-4.3.3 && Rscript ...`（会导致环境错乱）
- 正确示例：`Rscript -e "library(Seurat); ..."`
- **R脚本中禁止写 `.libPaths()`**，系统已自动设置 `R_LIBS_SITE` 环境变量指向正确的 conda 环境包路径

## ⚠️ write_file 工具使用规则
- 调用 write_file 时**必须同时提供 path 和 content 两个参数**
- path: 完整文件路径，如 `/sdd/bgi/wangzilu/04.OmicsClaw/analyze.R`
- content: 完整的脚本内容
- **不能只调用 write_file 而不带参数** — 这会导致任务失败
- 如果脚本内容很长，直接写完整内容，不要分批
"""


def _build_multimodal_content(text: str, image_paths: list[str]) -> list[dict]:
    """
    Build an OpenAI-compatible multimodal content list.
    Works with any vision-capable model (GPT-4o, Gemini via OpenAI compat, Qwen-VL, etc.)

    Format:
        [
            {"type": "text", "text": "..."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
            ...
        ]
    """
    import base64, mimetypes
    content: list[dict] = [{"type": "text", "text": text}]
    for path in image_paths:
        try:
            mime = mimetypes.guess_type(path)[0] or "image/png"
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"}
            })
            logger.debug(f"Attached image: {path} ({mime})")
        except Exception as e:
            logger.warning(f"Failed to encode image {path}: {e}")
    return content


def _recover_truncated_json(raw: str) -> dict:
    """
    Try to recover a truncated JSON string from DeepSeek API.
    DeepSeek sometimes cuts off the arguments mid-string when content is long.
    Strategy: close any open string, then close open braces.
    """
    if not raw or not raw.strip().startswith("{"):
        return {}
    s = raw.rstrip()
    # Count unclosed quotes (naive but works for simple cases)
    # Close open string: find last unescaped " position
    in_string = False
    escape_next = False
    for ch in s:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\':
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
    if in_string:
        s += '"'  # close the open string
    # Close open braces
    depth = 0
    for ch in s:
        if ch == '{': depth += 1
        elif ch == '}': depth -= 1
    s += '}' * max(0, depth)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {}


class ToolCall:
    """Represents a single tool call from native function calling."""
    def __init__(self, call_id: str, name: str, arguments: dict):
        self.call_id   = call_id
        self.name      = name       # function name
        self.arguments = arguments  # parsed dict

    # For backwards compatibility
    @property
    def tool(self):
        return self.name

    @property
    def params(self):
        return self.arguments

    @classmethod
    def from_api(cls, tc: dict) -> "ToolCall":
        """Parse from OpenAI API tool_call object."""
        fn   = tc.get("function", {})
        name = fn.get("name", "")
        raw  = fn.get("arguments", "{}")
        try:
            args = json.loads(raw)
        except json.JSONDecodeError:
            # DeepSeek sometimes truncates long arguments mid-string.
            # Attempt recovery: close any open string and braces.
            args = _recover_truncated_json(raw)
            if args:
                logger.warning(f"  [!] Recovered truncated JSON for {name}: {len(raw)} chars")
            else:
                args = {}
                logger.warning(f"  [!] Could not recover JSON for {name}, raw={raw[:200]}")
        return cls(
            call_id   = tc.get("id", ""),
            name      = name,
            arguments = args,
        )


# Type alias for the tool executor callback
ToolExecutor = Callable[[ToolCall], Awaitable[str]]


class LLMClient:
    """
    Async OpenAI-compatible LLM client with native Function Calling.
    Supports any OpenAI-compatible API (DeepSeek, OpenAI, Kimi, Qwen).
    """

    def __init__(
        self,
        base_url:     Optional[str] = None,
        api_key:      Optional[str] = None,
        model:        Optional[str] = None,
        max_tokens:   Optional[int] = None,
        proxy:        Optional[str] = None,
        project_root: Optional[str] = None,
        skills_dir:   Optional[str] = None,
    ):
        self.base_url   = (base_url   or os.environ.get("OMICS_LLM_BASE_URL",   _DEFAULT_BASE_URL)).rstrip("/")
        self.api_key    = (api_key    or os.environ.get("OMICS_LLM_API_KEY",    "")).strip()
        self.model      = (model      or os.environ.get("OMICS_LLM_MODEL",      _DEFAULT_MODEL)).strip()
        self.max_tokens = int(max_tokens or os.environ.get("OMICS_LLM_MAX_TOKENS", _DEFAULT_MAX_TOKENS))
        self.proxy      = (proxy or os.environ.get("OMICS_LLM_PROXY")
                           or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy"))

        _root = project_root or str(Path(__file__).parent.parent)

        from .skills import load_soul, SkillLoader
        self._soul         = load_soul(_root)
        _skills_path       = skills_dir or os.path.join(_root, "skills")
        self._skill_loader = SkillLoader(_skills_path)

        if not self.api_key:
            logger.warning("OMICS_LLM_API_KEY not set — LLM features disabled")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def skill_loader(self):
        return self._skill_loader

    def build_system_prompt(self, session_ctx: Optional[str] = None) -> str:
        """Build system prompt: soul identity + base rules + skills list + session context."""
        parts = []

        # Soul identity (first 400 chars — personality summary)
        if self._soul:
            parts.append(self._soul[:400].strip())

        # Base rules
        parts.append(BASE_SYSTEM_PROMPT)

        # Skills awareness (compact — full content loaded via read_skill tool)
        skill_section = self._skill_loader.build_prompt_section()
        parts.append(skill_section)

        # Runtime context (server, env, path, memory)
        if session_ctx:
            parts.append(f"## 当前会话上下文\n{session_ctx}")

        return "\n\n".join(parts)

    # ── Low-level API call ────────────────────────────────────────────────

    async def _call_api(
        self,
        messages:    list[dict],
        tools:       Optional[list] = None,
        max_tokens:  Optional[int]  = None,
        temperature: float = 0.3,
    ) -> dict:
        """
        Raw API call. Returns the full assistant message dict.
        Raises on HTTP errors.
        """
        if not self.enabled:
            return {"role": "assistant", "content": "[LLM disabled: no API key]"}

        payload: dict[str, Any] = {
            "model":       self.model,
            "messages":    messages,
            "max_tokens":  max_tokens or self.max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"]       = tools
            payload["tool_choice"] = "auto"

        import aiohttp
        import ssl as _ssl

        ssl_ctx   = _ssl._create_unverified_context()
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        timeout   = aiohttp.ClientTimeout(total=_DEFAULT_TIMEOUT)
        headers   = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }
        kwargs: dict = {"headers": headers, "json": payload}
        if self.proxy:
            kwargs["proxy"] = self.proxy

        try:
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.post(f"{self.base_url}/chat/completions", **kwargs) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        logger.error(f"LLM API {resp.status}: {body[:300]}")
                        return {"role": "assistant", "content": f"[LLM error {resp.status}]"}
                    data  = await resp.json()
                    return data["choices"][0]["message"]
        except asyncio.TimeoutError:
            logger.error("LLM API timeout")
            return {"role": "assistant", "content": "[LLM timeout]"}
        except Exception as e:
            logger.exception(f"LLM API error: {e}")
            return {"role": "assistant", "content": f"[LLM error: {e}]"}

    # ── Agent Loop (Native Function Calling) ─────────────────────────────

    async def agent_chat(
        self,
        user_message:  str,
        tool_executor: ToolExecutor,
        session_ctx:   Optional[str]       = None,
        history:       Optional[list[dict]] = None,
        max_rounds:    int = 15,
        images:        Optional[list[str]]  = None,
    ) -> str:
        """
        Multi-turn agent loop using NATIVE function calling.

        The model outputs tool_calls in the assistant message (no text parsing needed).
        We execute each tool and feed results back as tool-role messages.
        Loop continues until model outputs a text-only response (task complete).

        Args:
            user_message:  User's natural language request
            tool_executor: Async callback that executes a ToolCall and returns result string
            session_ctx:   Current session context (server, env, path, memory, skills)
            history:       Recent conversation history (list of message dicts)
            max_rounds:    Max tool call rounds before forced summary
            images:        Local image file paths for vision-capable models
        """
        system = self.build_system_prompt(session_ctx)

        messages: list[dict] = [{"role": "system", "content": system}]

        # Inject recent history (max 6 turns to keep token budget reasonable)
        if history:
            messages.extend(history[-6:])

        # Build user message content — plain text or multimodal (text + images)
        if images:
            user_content = _build_multimodal_content(user_message, images)
        else:
            user_content = user_message
        messages.append({"role": "user", "content": user_content})

        for round_n in range(max_rounds):
            # Call API with tool schemas
            assistant_msg = await self._call_api(messages, tools=TOOL_SCHEMAS)

            content    = assistant_msg.get("content") or ""
            tool_calls = assistant_msg.get("tool_calls") or []

            # No tool calls → final answer
            if not tool_calls:
                return content or "[无响应]"

            # Has tool calls → execute each one
            logger.info(f"[Agent] round={round_n+1} tool_calls={[tc['function']['name'] for tc in tool_calls]}")

            # Append assistant message with tool_calls to history
            messages.append(assistant_msg)

            # Execute all tool calls (sequential)
            job_submitted = False
            for tc_raw in tool_calls:
                tc = ToolCall.from_api(tc_raw)
                raw_args_str = tc_raw.get("function", {}).get("arguments", "")
                logger.info(f"  → {tc.name}({json.dumps(tc.arguments, ensure_ascii=False)[:200]})")
                # Debug: log raw arguments string if parsed result is empty
                if not tc.arguments and raw_args_str and raw_args_str != "{}":
                    logger.warning(f"  [!] arguments parse issue — raw: {raw_args_str[:300]}")

                try:
                    result = await tool_executor(tc)
                except Exception as e:
                    result = f"[Tool error: {e}]"
                    logger.exception(f"Tool execution failed: {tc.name}")

                # Truncate large outputs
                if len(result) > 3000:
                    result = result[:3000] + f"\n...(输出过长，已截断，共{len(result)}字符)"

                logger.info(f"  ← {tc.name}: {result[:100]!r}")

                # Append tool result
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.call_id,
                    "content":      result,
                })

                if tc.name == "submit_job":
                    job_submitted = True

            # submit_job was called → do one final LLM turn to compose reply, then stop immediately
            # This prevents the agent from hanging waiting for the long-running job to finish
            if job_submitted:
                messages.append({
                    "role":    "user",
                    "content": "任务已成功提交后台。请直接告诉用户：任务已提交、任务ID是什么、如何用 /job status 查看进度。不要再调用任何工具。"
                })
                final_msg = await self._call_api(messages)
                return final_msg.get("content") or "✅ 任务已提交后台运行，用 `/job status <id>` 查看进度。"

        # Max rounds reached — ask model to summarize
        messages.append({
            "role":    "user",
            "content": "请根据上面所有工具执行结果，给用户一个完整的总结回复。"
        })
        final_msg = await self._call_api(messages)
        return final_msg.get("content") or "⚠️ 任务已执行，但未能生成最终回复，请查看操作日志。"

    # ── Plain chat (no tools) ─────────────────────────────────────────────

    async def chat(
        self,
        user_message: str,
        system:       Optional[str] = None,
        history:      Optional[list[dict]] = None,
        max_tokens:   Optional[int] = None,
    ) -> str:
        """Simple chat without tool calling (for summarize/explain)."""
        _sys = system or "你是 OmicsClaw，专业生信 AI 助手。回复简洁专业，使用用户相同语言。"
        msgs = [{"role": "system", "content": _sys}]
        if history:
            msgs.extend(history[-4:])
        msgs.append({"role": "user", "content": user_message})
        msg = await self._call_api(msgs, max_tokens=max_tokens)
        return msg.get("content") or ""

    # ── Convenience methods ───────────────────────────────────────────────

    async def summarize_result(self, result: str, task: str) -> str:
        """Summarize a command/analysis result for the user."""
        prompt = f"任务：{task}\n\n执行结果：\n{result[:3000]}\n\n请用中文简洁总结关键发现，重点说明对用户有意义的信息。"
        return await self.chat(prompt)

    async def explain_error(self, error: str, context: str = "") -> str:
        """Explain an error and suggest a fix."""
        prompt = f"执行报错如下：\n{error[:2000]}\n\n上下文：{context[:500]}\n\n请分析错误原因，给出简洁的修复建议。"
        return await self.chat(prompt)


# ── Singleton ─────────────────────────────────────────────────────────────

_instance: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _instance
    if _instance is None:
        _instance = LLMClient()
    return _instance
