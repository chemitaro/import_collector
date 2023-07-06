#!/usr/bin/env python3

"""
Python Import Collector

Pythonプログラムの依存関係を解析し、それらのファイルの全コードを表示し、さらにクリップボードにコピーするツールです。
また、オプションを付けることでドキュメントコメントを省略することも可能です。

usage: collect_imports [OPTIONS] <MODULE_PATH ...> [EXCLUDE_PATH, ...]

positional arguments:
  module_path           依存関係を解析する起点のPythonファイルのパス, 複数指定可能

options:
    -h, --help                   ヘルプを表示
    -d, --depth <number>         依存関係の解析を行う深さを指定する
    -n, --no-comment             ドキュメントコメントを省略する
    -c, --chunk <number>         クリップボードへコピーする際に指定した文字数で分割する
    -e, --exclude [<path>, ...]  除外するファイルのパスを指定する, 複数指定可能
"""


import os
import sys
import ast
import importlib
import argparse
import pyperclip
import re
import tiktoken
from typing import List, Optional, Tuple, Dict


def read_file(path: str, remove_comments: bool = False) -> str:
    """
    指定されたファイルを読み込み、その内容を返します。

    Args:
        path (str): 読み込むファイルのパス。
        remove_comments (bool): ドキュメントコメントを削除するかどうかを示すブール値。

    Returns:
        str: ファイルの内容。
    """

    with open(path, "r") as f:
        content = f.read()
        if remove_comments:
            content = remove_docstring(content)
    return content


def remove_docstring(content):
    """
    指定されたPythonコードからドキュメントコメントを削除します。

    Args:
        content (str): ドキュメントコメントを削除するPythonコード。

    Returns:
        str: ドキュメントコメントが削除されたPythonコード。
    """
    # ドキュメントコメントを削除する
    omit_content = re.sub(r'""".*?"""\n', '', content, flags=re.DOTALL)
    # '# 'から始めるコメントを削除する
    omit_content = re.sub(r'# .*?\n', '', omit_content)
    return omit_content


def convert_relative_import(file, module):
    """
    相対インポートを絶対インポートに変換します。

    Args:
        file (str): 相対インポートを含むPythonファイルのパス。
        module (str): 相対インポートを含むモジュールの名前。

    Returns:
        str: 相対インポートが絶対インポートに変換されたモジュールの名前。
    """
    # モジュールの名前から階層を取得する
    levels = module.count('.')
    # ファイルのパスからディレクトリを取得する
    directory = os.path.dirname(file)
    # 階層の数だけディレクトリを上に上がる
    for _ in range(levels):
        directory = os.path.dirname(directory)
    # ディレクトリと階層から絶対インポートに変換する
    return '.'.join([directory] + [module])


def extract_imports(root_path: str, relative_path: str) -> List[str]:
    """
    指定されたPythonファイルのインポートを解析し、インポートされたモジュールのファイルの相対パスのリストを返します。

    Args:
        root_path (str): 依存関係を解析する起点のPythonファイルのパス。
        relative_path (str): 依存関係を解析するPythonファイルのパス。

    Returns:
        List[str]: インポートされたモジュールのファイルの相対パスのリスト。
    """
    # ファイルの内容を読み込む
    code = read_file(relative_path, remove_comments=False)
    absolute_path = os.path.join(root_path, relative_path)
    # コードをASTで解析する
    tree = ast.parse(code)

    # AST内のすべてのインポートノードを検索する
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]

    # モジュールのインポートをファイルパスに変換する
    absolute_paths = []
    for node in imports:
        module_name = node.module
        if isinstance(node, ast.ImportFrom) and node.level > 0:
            # Relative import
            base_dir = os.path.dirname(absolute_path)
            for _ in range(node.level - 1):
                base_dir = os.path.dirname(base_dir)
            module_file_path = os.path.join(base_dir, module_name.replace(".", "/")) + ".py"
        elif module_name is not None:
            # Absolute import
            module_file_path = os.path.join(root_dir, module_name.replace(".", "/")) + ".py"
        absolute_paths.append(module_file_path)
    # 絶対パスを相対パスに変換する
    relative_paths = [os.path.relpath(absolute_path, root_path) for absolute_path in absolute_paths]
    return relative_paths


def find_file(files, file):
    return files.get(file)


def get_all_py_paths(path):
    """
    指定されたディレクトリ以下にある全てのPythonファイルのパスを取得します。

    Args:
        path (str): Pythonファイルを検索するディレクトリのパス。

    Returns:
        Dict[str, str]: 相対パスをキー、絶対パスを値とするPythonファイルの辞書。
    """
    python_files = {}
    for root, _dirs, files in os.walk(path):
        for file in files:
            if file.endswith('.py'):
                absolute_path = os.path.join(root, file)
                relative_path = os.path.relpath(absolute_path, path)
                python_files[relative_path.replace("\\", "/")] = absolute_path
    return python_files


def exclude_paths(all_py_paths: Dict[str, str], excludes: List[str] = []) -> Dict[str, str]:
    """
    ルートディレクトリ以下の全pythonファイルの辞書から除外するファイルを除外する

    Args:
        all_py_paths (dir[str, str]): ルートディレクトリ以下の全pythonファイルの辞書(相対パスをキー、絶対パスを値とする)
        excludes (List[str]): 除外するファイルの相対パスのリスト

    Returns:
        dir[str, str]: 除外後の全pythonファイルの辞書
    """
    for exclude in excludes:
        # 除外するファイルの相対パスが辞書のキーに存在する場合、そのキーを削除する
        if exclude in all_py_paths.keys():
            del all_py_paths[exclude]
    return all_py_paths


