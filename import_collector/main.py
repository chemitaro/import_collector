#!/usr/bin/env python3

import os
import sys
import ast
import argparse
import pyperclip
import re
import tiktoken
import logging
from typing import List, Optional


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
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name
        elif isinstance(node, ast.ImportFrom):
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


def get_all_py_paths(path) -> List[str]:
    """
    指定されたディレクトリ以下にある全てのPythonファイルのパスを取得します。

    Args:
        path (str): Pythonファイルを検索するディレクトリのパス。

    Returns:
        List[str]: 相対パスのリスト。
    """
    all_py_paths: List[str] = []
    for root, _dirs, files in os.walk(path):
        for file in files:
            if file.endswith('.py'):
                absolute_path = os.path.join(root, file)
                relative_path = os.path.relpath(absolute_path, path)
                all_py_paths.append(relative_path)
    return all_py_paths


def exclude_paths(all_py_paths: List[str], excludes: List[str] = []) -> List[str]:
    """
    ルートディレクトリ以下の全pythonファイルの辞書から除外するファイルを除外する

    Args:
        all_py_paths (List[str]): ルートディレクトリ以下の全pythonファイルの辞書
        excludes (List[str]): 除外するファイルの相対パスのリスト

    Returns:
        List[str]: 除外後の全pythonファイルの辞書
    """
    for exclude in excludes:
        # 除外するファイルの相対パスが存在する場合、その要素を削除する
        if exclude in all_py_paths:
            all_py_paths.remove(exclude)

    return all_py_paths


# 起点となるファイルのパスから、依存関係を解析して、ファイルのパスを返す
def search_dependencies(root_path: str, module_paths: List[str], search_candidate_paths: List[str], depth: int = sys.maxsize) -> List[str]:
    search_paths: List[List[str]] = [module_paths]
    searched_result_paths: List[str] = []
    current_depth: int = 0  # 探索中の階層の深さを0で初期化
    # 指定された深さまで依存関係を解析する
    for i in range(0, depth):
        # 次に探索するファイルのパスを格納するリスト追加する
        search_paths.append([])
        # 現在の階層のログを出力する
        logging.info(f"\nParsing depth: {current_depth}")
        # 現在の階層のファイルのパスを取得する
        for path in search_paths[current_depth]:
            # 現在の階層のファイルのパスが、探索済みのファイルのパスに含まれていない、かつ、探索候補のファイルのパスに含まれている場合
            if path not in searched_result_paths and path in search_candidate_paths:
                logging.info(f"  {path}")
                # 現在の階層のファイルのパスを探索済みのパスの先頭に追加する
                searched_result_paths.insert(0, path)
                # 現在の階層のファイルのパスから、依存関係を解析して、ファイルのパスを取得する。この時、絶対パスに変換する
                dependencies: List[str] = extract_imports(root_path, path)
                # 現在の階層のファイルのパスの依存関係を、次の階層のファイルのパスに追加する
                search_paths[current_depth + 1].extend(dependencies)
        current_depth += 1  # 次の階層に移動する
        # 次の階層のファイルのパスが存在しない場合、探索を終了する
        if len(search_paths[current_depth]) == 0:
            break

    return searched_result_paths


def code_split(code: str, max_chara: int = sys.maxsize, max_token: int = sys.maxsize) -> List[str]:
    """
    文字列がチャンクサイズより大きい場合、チャンクサイズに分割する。

    この時、なるべく改行の位置で分割する。

    Args:
        string (str): 分割する文字列
        max_chara (int, optional): チャンクサイズ. Defaults to sys.maxsize.
        max_token (int, optional): チャンクサイズ. Defaults to sys.maxsize.

    Returns:
        List[str]: 分割後の文字列のリスト
    """

    # チャンクサイズより文章が小さい場合、そのまま返す
    if len(code) <= max_chara and count_tokens(code) <= max_token:
        return [code]

    chunked_code: List[str] = ['']
    split_last_message = '\n```\n'

    # 文字列を改行で分割する
    splited_rows: List[str] = code.split('\n')
    # 改行で分割した文字列をチャンクサイズより小さくなるように結合する
    for splited_row in splited_rows:
        size_check_set = chunked_code[-1] + splited_row + split_last_message
        if (len(size_check_set) > max_chara or count_tokens(size_check_set) > max_token):
            chunked_code[-1] += split_last_message
            chunked_code.append(f'\n```\n# The cord continued.\n{splited_row}')
        else:
            chunked_code[-1] += f'\n{splited_row}'

    return chunked_code


