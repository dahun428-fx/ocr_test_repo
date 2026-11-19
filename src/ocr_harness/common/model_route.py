"""모델 경로. 모든 모델 호출이 지나는 한 곳입니다.

호출 하나가 chat span 하나로 남고, 토큰·비용·오류 코드가 거기에 적힙니다. 비용 장부(ledger)는 그 span에서 뽑으므로,
여기를 거치지 않은 호출은 장부에 없는 호출이 됩니다. 그래서 모델을 부르는 코드는 뒷단(ModelBackend)을 직접 쓰지 않고
ModelRoute.call만 씁니다.

  ModelBackend   실제로 모델을 부르는 쪽의 인터페이스. 가짜(FakeBackend)와 Claude Agent SDK(model_agent_sdk)가 구현합니다.
  ModelRoute     뒷단을 감싸 span을 남기는 쪽. 뒷단이 무엇이든 기록 형식은 같습니다.
  PriceTable     토큰 수로 비용을 직접 계산하는 가격표.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ocr_harness.common import otlp
from ocr_harness.common.ids import content_digest
from ocr_harness.common.profile import Profile


@dataclass(frozen=True)
class ModelRequest:
    """모델 호출 1회의 입력. content는 Anthropic Messages API의 content 블록 목록입니다 (text, image)."""

    model: str
    content: list[dict]
    system: str | None = None
    role: str = "main"        # main: 답을 내는 주 모델, auxiliary: SDK가 따로 부른 보조 모델, ocr: OCR 단계에서 이미지를 읽는 모델
    attempt: int = 0          # 재시도 번호 (0부터). 재시도마다 호출도 span도 따로입니다.


@dataclass(frozen=True)
class ModelResult:
    """모델 호출 1회의 결과. 실패해도 예외가 아니라 이 값(error_type이 채워진)으로 돌려줍니다."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    response_model: str | None = None
    sdk_reported_usd: float | None = None   # SDK가 보고한 비용. 구독에서는 청구액이 아닌 환산값입니다. 모르면 None
    error_type: str | None = None           # 플랫폼 계약의 오류 코드 (RATE_LIMITED, UPSTREAM_ERROR 등). 성공이면 None
    stop_reason: str | None = None          # 모델이 멈춘 이유 (end_turn, max_tokens, refusal 등). 거절을 가려내는 데 씁니다.
    num_turns: int | None = None
    duration_api_ms: int | None = None
    # 같은 호출 안에서 SDK가 따로 부른 다른 모델들: ((모델 id, 그 모델의 결과), ...). 각각 chat span으로 남깁니다.
    auxiliary: tuple = ()


class ModelBackend(ABC):
    """모델을 실제로 부르는 쪽. 자식은 call만 구현하고, 아래 세 값으로 자기가 무엇인지 밝힙니다."""

    provider_name = "anthropic"      # gen_ai.provider.name
    platform_provider = "external"   # 플랫폼 계약의 구분: external(밖의 API) / self-hosted
    auth_route = "fake"              # subscription_oauth / api_key / fake. 인증 경로가 다른 실행은 결과를 섞지 않습니다.

    @abstractmethod
    def call(self, request: ModelRequest) -> ModelResult:
        """모델을 한 번 부릅니다. 예상한 실패(한도 초과 등)는 error_type을 채워 돌려줍니다."""


