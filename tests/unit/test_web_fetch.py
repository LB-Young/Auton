import pytest

from auton.tools.web_fetch import WebFetchTool


@pytest.mark.asyncio
async def test_web_fetch_disabled():
    tool = WebFetchTool()
    result = await tool.execute(url="https://example.com")
    assert not result.success
    assert "snapshot" in result.content
