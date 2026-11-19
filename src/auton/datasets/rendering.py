import json

from auton.datasets.contracts import TrainingExample
from auton.datasets.curation import validate_loss_mask


class LearningRecordRenderer:
    def render(self, example: TrainingExample) -> dict[str, object]:
        validate_loss_mask(example)
        if example.kind == "executor":
            assert example.target_message
            messages = (
                *example.input_messages,
                example.target_message,
                *example.following_tool_results,
            )
            return {
                "id": example.id,
                "kind": example.kind,
                "messages": [m.model_dump(mode="json", exclude_none=True) for m in messages],
                "tools": [t.model_dump(mode="json") for t in example.tools],
                "input_message_count": len(example.input_messages),
                "loss_message_indices": list(example.loss_message_indices),
            }
        return {
            "id": example.id,
            "kind": example.kind,
            "input": example.structured_input,
            "target": example.structured_target,
        }

    def encode(self, examples: tuple[TrainingExample, ...]) -> bytes:
        return "".join(
            json.dumps(self.render(e), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for e in examples
        ).encode()


class RecordRendererFactory:
    def create(self) -> LearningRecordRenderer:
        return LearningRecordRenderer()
