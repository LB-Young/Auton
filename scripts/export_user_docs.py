"""Export configuration and HTTP/schema"
" reference docs without reading secret"
"s or making calls."""

import argparse
import json
import re
from pathlib import Path
from typing import Any

from auton.bootstrap.config import ApplicationConfig

ROOT = Path(__file__).resolve().parents[1]


def anchor(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "-", name.lower())


def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def schema_type(value: dict[str, Any]) -> str:
    if "$ref" in value:
        name = value["$ref"].split("/")[-1]
        return f"[{name}](#{anchor(name)})"
    for key in ("anyOf", "oneOf", "allOf"):
        if key in value:
            return " / ".join(schema_type(v) for v in value[key])
    if "const" in value:
        return "`" + cell(json.dumps(value["const"], ensure_ascii=False)) + "`"
    if "enum" in value:
        return ", ".join("`" + cell(json.dumps(v, ensure_ascii=False)) + "`" for v in value["enum"])
    if value.get("type") == "array":
        return "array&lt;" + schema_type(value.get("items", {})) + "&gt;"
    if value.get("type") == "object" and isinstance(value.get("additionalProperties"), dict):
        return "map&lt;" + schema_type(value["additionalProperties"]) + "&gt;"
    return str(value.get("type", "object"))


def constraints(value: dict[str, Any]) -> str:
    labels = {
        "minimum": "≥",
        "exclusiveMinimum": ">",
        "maximum": "≤",
        "exclusiveMaximum": "<",
        "minLength": "最短",
        "maxLength": "最长",
        "minItems": "最少项",
        "maxItems": "最多项",
        "pattern": "格式",
        "format": "类型格式",
        "minProperties": "最少属性",
        "maxProperties": "最多属性",
    }
    return "; ".join(
        label + " " + cell(v) for k, label in labels.items() if (v := value.get(k)) is not None
    )


def fields(name: str, schema: dict[str, Any], defaults: dict[str, Any] | None = None) -> str:
    lines = [f'<a id="{anchor(name)}"></a>', f"### {name}", ""]
    if schema.get("description"):
        lines += [schema["description"], ""]
    if "properties" not in schema:
        return "\n".join([*lines, schema_type(schema), ""])
    lines += [
        "| 参数 | 类型 / 可选值 | 必填 | 默认值 | 约束 / 说明 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for field, definition in schema["properties"].items():
        default = (defaults or {}).get(field, definition.get("default"))
        shown = (
            "—"
            if default is None and "default" not in definition
            else "`" + cell(json.dumps(default, ensure_ascii=False)) + "`"
        )
        if name == "ApplicationConfig" and isinstance(default, dict):
            shown = "见对应类型字段"
        notes = "; ".join(
            v for v in (constraints(definition), definition.get("description", "")) if v
        )
        lines.append(
            f"| `{field}` | {schema_type(definition)} | "
            f"{'是' if field in schema.get('required', []) else '否'} | {shown} | {cell(notes)} |"
        )
    return "\n".join([*lines, ""])


def render() -> dict[Path, str]:
    config = ApplicationConfig()
    config_schema = config.model_json_schema()
    schemas = config_schema.get("$defs", {})
    config_lines = [
        "# 配置参数完整参考",
        "",
        "由 `scripts/export_user_docs.py` 从 Appl"
        "icationConfig 生成。不要手改参数表；使用"
        "说明见 [配置指南](../configuration.md)。默认值来自代"
        "码，不读取 .env、环境密钥或本机硬件。",
        "",
        "配置文件为 TOML。根字段对应 ApplicationConfig；模块字"
        "段置于同名 `[module]` 表。数组对象使用 `"
        "[[module.field]]`；下方类型链接列出嵌套对象。数字约束与跨字"
        "段校验同时生效，见配置指南。",
        "",
    ]
    config_lines += [fields("ApplicationConfig", config_schema, config.model_dump(mode="json"))]
    default_by_type = {
        type(getattr(config, n)).__name__: getattr(config, n).model_dump(mode="json")
        for n in type(config).model_fields
        if hasattr(getattr(config, n), "model_dump")
    }
    for name, schema in sorted(schemas.items()):
        config_lines += [fields(name, schema, default_by_type.get(name))]
    spec = json.loads((ROOT / "contracts/openapi.json").read_text())
    schema_lines = [
        "# HTTP 请求与响应参数完整参考",
        "",
        "由已提交的 OpenAPI 契约生成。入口和错误处理见 [API 使用指南]"
        "(../api.md)，接口目录见 [HTTP 路由]"
        "(api-endpoints.md)。`-Input` 为输入格式，`-Ou"
        "tput` 为返回格式；不要将响应中的 owner/role/内部状态自行拼"
        "进请求。",
        "",
        "表中必填以具体 HTTP schema 为准，含显式 null 的响应字段可"
        "能仍为必填。未显示默认值的字段不代表存在隐式授权。字段间业务约束还受服务端校"
        "验和当前状态门禁限制。",
        "",
    ]
    for name, schema in sorted(spec["components"]["schemas"].items()):
        schema_lines += [fields(name, schema)]
    endpoint_lines = [
        "# HTTP 路由完整目录",
        "",
        "由 `contracts/openapi.json` 生成；所有路径、方法、"
        "查询/路径参数、请求类型和响应状态如下。鉴权、写请求头"
        "、WebSocket 和 curl 示例见 [API 指南](../api."
        "md)。参数类型详见 [请求/响应参考](api-schemas.md)。",
        "",
    ]
    for path, operations in sorted(spec["paths"].items()):
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                continue
            endpoint_lines += [f"## {method.upper()} {path}", "", operation.get("summary", ""), ""]
            if operation.get("parameters"):
                endpoint_lines += [
                    "| 参数 | 位置 | 必填 | 类型 | 默认值 | 约束 |",
                    "| --- | --- | --- | --- | --- | --- |",
                ]
                for param in operation["parameters"]:
                    definition = param.get("schema", {})
                    default = (
                        cell(json.dumps(definition["default"], ensure_ascii=False))
                        if "default" in definition
                        else "—"
                    )
                    endpoint_lines.append(
                        f"| `{param['name']}` | {param['in']} | "
                        f"{'是' if param.get('required') else '否'} | {schema_type(definition)} | "
                        f"{default} | {cell(constraints(definition))} |"
                    )
                endpoint_lines.append("")
            for mime, body in operation.get("requestBody", {}).get("content", {}).items():
                endpoint_lines += [f"请求体 `{mime}`：" + schema_type(body.get("schema", {})), ""]
            for code, response in operation.get("responses", {}).items():
                types = [
                    schema_type(v.get("schema", {})) for v in response.get("content", {}).values()
                ]
                endpoint_lines.append(
                    f"- `{code}` {response.get('description', '')}"
                    + ("：" + " / ".join(types) if types else "")
                )
            endpoint_lines.append("")
    endpoints = "\n".join(endpoint_lines)
    # Cross-page model links in the route directory target the schema appendix.
    endpoints = re.sub(r"\]\(#([^)]+)\)", r"](api-schemas.md#\1)", endpoints)
    return {
        ROOT / "docs/reference/configuration.md": "\n".join(config_lines),
        ROOT / "docs/reference/api-schemas.md": "\n".join(schema_lines),
        ROOT / "docs/reference/api-endpoints.md": endpoints,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Check docs match committed schemas/defaults"
    )
    args = parser.parse_args()
    for path, content in render().items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit("Documentation drift: " + str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    print(
        "User parameter references match source"
        if args.check
        else "Exported user parameter references"
    )


if __name__ == "__main__":
    main()