def create_content(searched_result_paths: List[str] = [], max_chara: int = sys.maxsize, max_token: int = sys.maxsize,
                   no_comment: bool = False) -> List[str]:
    """指定されたファイルのパスのファイルの内容を取得する

    Args:
        searched_result_paths (List[str], optional): 指定されたファイルのパスのリスト. Defaults to [].
        max_chara (int, optional): ファイルの内容を取得する際のチャンクサイズ. Defaults to sys.maxsize.
        max_token (int, optional): ファイルの内容を取得する際のトークン数. Defaults to sys.maxsize.
        no_comment (bool, optional): コメントを除去するかどうか. Defaults to False.

    Returns:
        List[str]: 指定されたファイルのパスのファイルの内容のリスト
    """

    chunked_contents: List[str] = []
    for relative_path in searched_result_paths:
        code = read_file(relative_path, no_comment)
        content = f'\n```\n# {relative_path}\n{code}\n```\n'
        if len(chunked_contents) == 0 or len(chunked_contents[-1] + content) > max_chara or count_tokens(chunked_contents[-1] + content) > max_token:
            if len(content) > max_chara or count_tokens(content) > max_token:
                # チャンクサイズを超えた場合、チャンクサイズに収まるように分割する
                chunked_code: List[str] = code_split(content, max_chara, max_token)
                chunked_contents.extend(chunked_code)
            else:
                # チャンクサイズを超えた場合、新しいチャンクを作成する
                chunked_contents.append(content)
        else:
            # チャンクサイズを超えない場合、現在のチャンクに追加する
            chunked_contents[-1] += content
    return chunked_contents


# 受け取ったテキストのトークン数を返す
def count_tokens(text: str, model: str = 'gpt-4') -> int:
    """
    受け取ったテキストのトークン数を返す

    Args:
        text (str): 受け取ったテキスト
        model (str, optional): トークナイザーのモデル名. Defaults to 'gpt-4'.

    Returns:
        int: 受け取ったテキストのトークン数
    """
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))


def main(root_path: str, module_paths: List[str] = [], depth: int = sys.maxsize, no_comment: bool = False, max_chara: int = sys.maxsize,
         max_token: int = sys.maxsize, excludes: List[str] = []):
    """指定されたファイルのパスのファイルの内容を取得する

    Args:
        root_path (str): 起点となるファイルのパス
        module_paths (List[str], optional): 起点となるファイルのパスからの相対パスのリスト. Defaults to [].
        depth (int, optional): 起点となるファイルのパスからの相対パスのリスト. Defaults to sys.maxsize.
        no_comment (bool, optional): コメントを除去するかどうか. Defaults to False.
        max_chara (int, optional): ファイルの内容を取得する際のチャンクサイズ. Defaults to sys.maxsize.
        excludes (List[str], optional): 除外するファイルのパスのリスト. Defaults to [].

    Returns:
        List[str]: 指定されたファイルのパスのファイルの内容のリスト
    """
    # ルートディレクトリ以下の全Pythonファイルのパスを取得する
    all_py_paths: List[str] = get_all_py_paths(root_path)

    # 全ファイルのパスから除外するファイルのパスを除外する
    search_candidate_paths: List[str] = exclude_paths(all_py_paths, excludes)

    # 起点となるファイルのパスから、依存関係を解析して、ファイルのパスを取得する
    searched_result_paths: List[str] = search_dependencies(root_path, module_paths, search_candidate_paths, depth)

    # 依存関係を解析したファイルのパスから、ファイルの内容を取得する
    chunked_content: List[str] = create_content(searched_result_paths, max_chara, max_token, no_comment)
    return chunked_content


