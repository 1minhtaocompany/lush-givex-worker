import ast
import os
import re
import sys


FUNCTION_PATTERN = re.compile(
    r"^\s*(?:def\s+)?(?P<name>[A-Za-z_]\w*)\s*"
    r"\((?P<params>[^)]*)\)\s*(?:->\s*(?P<return>[^\n:]+))?",
    re.MULTILINE,
)


def normalize_type(type_text):
    if not type_text:
        return None
    cleaned = " ".join(type_text.strip().rstrip(":").split())
    return cleaned or None


def extract_param_names(args):
    names = []
    for arg in args.posonlyargs + args.args:
        names.append(arg.arg)
    if args.vararg:
        names.append(args.vararg.arg)
    for arg in args.kwonlyargs:
        names.append(arg.arg)
    if args.kwarg:
        names.append(args.kwarg.arg)
    return names


def parse_params_from_text(param_text):
    text = param_text.strip()
    if not text:
        return []
    try:
        tree = ast.parse(f"def __spec__({text}):\n    pass")
        func = tree.body[0]
        if isinstance(func, ast.FunctionDef):
            return extract_param_names(func.args)
    except SyntaxError:
        pass
    params = []
    for raw in text.split(","):
        piece = raw.strip()
        if not piece or piece in {"*", "/"}:
            continue
        if piece.startswith("**"):
            piece = piece[2:]
        elif piece.startswith("*"):
            piece = piece[1:]
        if ":" in piece:
            piece = piece.split(":", 1)[0].strip()
        if "=" in piece:
            piece = piece.split("=", 1)[0].strip()
        if piece:
            params.append(piece)
    return params


def format_annotation(node, source):
    if node is None:
        return None
    try:
        text = ast.unparse(node)
    except Exception:
        text = ast.get_source_segment(source, node) or ""
    return normalize_type(text)


def parse_interface_spec(spec_path):
    if not os.path.isfile(spec_path):
        return {}
    try:
        with open(spec_path, "r", encoding="utf-8") as file:
            content = file.read()
    except (OSError, UnicodeError):
        return {}
    signatures = {}
    for match in FUNCTION_PATTERN.finditer(content):
        name = match.group("name")
        params_text = match.group("params") or ""
        return_text = normalize_type(match.group("return") or "")
        signatures[name] = {
            "params": parse_params_from_text(params_text),
            "return_type": return_text,
        }
    return signatures


def parse_schema_spec(spec_path):
    if not os.path.isfile(spec_path):
        return {}
    try:
        with open(spec_path, "r", encoding="utf-8") as file:
            content = file.read()
    except (OSError, UnicodeError):
        return {}
    try:
        tree = ast.parse(content, filename=spec_path)
    except SyntaxError:
        return {}
    signatures = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            signatures[node.name] = {
                "params": extract_param_names(node.args),
                "return_type": format_annotation(node.returns, content),
            }
    return signatures


def load_spec_signatures(repo_root):
    spec_dir = os.path.join(repo_root, "spec")
    interface_path = os.path.join(spec_dir, "interface.md")
    schema_path = os.path.join(spec_dir, "schema.py")
    interface_signatures = parse_interface_spec(interface_path)
    if interface_signatures:
        return interface_signatures
    schema_signatures = parse_schema_spec(schema_path)
    return schema_signatures


def iter_python_files(modules_dir):
    for root, _, files in os.walk(modules_dir):
        for filename in files:
            if filename.endswith(".py"):
                yield os.path.join(root, filename)


def compare_signatures(
    file_path, node, spec_signature, source, errors, warnings, repo_root
):
    spec_params = spec_signature["params"]
    code_params = extract_param_names(node.args)
    rel_path = os.path.relpath(file_path, repo_root)
    if len(code_params) != len(spec_params):
        missing = [name for name in spec_params if name not in code_params]
        extra = [name for name in code_params if name not in spec_params]
        if missing:
            message = f"missing params: {', '.join(missing)}"
        elif extra:
            message = f"extra params: {', '.join(extra)}"
        else:
            message = (
                f"param count mismatch (expected {len(spec_params)}, got {len(code_params)})"
            )
        errors.append((rel_path, node.lineno, node.name, message))
        return
    if code_params != spec_params:
        mismatches = [
            f"{idx + 1}: expected {spec} got {code}"
            for idx, (spec, code) in enumerate(zip(spec_params, code_params))
            if spec != code
        ]
        if mismatches:
            message = "param name mismatch (" + "; ".join(mismatches) + ")"
            errors.append((rel_path, node.lineno, node.name, message))
            return
    spec_return = spec_signature.get("return_type")
    if spec_return:
        code_return = format_annotation(node.returns, source)
        if not code_return:
            warnings.append(
                (
                    rel_path,
                    node.lineno,
                    node.name,
                    f"missing return annotation (expected {spec_return})",
                )
            )
        elif normalize_type(code_return) != normalize_type(spec_return):
            warnings.append(
                (
                    rel_path,
                    node.lineno,
                    node.name,
                    f"return type mismatch (expected {spec_return}, got {code_return})",
                )
            )


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    modules_dir = os.path.join(repo_root, "modules")
    spec_signatures = load_spec_signatures(repo_root)

    if not os.path.isdir(modules_dir):
        print("check_signature: PASS")
        return 0

    errors = []
    warnings = []

    for file_path in iter_python_files(modules_dir):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                content = file.read()
            tree = ast.parse(content, filename=file_path)
        except SyntaxError as exc:
            rel_path = os.path.relpath(file_path, repo_root)
            errors.append((rel_path, exc.lineno or 0, "<syntax>", exc.msg))
            continue
        except (OSError, UnicodeError) as exc:
            rel_path = os.path.relpath(file_path, repo_root)
            errors.append((rel_path, 0, "<read>", str(exc)))
            continue

        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            spec_signature = spec_signatures.get(node.name)
            if not spec_signature:
                continue
            compare_signatures(
                file_path, node, spec_signature, content, errors, warnings, repo_root
            )

    if errors:
        print("check_signature: FAIL")
        for rel_path, line, func_name, message in errors:
            print(f"FAIL: {rel_path}:{line} {func_name} {message}")
        for rel_path, line, func_name, message in warnings:
            print(f"WARN: {rel_path}:{line} {func_name} {message}")
        return 1

    for rel_path, line, func_name, message in warnings:
        print(f"WARN: {rel_path}:{line} {func_name} {message}")
    print("check_signature: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
