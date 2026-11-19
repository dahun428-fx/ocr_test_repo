"""Claude Agent SDK로 모델을 부르는 뒷단 (구독 인증).

claude-agent-sdk는 모델을 부르는 PC에만 설치하므로 패키지 의존성에 넣지 않고 실제로 부를 때 가져옵니다.
그래서 이 파일은 CI에서 실행되지 않습니다. 기록 형식은 가짜 뒷단으로 model_route의 테스트가 검사합니다.

API 사용법의 출처 (2026-11-19에 읽음):
  https://code.claude.com/docs/en/agent-sdk/python                    ClaudeAgentOptions, ResultMessage, AssistantMessage
  https://code.claude.com/docs/en/agent-sdk/streaming-vs-single-mode  이미지는 스트리밍 입력으로만 보낼 수 있음
"""
import asyncio
import os
import tempfile

from ocr_harness.common.model_route import ModelBackend, ModelRequest, ModelResult

# SDK가 알려 주는 오류 분류 → 플랫폼 계약의 오류 코드. 표에 없는 값은 UPSTREAM_ERROR로 둡니다.
ERROR_CODES = {
    "authentication_failed": "UNAUTHENTICATED",
    "billing_error": "FORBIDDEN",
    "rate_limit": "RATE_LIMITED",
    "invalid_request": "VALIDATION_ERROR",
    "server_error": "UPSTREAM_UNAVAILABLE",
}
# 이 환경 변수가 있으면 SDK가 구독이 아니라 API 키로 인증합니다.
API_KEY_VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def _usage(counts: dict, names: tuple[str, str, str, str]) -> dict:
    """SDK의 토큰 수 사전 → ModelResult의 토큰 인자. 없는 값은 0입니다 (캐시를 쓰지 않은 호출)."""
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_write_input_tokens")
    return {key: int(counts.get(name) or 0) for key, name in zip(keys, names)}


class AgentSdkBackend(ModelBackend):
    """Claude Code에 로그인된 구독으로 모델을 한 번 부릅니다. 도구 없이, 한 턴만."""

    auth_route = "subscription_oauth"

    def __init__(self):
        # 구독 실행과 API 키 실행은 비용의 뜻이 달라 결과를 섞지 않기로 했습니다. 키가 잡혀 있으면 시작하지 않습니다.
        found = [name for name in API_KEY_VARIABLES if os.environ.get(name)]
        if found:
            raise RuntimeError(f"구독 인증 실행인데 {', '.join(found)}가 설정되어 있습니다. 지우고 다시 실행하세요.")

    def call(self, request: ModelRequest) -> ModelResult:
        return asyncio.run(self._call(request))

    async def _call(self, request: ModelRequest) -> ModelResult:
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, TextBlock

        async def messages():
            # 이미지가 든 입력은 글자열 프롬프트로는 보낼 수 없고 메시지 사전을 흘려보내야 합니다.
            yield {"type": "user", "message": {"role": "user", "content": request.content}}

        # 빈 폴더에서 실행하고 설정 파일을 읽지 않게 합니다. 이 PC의 다른 프로젝트 지시문이 섞이면 실행마다 입력이 달라집니다.
        with tempfile.TemporaryDirectory() as empty:
            options = ClaudeAgentOptions(
                model=request.model,
                tools=[],              # 내장 도구를 주지 않습니다. 글자만 받으면 됩니다.
                max_turns=1,
                setting_sources=[],
                cwd=empty,
                # 아래 넷은 2026-11-19 PC 시험에서 드러난 문제 때문에 넣었습니다. tools=[]와 setting_sources=[]만으로는
                # 이 PC 사용자의 MCP 연결, 플러그인, 스킬이 그대로 붙어 도구 정의 수만 토큰이 입력에 섞였고,
                # MCP가 붙는 타이밍에 따라 같은 이미지의 입력 크기가 2천~4.9만 토큰으로 흔들렸습니다.
                # 모델 입력이 실행마다 달라지면 비용도 정확도도 비교할 수 없으므로 모두 끕니다.
                mcp_servers={},        # 우리가 주는 MCP 서버는 없습니다.
                plugins=[],
                # SDK 버전에 따라 전용 필드가 없을 수 있어 CLI 인자를 그대로 넘깁니다 (값 없는 인자는 None).
                # strict-mcp-config: 위 mcp_servers에 적은 것만 쓰고 사용자·프로젝트·플러그인·claude.ai 연결은 무시합니다.
                # disable-slash-commands: 스킬과 명령을 모두 끕니다.
                extra_args={"strict-mcp-config": None, "disable-slash-commands": None},
                # 시스템 프롬프트를 주지 않으면 CLI의 기본 프롬프트가 들어갑니다. 요청에 없으면 빈 글자열로 바꿔
                # 모델이 받는 지시가 요청에 적힌 것뿐이 되게 합니다 (프롬프트 해시가 실제 입력과 맞도록).
                system_prompt=request.system if request.system is not None else "",
            )
            texts, response_model, error, final = [], None, None, None
            async with ClaudeSDKClient(options) as client:
                await client.query(messages())
                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        response_model = message.model or response_model
                        error = message.error or error
                        texts.extend(block.text for block in message.content if isinstance(block, TextBlock))
                    elif isinstance(message, ResultMessage):
                        final = message
        if final is None:
            return ModelResult(text="", error_type="UPSTREAM_ERROR")
        failed = error is not None or (final.is_error and final.stop_reason != "refusal")
        # 모델별 사용량에서 주 모델을 뺀 나머지가 SDK가 따로 부른 보조 모델입니다.
        auxiliary = tuple(
            (model, ModelResult(text="", sdk_reported_usd=counts.get("costUSD"),
                                **_usage(counts, ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens"))))
            for model, counts in (final.model_usage or {}).items()
            if response_model is not None and model != response_model
        )
        main_cost = (final.model_usage or {}).get(response_model, {}).get("costUSD") if response_model else None
        return ModelResult(
            text="\n".join(texts),
            response_model=response_model,
            # 주 모델의 비용을 따로 알면 그것을, 모르면 SDK의 합계를 적습니다 (보조 모델이 없으면 둘은 같습니다).
            sdk_reported_usd=main_cost if main_cost is not None else final.total_cost_usd,
            error_type=ERROR_CODES.get(error, "UPSTREAM_ERROR") if failed else None,
            stop_reason=final.stop_reason,
            num_turns=final.num_turns,
            duration_api_ms=final.duration_api_ms,
            auxiliary=auxiliary,
            **_usage(final.usage or {}, ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")),
        )
