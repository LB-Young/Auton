import re


def scope_groups(
    prompt: str,
    answer: str,
    kind: str,
    domain: str = "general",
    tags: tuple[str, ...] = (),
    critical: bool = False,
    has_evidence: bool = False,
) -> tuple[str, ...]:
    text = prompt + "\n" + answer
    chinese, latin = bool(re.search(r"[\u4e00-\u9fff]", text)), bool(re.search(r"[a-zA-Z]", text))
    language = "mixed" if chinese and latin else "zh" if chinese else "en" if latin else "other"
    groups = [
        f"language:{language}",
        "length:long" if len(text.encode()) > 3000 else "length:short",
        "kind:" + kind,
        "domain:" + domain,
        "evidence:provided" if has_evidence else "evidence:none",
        *("tag:" + tag for tag in tags),
    ]
    if critical:
        groups.append("risk:critical")
    return tuple(dict.fromkeys(groups))