class FakeBackend(ModelBackend):
    """정해 둔 결과를 차례로 돌려주는 가짜 뒷단. 테스트와 배선 확인에 씁니다."""

    def __init__(self, results: list[ModelResult]):
        self._results = list(results)
        self.requests: list[ModelRequest] = []   # 무엇이 보내졌는지 테스트에서 들여다보려고 남깁니다.

    def call(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        return self._results.pop(0)


@dataclass(frozen=True)
class PriceTable:
    """모델별 가격 (100만 토큰당 달러). 버전을 함께 적어 어느 가격표로 계산했는지 남깁니다.

    SDK가 보고하는 비용과 따로 계산하는 이유: 구독 인증에서는 SDK의 값이 청구액이 아닌 환산값이고,
    가격이 바뀐 뒤에도 같은 토큰 수로 다시 계산할 수 있어야 하기 때문입니다.
    """

    version: str
    prices: dict = field(default_factory=dict)   # {모델 id: {"input", "output", "cache_read", "cache_write"}}

    def cost(self, model: str, result: ModelResult) -> float | None:
        """가격을 모르는 모델이면 None. 0으로 적으면 공짜로 읽히므로 모름과 구분합니다."""
        price = self.prices.get(model)
        if price is None:
            return None
        return (
            result.input_tokens * price["input"]
            + result.output_tokens * price["output"]
            + result.cache_read_input_tokens * price["cache_read"]
            + result.cache_write_input_tokens * price["cache_write"]
        ) / 1_000_000


class ModelRoute:
    """모델 호출의 단일 통로. 뒷단을 부르고 chat span 하나를 남깁니다."""

    def __init__(self, profile: Profile, tracer, backend: ModelBackend, prices: PriceTable, route_id: str = "route-default"):
        self.profile = profile
        self._tracer = tracer
        self._backend = backend
        self._prices = prices
        self._route_id = route_id   # 플랫폼 계약의 routeDecisionId. 경로가 하나뿐인 동안은 고정값입니다.

    def call(self, request: ModelRequest) -> ModelResult:
        try:
            result = self._backend.call(request)
        except Exception:  # noqa: BLE001  뒷단이 무엇을 던지든 호출 기록은 남겨야 합니다.
            # 예외 내용에는 원문이 섞일 수 있어 기록에 넣지 않고 분류 코드만 적습니다.
            result = ModelResult(text="", error_type="UPSTREAM_ERROR")
        self._record(request, result)
        # SDK가 안에서 따로 부른 모델(짧은 보조 작업용)도 비용이 드는 호출이므로 각각 한 줄로 남깁니다.
        for model, extra in result.auxiliary:
            self._record(ModelRequest(model=model, content=request.content, system=request.system,
                                      role="auxiliary", attempt=request.attempt), extra)
        return result

    def _record(self, request: ModelRequest, result: ModelResult) -> None:
        """호출 1회를 chat span 하나로 남깁니다. 현재 span이 있으면 그 자식으로 붙습니다 (항목 실행의 루트나 ocr span 아래).

        span의 길이는 기록하는 순간만 잽니다. 뒷단이 걸린 시간은 SDK가 보고한 값(sdk.duration_api_ms)을 봅니다.
        """
        own = self.profile.attr
        with self._tracer.start_as_current_span(f"chat {request.model}") as span:
            attributes = {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": self._backend.provider_name,
                "gen_ai.request.model": request.model,
                "gen_ai.usage.input_tokens": result.input_tokens,
                "gen_ai.usage.output_tokens": result.output_tokens,
                "gen_ai.usage.cache_read.input_tokens": result.cache_read_input_tokens,
                "gen_ai.usage.cache_write.input_tokens": result.cache_write_input_tokens,
                # 원문 대신 해시만 남깁니다. 같은 입력을 두 번 보냈는지 견줄 수 있습니다.
                own("prompt.digest"): content_digest({"system": request.system, "content": request.content}),
                own("model.role"): request.role,
                own("model.auth_route"): self._backend.auth_route,
                own("model.attempt"): request.attempt,
                "platform.model.provider": self._backend.platform_provider,
                "platform.route_decision.id": self._route_id,
                own("cost.price_table.version"): self._prices.version,
            }
            # 아래는 아는 경우에만 적습니다. 모르는 값을 0이나 빈 글자로 채우지 않습니다.
            optional = {
                "gen_ai.response.model": result.response_model,
                "gen_ai.response.finish_reasons": [result.stop_reason] if result.stop_reason else None,
                own("cost.computed_usd"): self._prices.cost(result.response_model or request.model, result),
                own("cost.sdk_reported_usd"): result.sdk_reported_usd,
                own("sdk.num_turns"): result.num_turns,
                own("sdk.duration_api_ms"): result.duration_api_ms,
            }
            attributes.update({key: value for key, value in optional.items() if value is not None})
            span.set_attributes(attributes)
            otlp.finish(span, result.error_type)