# 取得したコードと文字数やトークン数、chunkの数を表示する
def print_result(chunked_content: List[str], max_chara: int = sys.maxsize, max_token: int = sys.maxsize) -> None:
    """
    取得したコードと文字数やトークン数、chunkの数を表示する

    Args:
        chunked_content (List[str]): 取得したコードのリスト
        max_chara (int, optional): ファイルの内容を取得する際のチャンクサイズ. Defaults to sys.maxsize.
        max_token (int, optional): ファイルの内容を取得する際のチャンクサイズ. Defaults to sys.maxsize.

    Returns:
        None
    """
    joined_content: str = ''.join(chunked_content)
    print('\n== Result ==')
    print(f'total characters: {len(joined_content)}')
    print(f'total tokens:     {count_tokens(joined_content)} (encoded for gpt-4)')
    if len(chunked_content) > 1:
        print(f'\n{len(chunked_content)} chunks.')
        if max_chara < sys.maxsize:
            print(f'  ({max_chara} characters per chunk.)')
        if max_token < sys.maxsize:
            print(f'  ({max_token} tokens per chunk.)')


# chunked_content を順番にクリップボードにコピーする
def copy_to_clipboard(chunked_content: List[str]):
    """
    chunked_content を順番にクリップボードにコピーする

    Args:
        chunked_content (List[str]): コピーする内容のリスト

    Returns:
        None
    """
    for content in chunked_content:
        pyperclip.copy(content)
        # chunkのナンバーを表示する
        print(f'\nChunk {chunked_content.index(content) + 1} of {len(chunked_content)} copied to clipboard.')
        # 文字数とトークン数を表示する
        print(f'  ({len(content)} chara, {count_tokens(content)} tokens)')
        # chunkが最後のchunkでない場合、Enterキーを押すまで待機する
        if chunked_content.index(content) + 1 < len(chunked_content):
            input('\nPress Enter to continue...')


if __name__ == "__main__":
    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(
        description="""
        This tool analyzes the dependencies of Python programs, displays all the code in those files, and also copies them to the clipboard.
        It is also possible to omit document comments by adding options.
        Assuming a character limit, you can also split the copy to the clipboard by a specified number of characters.
        """
    )
    parser.add_argument('module_path', nargs='+', help='Path of the Python file from which to parse dependencies, multiple paths can be specified')
    parser.add_argument('-d', '--depth', type=int, default=999, help='Specify depth of dependency analysis')
    parser.add_argument('-n', '--no-comment', action='store_true', help='Omit document comments')
    parser.add_argument('-mc', '--max_chara', type=int, default=15000,
                        help='Split by a specified number of characters when copying to the clipboard')
    parser.add_argument('-mt', '--max_token', type=int, default=2700,
                        help='Split by a specified number of tokens when copying to the clipboard')
    parser.add_argument('-e', '--exclude', nargs='*', default=[], help='Specify paths of files to exclude, multiple files can be specified')
    args = parser.parse_args()

    root_dir = os.getcwd()

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    # メイン処理
    chunked_content = main(root_dir, module_paths=args.module_path, depth=args.depth, no_comment=args.no_comment, max_chara=args.max_chara,
                           max_token=args.max_token, excludes=args.exclude)

    # 取得したコードと文字数やトークン数、chunkの数を表示する
    print_result(chunked_content, max_chara=args.max_chara, max_token=args.max_token)

    # chunked_content を順番にクリップボードにコピーする
    copy_to_clipboard(chunked_content)