from auton.judgment.contracts import Option, Question


class JudgmentQuestionsFactory:
    def create(self) -> tuple[Question, ...]:
        return (
            Question(
                id="sufficient",
                point="information_sufficiency",
                type="boolean",
                instructions=(
                    "Is the request specific enough to start useful work "
                    "without asking for essential missing information?"
                ),
            ),
            Question(
                id="executor",
                point="executor_tier",
                instructions="What executor capability does this task need?",
                options=(
                    Option(
                        id="small_2b",
                        description="Simple extraction, classification or short formatting.",
                    ),
                    Option(
                        id="small_7b",
                        description="Moderate writing or reasoning with a few constraints.",
                    ),
                    Option(
                        id="strong",
                        description=(
                            "Complex architecture, difficult coding, "
                            "multi-step reasoning or high consequence decisions."
                        ),
                    ),
                ),
            ),
            Question(
                id="tool",
                point="tool_domain",
                instructions="Which tool domain is most useful for this request?",
                options=(
                    Option(
                        id="none",
                        description="Answer from the given information; no tools required.",
                    ),
                    Option(id="read", description="Read documents or search for information."),
                    Option(id="write", description="Create or modify project files or run code."),
                ),
            ),
            Question(
                id="skill",
                point="skill_match",
                instructions="Which work pattern best matches the request?",
                options=(
                    Option(
                        id="general", description="General conversation or text transformation."
                    ),
                    Option(
                        id="research",
                        description="Collect and compare sources, write a research report.",
                    ),
                    Option(id="engineering", description="Design, implement or debug software."),
                ),
            ),
        )
