#!/usr/bin/env python3

import os
import sys
import ast
import importlib.util
import pkgutil
import inspect
import argparse
import pyperclip
import re
import tiktoken
import logging
from typing import List


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


def is_package(module_name):
    """
    指定されたモジュールがパッケージであるかどうかを返します。

    Args:
        module_name (str): モジュール名。

    Returns:
        bool: パッケージであるかどうかを示すブール値。
    """
    try:
        spec = importlib.util.find_spec(module_name)
    except (AttributeError, ModuleNotFoundError):
        return False
    return spec is not None and spec.submodule_search_locations is not None


def get_modules_in_package(package_name: str) -> List[str]:
    """
    指定されたパッケージに含まれるモジュールの名前のリストを返します。

    Args:
        package_name (str): パッケージ名。

    Returns:
        List[str]: パッケージに含まれるモジュールの名前のリスト。
    """
    return [name for _, name, _ in pkgutil.iter_modules([package_name])]


def get_module_if_contains(package_name: str, target_class_or_func_names: List[str]) -> List[str]:
    """
    指定されたパッケージに含まれるモジュールのうち、指定されたクラスまたは関数を含むモジュールの名前のリストを返します。

    Args:
        package_name (str): パッケージ名。
        target_class_or_func_names (List[str]): 検索対象のクラスまたは関数の名前。

    Returns:
        List[str]: 指定されたクラスまたは関数を含むモジュールの名前のリスト。
    """
    modules = []
    for _, module_name, _ in pkgutil.iter_modules([package_name]):
        module = importlib.import_module(f"{package_name}.{module_name}")
        for name, _ in inspect.getmembers(module):
            for target_class_or_func_name in target_class_or_func_names:
                if name == target_class_or_func_name:
                    modules.append(module.__name__)
                    break
    return modules


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


class DependenciesSearcher():
    def __init__(self, root_path: str, module_paths: List[str], search_candidate_paths: List[str], depth: int = sys.maxsize):
        self.root_path: str = root_path
        self.module_paths: List[str] = module_paths
        self.search_candidate_paths: List[str] = search_candidate_paths
        self.depth: int = depth

    # 起点となるファイルのパスから、依存関係を解析して、ファイルのパスを返す
    def search_dependencies(self) -> List[str]:
        search_paths: List[List[str]] = [self.module_paths]
        searched_result_paths: List[str] = []
        current_depth: int = 0  # 探索中の階層の深さを0で初期化
        logging.info('\n== Parsing module dependencies ==')
        # 指定された深さまで依存関係を解析する
        for i in range(0, self.depth + 1):
            # 次に探索するファイルのパスを格納するリスト追加する
            search_paths.append([])
            # 現在の階層のログを出力する
            logging.info(f"\nDepth: {current_depth}")
            # 現在の階層のファイルのパスを取得する
            for path in search_paths[current_depth]:
                # 現在の階層のファイルのパスが探索済みのパスに含まれている場合、次のファイルのパスを探索する
                if path in searched_result_paths or path not in self.search_candidate_paths:
                    continue

                logging.info(f"  {path}")
                # 現在の階層のファイルのパスを探索済みのパスの先頭に追加する
                searched_result_paths.insert(0, path)
                # 現在の階層のファイルのパスから、依存関係を解析して、ファイルのパスを取得する。この時、絶対パスに変換する
                dependencies: List[str] = self.extract_imports(path)
                # 現在の階層のファイルのパスの依存関係のうち、探索済みのファイルのパスに含まれていない、かつ、探索候補のファイルのパスに含まれている場合は、次の階層のファイルのパスに追加する
                for dependency in dependencies:
                    if dependency in searched_result_paths or dependency not in self.search_candidate_paths:
                        continue

                    search_paths[current_depth + 1].append(dependency)
            current_depth += 1  # 次の階層に移動する
            # 次の階層のファイルのパスが存在しない場合、探索を終了する
            if len(search_paths[current_depth]) == 0:
                break

        return searched_result_paths

    def extract_imports(self, relative_path: str) -> List[str]:
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
        absolute_path = self.absolute_path(relative_path)
        # コードをASTで解析する
        tree = ast.parse(code)

        # AST内のすべてのImportFromノードを検索する
        imports: List[ast.ImportFrom] = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]

        result_module_names = []

        # モジュール名を取得する
        for node in imports:
            import_class_and_func_names = []
            module_name: str = node.module or ''

            # インポートされたクラスや関数の名前を取得する
            for alias in node.names:
                import_class_and_func_names.append(alias.name)

            # 相対インポートの場合は、絶対インポートに変換する
            if node.level > 0:
                base_dir = os.path.dirname(absolute_path)
                for _ in range(node.level - 1):
                    base_dir = os.path.dirname(base_dir)

                # root_pathとbase_dirの共通部分を削除するし、相対パスに変換する
                package_relative_name = os.path.relpath(base_dir, self.root_path).replace("/", ".")
                # モジュール名を結合する
                module_name = f"{package_relative_name}.{module_name}"

            # モジュール名がパッケージであるの場合は、パッケージに含まれるモジュールの内、直接importしているクラスや関数を含むモジュールを取得する
            if is_package(module_name):
                modules = get_modules_in_package(module_name)
                for module in modules:
                    result_module_names.append(f"{package_relative_name}.{module}")
                continue

            result_module_names.append(module_name)  # モジュール名を追加する

        # モジュール名をファイルの相対パスに変換する
        relative_paths = []
        for module_name in result_module_names:
            relative_path = module_name.replace(".", "/") + ".py"
            relative_paths.append(relative_path)
        return relative_paths

    def absolute_path(self, relative_path: str) -> str:
        """相対パスを絶対パスに変換する

        Args:
            relative_path (str): 相対パス

        Returns:
            str: 絶対パス
        """
        absolute_path = os.path.join(self.root_path, relative_path)
        # ファイルが存在しない場合は、空文字を返す
        if not os.path.exists(absolute_path):
            return ""
        return absolute_path


