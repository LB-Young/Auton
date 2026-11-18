import json

from pydantic import ValidationError

from auton.assess.contracts import AssessConfig, JudgeObservation, JudgeVerdict
from auton.assess.ports import JudgePort
from auton.assess.rubric import RUBRIC
from auton.constitution.config import Principal
from auton.kernel.ports import ApplicationError
from auton.model.contracts import ModelMessage, ModelRequest
from auton.model.ports import ModelError, ModelGatewayPort


class ModelJudge:
    def __init__(self, config: AssessConfig, models: ModelGatewayPort) -> None:
        self.config, self.models = config, models

    async def evaluate(
        self,
        principal: Principal,
        identity: str,
        prompt: str,
        answer: str,
        public: bool,
        evidence: tuple[str, ...],
        actor_models: tuple[str, ...],
        actor_fingerprints: tuple[str, ...],
        evidence_text: dict[str, str] | None = None,
    ) -> JudgeObservation:
        observation = JudgeObservation(
            request_id=identity,
            rubric_revision=self.config.rubric_revision,
            configuration_digest=self.config.digest,
            verdict="unknown",
            reason="not_dispatched",
            source="unavailable",
        )
        payload = json.dumps(
            {
                "task": prompt,
                "answer": answer,
                "evidence_ids": evidence,
                "evidence_text": evidence_text or {},
            },
            ensure_ascii=False,
        )
        if len(payload.encode()) > 6000:
            return observation.model_copy(update={"reason": "judge_input_limit"})
        try:
            result = await self.models.generate(
                ModelRequest(
                    model_id=self.config.judge_model,
                    request_id=identity,
                    principal=principal.model_copy(update={"role": "runtime"}),
                    goal_id="assess-judge-" + identity[:64],
                    messages=(
                        ModelMessage(role="system", content=RUBRIC),
                        ModelMessage(role="user", content=payload),
                    ),
                    output_format="json",
                    max_output_tokens=512,
                    data_domain="public" if public else "local-only",
                )
            )
            biased = result.reported_model.casefold() in {
                name.casefold() for name in actor_models
            } or bool(result.system_fingerprint and result.system_fingerprint in actor_fingerprints)
            try:
                parsed = JudgeVerdict.model_validate_json(result.content)
                if (
                    any(ref not in evidence for ref in parsed.evidence)
                    or result.redacted
                    or (parsed.verdict != "unknown" and evidence and not parsed.evidence)
                    or result.finish_reason != "stop"
                    or result.tool_calls
                ):
                    raise ValueError("Invalid judge evidence or output protocol")
                verdict, reason = parsed.verdict, parsed.reason
            except (ValidationError, ValueError):
                parsed = None
                verdict, reason = "unknown", "invalid_or_unsupported_judge_output"
            return observation.model_copy(
                update={
                    "dispatch_outcome": "confirmed",
                    "verdict": verdict,
                    "reason": reason,
                    "evidence": parsed.evidence if parsed else (),
                    "reported_model": result.reported_model,
                    "fingerprint": result.system_fingerprint,
                    "source": result.source,
                    "self_eval_bias": biased,
                    "tokens": result.usage.input_tokens + result.usage.output_tokens,
                    "cost_microusd": result.usage.estimated_cost_microusd,
                    "reported_confidence": parsed.confidence if parsed else None,
                }
            )
        except ApplicationError as error:
            usage = error.usage if isinstance(error, ModelError) else None
            if usage is not None:
                return observation.model_copy(
                    update={
                        "reason": error.code,
                        "dispatch_outcome": "confirmed",
                        "tokens": usage.input_tokens + usage.output_tokens,
                        "cost_microusd": usage.estimated_cost_microusd,
                    }
                )
            unknown = isinstance(error, ModelError) and error.dispatched
            return observation.model_copy(
                update={
                    "reason": error.code,
                    "dispatch_outcome": "unknown" if unknown else "not_dispatched",
                    "tokens": None if unknown else 0,
                    "cost_microusd": None if unknown else 0,
                }
            )


class JudgeFactory:
    def create(self, config: AssessConfig, models: ModelGatewayPort) -> JudgePort:
        return ModelJudge(config, models)
