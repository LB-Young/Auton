"""Typed choice supervision for an encoder ranker; never conversation SFT."""

import hashlib
import json
from typing import Any

from auton.constitution.config import Principal
from auton.judgment.contracts import Question
from auton.kernel.ports import ApplicationError
from auton.training.contracts import TrainingPlanCommand
from auton.training.data import TrainingDataReader, source_artifacts
from auton.training.dependencies import TrainingDependencies


def decision_record(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("kind") != "decision" or set(record.get("input", {})) != {"state", "question"}:
        raise ValueError("decision_input_schema")
    question = Question.model_validate(record["input"]["question"])
    state = record["input"]["state"]
    if not isinstance(state, str) or not state or len(state) > 12000:
        raise ValueError("decision_state_bounds")
    options = [(o.id, o.description) for o in question.options]
    if question.type == "boolean":
        options = [("no", "No"), ("yes", "Yes")]
    target = record["target"]
    if target.get("question_id") != question.id or target.get("type") != question.type:
        raise ValueError("decision_target_scope")
    selected = target.get("selected_id")
    if selected not in {identity for identity, _ in options}:
        raise ValueError("decision_unknown_option")
    return {
        "id": record["id"],
        "state": state,
        "question": question.model_dump(mode="json"),
        "options": options,
        "selected_id": selected,
        "group_id": record.get("_lineage_group", hashlib.sha256(state.encode()).hexdigest()),
    }


class DecisionDataReader(TrainingDataReader):
    def __init__(self, deps: TrainingDependencies) -> None:
        super().__init__(deps, "decision")

    async def read(
        self, principal: Principal, command: TrainingPlanCommand
    ) -> tuple[dict[str, bytes], dict[str, str], dict[str, int], dict[str, int]]:
        inputs, manifests, examples, groups = await super().read(principal, command)
        for scope, content in tuple(inputs.items()):
            lineage = {}
            for identity in source_artifacts(command, scope):
                artifact, _ = await self.deps.datasets.read_artifact(principal, identity)
                snapshot = await self.deps.datasets.get(principal, artifact.snapshot_id)
                lineage.update(
                    {
                        e.id: e.group_id
                        for e in snapshot.examples
                        if e.split == artifact.command.split
                    }
                )
            derived = []
            try:
                for line in content.splitlines():
                    record = json.loads(line)
                    decision_record(record)
                    record["_lineage_group"] = lineage[record["id"]]
                    derived.append(json.dumps(record, ensure_ascii=False, sort_keys=True))
            except (ValueError, TypeError, KeyError) as error:
                raise ApplicationError(
                    409,
                    "decision_training_invalid_record",
                    "Decision data must preserve typed questions and stable option labels",
                ) from error
            inputs[scope] = ("\n".join(derived) + "\n").encode()
        return inputs, manifests, examples, groups


class EncoderChoiceDataAdapter:
    def render(self, record: dict[str, Any]) -> dict[str, Any]:
        value = decision_record(record)
        return {
            "format": "encoder-choice-v1",
            "id": value["id"],
            "state": value["state"],
            "question": value["question"],
            "options": value["options"],
            "label_id": value["selected_id"],
        }


class LLMDecisionDataAdapter:
    """Separate JSON readout export, never executor tool-call SFT."""

    def render(self, record: dict[str, Any]) -> dict[str, Any]:
        value = decision_record(record)
        prompt = json.dumps(
            {"state": value["state"], "question": value["question"]},
            ensure_ascii=False,
            sort_keys=True,
        )
        target = json.dumps(
            {
                "question_id": value["question"]["id"],
                "type": value["question"]["type"],
                "selected_id": value["selected_id"],
            },
            sort_keys=True,
        )
        return {
            "format": "decision-json-readout-v1",
            "id": value["id"],
            "messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": target},
            ],
            "loss_message_indices": [1],
            "requires_actual_template_token_mask": True,
        }


class DecisionDataAdapterFactory:
    def create(self, readout: str) -> EncoderChoiceDataAdapter | LLMDecisionDataAdapter:
        if readout == "encoder_choice":
            return EncoderChoiceDataAdapter()
        if readout == "llm_json":
            return LLMDecisionDataAdapter()
        raise ValueError("Unsupported decision readout")