# 起点となるファイルのパスから、依存関係を解析して、ファイルのパスを返す
def search_dependencies(root_path: str, module_paths: List[str], search_candidate_paths: Dict[str, str], depth: int = sys.maxsize) -> Dict[str, str]:
    search_paths: List[List[str]] = [module_paths]
    searched_result_paths: Dict[str, str] = {}
    current_depth: int = 0  # 探索中の階層の深さを0で初期化
    # 指定された深さまで依存関係を解析する
    for i in range(0, depth):
        # 次に探索するファイルのパスを格納するリスト追加する
        search_paths.append([])
        # 現在の階層のファイルのパスを取得する
        for path in search_paths[current_depth]:
            # 現在の階層のファイルのパスが、探索済みのファイルのパスに含まれていない、かつ、探索候補のファイルのパスに含まれている場合
            if path not in searched_result_paths.keys() and path in search_candidate_paths.keys():
                # 現在の階層のファイルのパスを探索済みのファイルのパスに追加する
                searched_result_paths[path] = search_candidate_paths[path]
                # 現在の階層のファイルのパスから、依存関係を解析して、ファイルのパスを取得する。この時、絶対パスに変換する
                dependencies: List[str] = extract_imports(root_path, path)
                # 現在の階層のファイルのパスの依存関係を、次の階層のファイルのパスに追加する
                search_paths[current_depth + 1].extend(dependencies)
        current_depth += 1  # 次の階層に移動する
        # 次の階層のファイルのパスが存在しない場合、探索を終了する
        if len(search_paths[current_depth]) == 0:
            break

    return searched_result_paths


def create_content(searched_result_paths: Dict[str, str] = {}, chunk_size: int = sys.maxsize, no_comment: bool = False) -> List[str]:
    chunked_contents: List[str] = []
    for relative_path, absolute_path in searched_result_paths.items():
        content = read_file(absolute_path, no_comment)

def main(root_path: str, module_paths: List[str] = [], depth: int = sys.maxsize, no_comment: bool = False, chunk_size: int = sys.maxsize,
         excludes: List[str] = []):
    parsed_files = []
    # files_to_parse = module_paths
    # remove_comments = no_comment

    # clipboard_content = ""

    # ルートディレクトリ以下の全Pythonファイルのパスを取得する
    all_py_paths: Dict[str, str] = get_all_py_paths(root_path)

    # 全ファイルのパスから除外するファイルのパスを除外する
    search_candidate_paths: Dict[str, str] = exclude_paths(all_py_paths, excludes)

    # 起点となるファイルのパスから、依存関係を解析して、ファイルのパスを取得する
    searched_result_paths: Dict[str, str] = search_dependencies(root_path, module_paths, search_candidate_paths, depth)
    import pdb; pdb.set_trace()
    # 依存関係を解析したファイルのパスから、ファイルの内容を取得する
    chunked_content: List[str] = create_content(searched_result_paths, chunk_size, no_comment)

    # 処理を中断する
    sys.exit()

    while files_to_parse:
        file = files_to_parse.pop(0)
        file = file if os.path.isabs(file) else os.path.join(root_path, file)
        if file in parsed_files:
            continue
        parsed_files.append(file)

        if not os.path.isfile(file):
            continue

        file_content = read_file(file, remove_comments)
        relative_path = os.path.relpath(file, root_path)
        clipboard_content += f'\n```\n# {relative_path}\n'
        clipboard_content += file_content
        clipboard_content += '\n```\n'

        imports = parse_import(file)
        for is_relative, module in imports:
            module = module.replace(".", "/") + ".py"
            if is_relative:
                module_file = os.path.join(os.path.dirname(file), module)
            else:
                module_file = find_file(search_candidate_paths, module)
            if module_file and module_file not in parsed_files:
                files_to_parse.append(module_file)

    print(clipboard_content)
    pyperclip.copy(clipboard_content)
    print(f'\n{len(clipboard_content)} characters copied to clipboard.')
    encoding = tiktoken.encoding_for_model("gpt-4")
    encoding.encode(clipboard_content)
    print(f'\n{len(encoding.encode(clipboard_content))} tokens encoded for gpt-4.')


if __name__ == "__main__":
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(description='Python Import Collector')
    parser.add_argument('module_path', nargs='+', help='依存関係を解析する起点のPythonファイルのパス, 複数指定可能')
    parser.add_argument('-d', '--depth', type=int, default=sys.maxsize, help='依存関係の解析を行う深さを指定する')
    parser.add_argument('-n', '--no-comment', action='store_true', help='ドキュメントコメントを省略する')
    parser.add_argument('-c', '--chunk_size', type=int, default=sys.maxsize, help='クリップボードへコピーする際に指定した文字数で分割する')
    parser.add_argument('-e', '--exclude', nargs='*', default=[], help='除外するファイルのパスを指定する, 複数指定可能')
    args = parser.parse_args()

    root_dir = os.getcwd()

    # メイン処理
    main(root_dir, module_paths=args.module_path, depth=args.depth, no_comment=args.no_comment, chunk_size=args.chunk_size, excludes=args.exclude)