class ContentCreator():
    def __init__(self, searched_result_paths: List[str] = [], max_chara: int = sys.maxsize, max_token: int = sys.maxsize,
                 no_comment: bool = False):
        self.searched_result_paths = searched_result_paths
        self.max_chara = max_chara
        self.max_token = max_token
        self.no_comment = no_comment

    def create_content(self) -> List[str]:
        """指定されたファイルのパスのファイルの内容を取得する

        Returns:
            List[str]: 指定されたファイルのパスのファイルの内容のリスト
        """

        chunked_contents: List[str] = []
        logging.info('\n== Store file in Chunk ==')
        for relative_path in self.searched_result_paths:
            code = read_file(relative_path, self.no_comment)
            content = f'\n### {relative_path}\n```\n{code}\n```\n'
            if len(chunked_contents) == 0 or len(chunked_contents[-1] + content) > self.max_chara or count_tokens(chunked_contents[-1] + content) > self.max_token:
                if len(content) > self.max_chara or count_tokens(content) > self.max_token:
                    # チャンクサイズを超えた場合、チャンクサイズに収まるように分割する
                    chunked_codes: List[str] = code_split(content, self.max_chara, self.max_token)
                    for chunked_code in chunked_codes:
                        chunked_contents.append(chunked_code)
                        logging.info(f'\nChunk {len(chunked_contents)}')
                        logging.info(f'  {relative_path}(split)')
                else:
                    # チャンクサイズを超えた場合、新しいチャンクを作成する
                    chunked_contents.append(content)
                    logging.info(f'\nChunk {len(chunked_contents)}')
                    logging.info(f'  {relative_path}')
            else:
                # チャンクサイズを超えない場合、現在のチャンクに追加する
                chunked_contents[-1] += content
                logging.info(f'  {relative_path}')
        return chunked_contents


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

    # 引数の検証
    if type(root_path) is not str:
        raise TypeError('root_path must be str')
    if type(module_paths) is not list:
        raise TypeError('module_paths must be list')
    if type(depth) is not int:
        raise TypeError('depth must be int')
    # depthは0以上の整数でなければならない
    if depth < 0:
        raise ValueError('depth must be positive')
    if type(no_comment) is not bool:
        raise TypeError('no_comment must be bool')
    if type(max_chara) is not int:
        raise TypeError('max_chara must be int')
    if max_chara < 1:
        raise ValueError('max_chara must be positive')
    if type(max_token) is not int:
        raise TypeError('max_token must be int')
    if max_token < 1:
        raise ValueError('max_token must be positive')
    if type(excludes) is not list:
        raise TypeError('excludes must be list')

    # ルートディレクトリ以下の全Pythonファイルのパスを取得する
    all_py_paths: List[str] = get_all_py_paths(root_path)

    # 全ファイルのパスから除外するファイルのパスを除外する
    search_candidate_paths: List[str] = exclude_paths(all_py_paths, excludes)

    # 起点となるファイルのパスから、依存関係を解析して、ファイルのパスを取得する
    searcher = DependenciesSearcher(root_path, module_paths, search_candidate_paths, depth=depth)
    searched_result_paths: List[str] = searcher.search_dependencies()

    # 依存関係を解析したファイルのパスから、ファイルの内容を取得する
    creator = ContentCreator(searched_result_paths, max_chara, max_token, no_comment)
    chunked_content: List[str] = creator.create_content()

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
    lines = joined_content.split('\n')
    print('\n== Result ==\n')
    print(f'total characters: {len(joined_content)}')
    print(f'total lines:      {len(lines)}')
    print(f'total tokens:     {count_tokens(joined_content)} (encoded for gpt-4)')
    if len(chunked_content) > 1:
        print(f'total chunks:     {len(chunked_content)}')
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
    print('\n== Copy to clipboard ==')
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
    parser.add_argument('-mc', '--max_chara', type=int, default=3000000,
                        help='Split by a specified number of characters when copying to the clipboard')
    parser.add_argument('-mt', '--max_token', type=int, default=120000,
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
