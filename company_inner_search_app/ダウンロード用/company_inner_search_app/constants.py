# constants.py
"""
このファイルは、固定の文字列や数値などのデータを変数として一括管理する“唯一の真実の源泉”です。
"""

############################################################
# ライブラリの読み込み（拡張子→ローダの紐づけに使用）
############################################################
# constants.py の先頭付近に（まだなら）追加
import os
from langchain_community.document_loaders import PyMuPDFLoader, Docx2txtLoader, CSVLoader, TextLoader
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

############################################################
# 画面表示系
############################################################
APP_NAME = "社内情報特化型生成AI検索アプリ"
ANSWER_MODE_1 = "社内文書検索"
ANSWER_MODE_2 = "社内問い合わせ"
CHAT_INPUT_HELPER_TEXT = "こちらからメッセージを送信してください。"
DOC_SOURCE_ICON = ":material/description: "
LINK_SOURCE_ICON = ":material/link: "
WARNING_ICON = ":material/warning:"
ERROR_ICON = ":material/error:"
SPINNER_TEXT = "回答生成中..."


############################################################
# ログ出力系
############################################################
LOG_DIR_PATH = "./logs"
LOGGER_NAME = "ApplicationLog"
LOG_FILE = "application.log"
APP_BOOT_MESSAGE = "アプリが起動されました。"


############################################################
# LLM設定系
############################################################
# モデル名（互換のため MODEL と LLM_MODEL を両方定義）
LLM_MODEL = "gpt-4o-mini"
MODEL = LLM_MODEL
# 生成の多様性
TEMPERATURE = 0.0
# 1レスポンスの最大トークン数（必要に応じて使用）
MAX_TOKENS = 1024
# 埋め込みモデル
EMBEDDING_MODEL = "text-embedding-3-small"


############################################################
# RAG設定系
############################################################
TOP_K = int(os.getenv("TOP_K", 5))

# "mmr" か "similarity" を選択（MMR_ENABLE は不要になります）
RETRIEVER_TYPE = os.getenv("RETRIEVER_TYPE", "mmr")

# MMR パラメータ
MMR_FETCH_K_MULTIPLIER = int(os.getenv("MMR_FETCH_K_MULTIPLIER", 5))  # 候補母集団
MMR_LAMBDA_MULT = float(os.getenv("MMR_LAMBDA_MULT", 0.5))            # 0=多様性 / 1=類似度

# チャンク
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 500))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 50))
assert 0 <= CHUNK_OVERLAP < CHUNK_SIZE, "chunk_overlap は 0 <= overlap < chunk_size を満たす必要があります"

# Embedding / VectorStore
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
CHROMA_DIR = os.getenv("CHROMA_DIR", ".chroma")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "company_inner_search")

# 検証用：作成チャンク数の上限（0は無制限）
MAX_CHUNKS = int(os.getenv("MAX_CHUNKS", 0))

# 文書0件時のメッセージ
NO_DOCS_WARNING = "インデックス対象の文書が読み込まれていません。RAG用フォルダやWeb設定を確認してください。"

############################################################
# RAG参照用のデータソース系
############################################################
from langchain_community.document_loaders import (
    PyMuPDFLoader,
    Docx2txtLoader,
    TextLoader,
    CSVLoader,
)

BASE_DIR = Path(__file__).resolve().parent

# ★ RAG_TOP_FOLDER_PATH は一度だけ定義（重複削除）
RAG_TOP_FOLDER_PATH = str((BASE_DIR / "data").resolve())

SUPPORTED_EXTENSIONS = {
    ".pdf": PyMuPDFLoader,
    ".docx": Docx2txtLoader,
    ".csv": lambda path: CSVLoader(path, encoding="utf-8"),
    # .txt は initialize.py 側でエンコーディングを再試行するのでここはクラス指定でOK
    ".txt": TextLoader,
}

# Web読み込みはデフォルトOFF（必要時だけ環境変数 ENABLE_WEB_SOURCES=1 でON）
WEB_SOURCES_ENABLED = bool(int(os.getenv("ENABLE_WEB_SOURCES", "0")))
WEB_URL_LOAD_TARGETS = []  # 使う時だけ URL を入れる

############################################################
# プロンプトテンプレート
############################################################
SYSTEM_PROMPT_CREATE_INDEPENDENT_TEXT = "会話履歴と最新の入力をもとに、会話履歴なしでも理解できる独立した入力テキストを生成してください。"

SYSTEM_PROMPT_DOC_SEARCH = """
    あなたは社内の文書検索アシスタントです。
    以下の条件に基づき、ユーザー入力に対して回答してください。

    【条件】
    1. ユーザー入力内容と以下の文脈との間に関連性がある場合、空文字「""」を返してください。
    2. ユーザー入力内容と以下の文脈との関連性が明らかに低い場合、「該当資料なし」と回答してください。

    【文脈】
    {context}
"""

SYSTEM_PROMPT_INQUIRY = """
    あなたは社内情報特化型のアシスタントです。
    以下の条件に基づき、ユーザー入力に対して回答してください。

    【条件】
    1. ユーザー入力内容と以下の文脈との間に関連性がある場合のみ、以下の文脈に基づいて回答してください。
    2. ユーザー入力内容と以下の文脈との関連性が明らかに低い場合、「回答に必要な情報が見つかりませんでした。」と回答してください。
    3. 憶測で回答せず、あくまで以下の文脈を元に回答してください。
    4. できる限り詳細に、マークダウン記法を使って回答してください。
    5. マークダウン記法で回答する際にhタグの見出しを使う場合、最も大きい見出しをh3としてください。
    6. 複雑な質問の場合、各項目についてそれぞれ詳細に回答してください。
    7. 必要と判断した場合は、以下の文脈に基づかずとも、一般的な情報を回答してください。

    {context}
"""


############################################################
# LLMレスポンスの一致判定用
############################################################
INQUIRY_NO_MATCH_ANSWER = "回答に必要な情報が見つかりませんでした。"
NO_DOC_MATCH_ANSWER = "該当資料なし"


############################################################
# エラー・警告メッセージ
############################################################
COMMON_ERROR_MESSAGE = "このエラーが繰り返し発生する場合は、管理者にお問い合わせください。"
INITIALIZE_ERROR_MESSAGE = "初期化処理に失敗しました。"
NO_DOC_MATCH_MESSAGE = """
    入力内容と関連する社内文書が見つかりませんでした。\n
    入力内容を変更してください。
"""
CONVERSATION_LOG_ERROR_MESSAGE = "過去の会話履歴の表示に失敗しました。"
GET_LLM_RESPONSE_ERROR_MESSAGE = "回答生成に失敗しました。"
DISP_ANSWER_ERROR_MESSAGE = "回答表示に失敗しました。"
