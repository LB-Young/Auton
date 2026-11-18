# Vendored DeepSeek text encoders

The Python files are unchanged upstream source under the accompanying MIT
[LICENSE](./LICENSE). They are imported locally; no remote Python is fetched or
executed by setup or runtime. Ruff excludes this directory to preserve source
bytes. Mypy suppressions apply only to these upstream modules.

| Local file | Official fixed source | SHA256 |
| --- | --- | --- |
| `flash.py` | [V4.1 Flash encoding.py, commit 314113f8a7dadb388215396ba5fbee2c610a04d6](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/blob/314113f8a7dadb388215396ba5fbee2c610a04d6/encoding/encoding.py) | `13231c592e958fb39e2af6001dae69d90e7a36b265702b9b390236fb387599e2` |
| `pro.py` | [V4 Pro encoding_dsv4.py, commit b5968e9190ef611bbf34a7229255be88a0e937c1](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro/blob/b5968e9190ef611bbf34a7229255be88a0e937c1/encoding/encoding_dsv4.py) | `bdbd57c132a1b3725042323d02b98b9d1df28e5f388f134399555d041f5055e0` |

Only `encode_messages(..., thinking_mode="chat")` is called. Upstream imports are
standard-library typing/copy/json/re; no network, subprocess, eval or dynamic
imports. Flash also exposes an upstream `load_cases` local-file helper, which
Auton never calls. Image/video/audio and upstream completion parsing are outside
M08. Tools are attached to the first system message according to the official
encoder API; tokenization uses `add_special_tokens=False` because the encoder
already renders conversation special tokens.

Tokenizer JSON files are not vendored or committed. `make context-setup`
downloads the two fixed objects listed in `tokenization.BINDINGS`, verifies the
upstream Git blob digest and size, then saves them under ignored `weights/`.
DeepSeek model licensing and tokenizer provenance remain attached to the
respective official repositories; the MIT license here applies to encoder code.

Local encoder identity is distinct from the hosted alias: DeepSeek can update a
hosted model or prefix. This code does not assert identical hosted token counts
for every payload. Keep the conservative admission gate and use returned `usage`
for settlement. Upgrading encoder bytes, bindings or thinking mode requires
review, new compatibility evidence and a context algorithm version change.
