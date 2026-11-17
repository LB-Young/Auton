"""Fixed allowlisted programs. User source is parsed, never executed."""

import ast
import json
import resource
import sys


def main() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    value = json.loads(sys.stdin.read(262144))
    if value["program"] == "python.version":
        print(json.dumps({"output": sys.version.split()[0], "code": "ok"}))
    elif value["program"] == "python.syntax_check":
        try:
            ast.parse(value["source"], filename="<workspace-input>")
        except (SyntaxError, ValueError, RecursionError, MemoryError):
            print(json.dumps({"output": "Python syntax is invalid", "code": "syntax_error"}))
            raise SystemExit(1) from None
        print(
            json.dumps({"output": "Python syntax is valid; source was not executed", "code": "ok"})
        )
    else:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
