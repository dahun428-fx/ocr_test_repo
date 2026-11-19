"""비용 장부. 원본은 추적 파일의 chat span이고, 장부는 거기서 뽑는 집계입니다.

토큰과 비용을 한 곳(chat span)에만 적기 때문에 장부와 추적이 서로 어긋날 수 없습니다.
행의 키는 플랫폼 계약 0.2.0의 model-result와 같은 이름을 씁니다 (usage.inputTokens, provider, routeDecisionId).

속성 이름은 세 군데서 옵니다.
  - gen_ai.*, error.type   OTel 규약. 어느 프로젝트나 같으므로 여기 적어 둡니다.
  - platform.*             플랫폼 개념. 역시 같습니다.
  - <접두사>.*              프로젝트가 정한 이름. Profile의 접두사로 만듭니다 (이 연구는 ocr.*).
"""
from collections.abc import Iterable

from ocr_harness.common import otlp
from ocr_harness.common.profile import Profile


class Ledger:
    """프로젝트 하나의 비용 장부. 프로젝트만의 열이 필요하면 상속해서 extra_columns를 채웁니다."""

    # OTel GenAI 규약의 작업 이름. span 이름은 "<작업> <대상>" 꼴이라 앞부분으로 가려냅니다.
    ROOT_OPERATION = "invoke_agent"   # 항목 1건의 실행 전체 (항목 id와 조건 id가 여기 있습니다)
    CALL_OPERATION = "chat"           # 모델 호출 1회 (토큰과 비용이 여기 있습니다)

    def __init__(self, profile: Profile):
        self.profile = profile

    def extra_columns(self, call: dict, root: dict, resource: dict) -> dict:
        """프로젝트가 장부에 더 싣고 싶은 열. 기본은 없음.

        call은 chat span의 속성, root는 같은 추적의 루트 span 속성, resource는 그 줄의 resource 속성입니다.
        공통 열과 같은 키를 돌려주면 공통 열이 이깁니다 (플랫폼 계약의 이름을 프로젝트가 덮어쓰지 못하게).
        """
        return {}

    def model_calls(self, lines: Iterable[dict]) -> list[dict]:
        """추적 파일의 줄들(TracesData)에서 모델 호출 1회당 한 행을 만듭니다.

        재시도와 보조 모델 호출, 실패한 호출도 각각 한 행입니다. 실패를 빼면 비용이 실제보다 적게 잡힙니다.
        """
        own = self.profile.attr
        spans = [row for line in lines for row in otlp.flatten_spans(line)]
        # 항목 id와 조건 id는 루트 span에만 있으므로 traceId로 찾아 붙입니다.
        roots = {row["traceId"]: row["attributes"] for row in spans if row["name"].startswith(self.ROOT_OPERATION)}
        rows = []
        for row in spans:
            if not row["name"].startswith(self.CALL_OPERATION):
                continue
            a, root = row["attributes"], roots.get(row["traceId"], {})
            rows.append(self.extra_columns(a, root, row["resource"]) | {
                "runId": row["resource"].get(own("run.id")),
                "traceId": row["traceId"],
                "spanId": row["spanId"],
                "itemId": root.get(own("item.id")),
                "conditionId": root.get(own("condition.id")),
                "requestModel": a.get("gen_ai.request.model"),
                "modelRole": a.get(own("model.role")),
                "authRoute": a.get(own("model.auth_route")),
                "attempt": a.get(own("model.attempt")),
                "provider": a.get("platform.model.provider"),
                "routeDecisionId": a.get("platform.route_decision.id"),
                "usage": {"inputTokens": a.get("gen_ai.usage.input_tokens"), "outputTokens": a.get("gen_ai.usage.output_tokens")},
                "cacheReadInputTokens": a.get("gen_ai.usage.cache_read.input_tokens"),
                "cacheWriteInputTokens": a.get("gen_ai.usage.cache_write.input_tokens"),
                "hiddenContextTokens": a.get(own("usage.hidden_context_tokens")),
                # 비용을 모르면 속성이 없으므로 None이 됩니다. 0과 "모름"을 구분합니다.
                "cost": {
                    "sdkReportedUsd": a.get(own("cost.sdk_reported_usd")),
                    "computedUsd": a.get(own("cost.computed_usd")),
                    "priceTableVersion": a.get(own("cost.price_table.version")),
                },
                "errorCode": a.get("error.type"),
                "durationMs": (int(row["endTimeUnixNano"]) - int(row["startTimeUnixNano"])) // 1_000_000,
            })
        return rows
