"""WebSearch Providers — 抽象基类与数据结构"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    """单条搜索结果"""

    title: str
    url: str
    snippet: str
    source: str = ""      # provider 名称
    score: float = 0.0    # 相关度（部分 provider 提供）

    def to_text(self) -> str:
        lines = [f"**{self.title}**", f"URL: {self.url}"]
        if self.snippet:
            lines.append(self.snippet)
        return "\n".join(lines)


class SearchProvider(ABC):
    """搜索 Provider 抽象基类

    子类必须定义：
      - ``NAME``      provider 标识符（小写）
      - ``ENV_KEYS``  触发该 provider 所需的环境变量名列表
    """

    NAME: str
    ENV_KEYS: list[str]

    @abstractmethod
    async def search(
        self,
        query: str,
        num_results: int = 5,
    ) -> list[SearchResult]:
        """执行搜索，返回结果列表。失败时抛出异常。"""
        ...

    def is_available(self) -> bool:
        """检查所需环境变量是否全部已设置"""
        import os
        return all(os.environ.get(k) for k in self.ENV_KEYS)
