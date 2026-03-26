# Kiểm tra module có import từ module khác không
import ast
import os
import sys


def find_module_names(modules_dir):
    return sorted(
        name
        for name in os.listdir(modules_dir)
        if os.path.isdir(os.path.join(modules_dir, name))
    )


def iter_python_files(module_path):
    for root, _, files in os.walk(module_path):
        for filename in files:
            if filename.endswith(".py"):
                yield os.path.join(root, filename)


def resolve_import_root(import_name):
    if import_name == "modules":
        return "modules"
    if import_name.startswith("modules."):
        parts = import_name.split(".")
        if len(parts) > 1:
            return parts[1]
        return None
    return import_name.split(".")[0]


def check_import_statement(current_module, module_names, file_path, tree, errors, repo_root):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = resolve_import_root(alias.name)
                if root in module_names and root != current_module:
                    rel_path = os.path.relpath(file_path, repo_root)
                    errors.append((rel_path, node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                continue
            if not node.module:
                continue
            if node.module == "modules":
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in module_names and root != current_module:
                        rel_path = os.path.relpath(file_path, repo_root)
                        import_name = f"{node.module}.{alias.name}"
                        errors.append((rel_path, node.lineno, import_name))
            else:
                root = resolve_import_root(node.module)
                if root in module_names and root != current_module:
                    rel_path = os.path.relpath(file_path, repo_root)
                    errors.append((rel_path, node.lineno, node.module))


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    modules_dir = os.path.join(repo_root, "modules")
    if not os.path.isdir(modules_dir):
        print("check_import_scope: PASS")
        return 0

    module_names = find_module_names(modules_dir)
    errors = []

    for module_name in module_names:
        module_path = os.path.join(modules_dir, module_name)
        for file_path in iter_python_files(module_path):
            try:
                with open(file_path, "r", encoding="utf-8") as handle:
                    content = handle.read()
                tree = ast.parse(content, filename=file_path)
            except SyntaxError as exc:
                rel_path = os.path.relpath(file_path, repo_root)
                errors.append((rel_path, exc.lineno or 0, f"syntax error: {exc.msg}"))
                continue

            check_import_statement(
                module_name, module_names, file_path, tree, errors, repo_root
            )

    if errors:
        print("check_import_scope: FAIL")
        for file_path, line, import_name in errors:
            print(f"FAIL: {file_path}:{line} imports {import_name}")
        return 1

    print("check_import_scope: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
