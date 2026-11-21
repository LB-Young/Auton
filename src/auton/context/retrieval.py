import hashlib
import re

from auton.context.contracts import ContextConfig, Evidence, SourceLocation
from auton.context.ports import RerankerPort, RetrieverPort
from auton.genome.contracts import Snapshot


def terms(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9_]{2,}", text.casefold()))
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        words.update(run[i : i + 2] for i in range(max(1, len(run) - 1)))
    return words


class LexicalRetriever:
    def __init__(self, config: ContextConfig) -> None:
        self.config = config

    def retrieve(self, query: str, snapshot: Snapshot) -> tuple[Evidence, ...]:
        search = terms(query)
        found: dict[str, Evidence] = {}
        for asset in snapshot.assets:
            for start in range(0, len(asset.content), self.config.chunk_characters):
                text = asset.content[start : start + self.config.chunk_characters]
                words = terms(text + " " + asset.name)
                overlap = len(search & words)
                if not overlap:
                    continue
                digest = hashlib.sha256(text.encode()).hexdigest()
                score = overlap / max(1, len(search | words))
                location = SourceLocation(
                    asset_id=asset.id,
                    source=asset.source,
                    start_character=start,
                    end_character=start + len(text),
                )
                if digest in found:
                    old = found[digest]
                    found[digest] = old.model_copy(
                        update={
                            "locations": (*old.locations, location),
                            "score": max(old.score, score),
                            "asset_ids": tuple(sorted(set(old.asset_ids) | {asset.id})),
                            "source_references": tuple(
                                sorted(set(old.source_references) | {asset.source})
                            ),
                        }
                    )
                else:
                    found[digest] = Evidence(
                        locations=(location,),
                        asset_ids=(asset.id,),
                        source_references=(asset.source,),
                        start_character=start,
                        end_character=start + len(text),
                        content_digest=digest,
                        text=text,
                        score=score,
                    )
        return tuple(found.values())


class DeterministicReranker:
    def rank(self, evidence: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
        return tuple(sorted(evidence, key=lambda e: (-e.score, e.asset_ids, e.start_character)))


class RetrieverFactory:
    def create(self, config: ContextConfig) -> RetrieverPort:
        return LexicalRetriever(config)


class RerankerFactory:
    def create(self) -> RerankerPort:
        return DeterministicReranker()
