#!/usr/bin/env python3

"""
Python Import Collector and Viewer (PICV)

PICVはPythonプログラムの依存関係を解析し、それらのファイルの全コードを表示し、さらにクリップボードにコピーするツールです。
また、オプションを付けることでドキュメントコメントを省略することも可能です。

usage: collect_imports [OPTIONS] <MODULE_PATH ...> [EXCLUDE_PATH, ...]

positional arguments:
  module_path           依存関係を解析する起点のPythonファイルのパス
  exclude_path          除外するPythonファイルのパス

options:
    -h, --help            ヘルプを表示
    -n, --no-comment      ドキュメントコメントを省略する
    -d, --depth <number>   依存関係の解析を行う深さを指定する
    -l, --limit <number>   クリップボードへコピーを行う文字数の上限を指定する
"""


import os
import sys
import ast
import pyperclip
import re
import tiktoken


class ImportParser(ast.NodeVisitor):
    def __init__(self):
        self.imports = []

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append((False, alias.name))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        self.imports.append((node.level > 0, node.module))
        self.generic_visit(node)


def read_file(file, remove_comments):
    with open(file, "r") as f:
        content = f.read()
        if remove_comments:
            content = remove_docstring(content)
    return content


def remove_docstring(content):
    # ドキュメントコメントを削除する
    omit_content = re.sub(r'""".*?"""\n', '', content, flags=re.DOTALL)
    # '# 'から始めるコメントを削除する
    omit_content = re.sub(r'# .*?\n', '', omit_content)
    return omit_content


def parse_file(file):
    with open(file, "r") as f:
        tree = ast.parse(f.read())
    parser = ImportParser()
    parser.visit(tree)
    return parser.imports


def find_file(files, file):
    return files.get(file)


def get_all_py_files(dir):
    python_files = {}
    for root, _dirs, files in os.walk(dir):
        for file in files:
            if file.endswith('.py'):
                absolute_path = os.path.join(root, file)
                relative_path = os.path.relpath(absolute_path, dir)
                python_files[relative_path.replace("\\", "/")] = absolute_path
    return python_files


def main():
    dir = os.getcwd()
    parsed_files = []
    all_py_files = get_all_py_files(dir)
    files_to_parse = [arg for arg in sys.argv[1:] if arg != '--no-comment']
    clipboard_content = ""
    remove_comments = '--no-comment' in sys.argv[1:]

    while files_to_parse:
        file = files_to_parse.pop(0)
        file = file if os.path.isabs(file) else os.path.join(dir, file)

        if file in parsed_files:
            continue
        parsed_files.append(file)

        if not os.path.isfile(file):
            continue

        file_content = read_file(file, remove_comments)
        relative_path = os.path.relpath(file, dir)
        clipboard_content += f'\n=== {relative_path} ===\n'
        clipboard_content += file_content
        clipboard_content += '\n=== end ===\n'

        imports = parse_file(file)
        for is_relative, module in imports:
            module = module.replace(".", "/") + ".py"
            if is_relative:
                module_file = os.path.join(os.path.dirname(file), module)
            else:
                module_file = find_file(all_py_files, module)
            if module_file and module_file not in parsed_files:
                files_to_parse.append(module_file)

    print(clipboard_content)
    pyperclip.copy(clipboard_content)
    print(f'\n{len(clipboard_content)} characters copied to clipboard.')
    encoding = tiktoken.encoding_for_model("gpt-4")
    encoding.encode(clipboard_content)
    print(f'\n{len(encoding.encode(clipboard_content))} tokens encoded for gpt-4.')


if __name__ == "__main__":
    main()
