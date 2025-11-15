"""
このファイルは、最初の画面読み込み時にのみ実行される初期化処理が記述されたファイルです。
"""

############################################################
# ライブラリの読み込み
############################################################
# 標準
import os
import sys
import logging
import csv
from logging.handlers import TimedRotatingFileHandler
from uuid import uuid4
import unicodedata

# 環境変数
from dotenv import load_dotenv

# UI
from uuid import uuid4
import streamlit as st

# （任意）Word操作を使う場合のみ。未使用なら削除OK
try:
    from docx import Document  # python-docx
except Exception:
    Document = None  # 未使用なら問題なし

# データ読み込み/分割/ベクターストア
from langchain_community.document_loaders import WebBaseLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document as LCDocument

# 自作定数
import constants as ct

############################################################
# 設定関連
############################################################
# 「.env」ファイルで定義した環境変数の読み込み
load_dotenv()


############################################################
# 関数定義
############################################################

def initialize():
    initialize_session_state()
    initialize_session_id()
    log = initialize_logger()         # ← 関数の戻り値を使う
    log.info("initialize: start")
    initialize_retriever()
    log.info("initialize: retriever ready")

def initialize_logger():
    os.makedirs(ct.LOG_DIR_PATH, exist_ok=True)

    logger = logging.getLogger(ct.LOGGER_NAME)
    if logger.handlers:               # ← 二重付与防止
        return logger

    log_handler = TimedRotatingFileHandler(
        os.path.join(ct.LOG_DIR_PATH, ct.LOG_FILE),
        when="D",
        encoding="utf8",
        # 任意：世代管理したいなら constants に LOG_BACKUP_COUNT を用意
        backupCount=getattr(ct, "LOG_BACKUP_COUNT", 7),
    )
    formatter = logging.Formatter(
        f"[%(levelname)s] %(asctime)s line %(lineno)s, in %(funcName)s, "
        f"session_id={st.session_state.get('session_id', '-')}: %(message)s"
    )
    log_handler.setFormatter(formatter)

    logger.setLevel(logging.INFO)
    logger.addHandler(log_handler)
    logger.propagate = False          # ← ここで伝播を止める（重複出力防止）
    return logger

def initialize_retriever():
    """
    画面読み込み時にRAGのRetriever（ベクターストアから検索するオブジェクト）を作成
    """
    log = logging.getLogger(ct.LOGGER_NAME)

    # 既に作成済みならスキップ
    if "retriever" in st.session_state and st.session_state.retriever is not None:
        return

    # データ読み込み
    docs_all = load_data_sources()

    # Windows用の文字正規化
    for d in docs_all:
        d.page_content = adjust_string(d.page_content)
        for k in list(d.metadata.keys()):
            d.metadata[k] = adjust_string(d.metadata[k])

    # 0件なら retriever 無効化して戻る（落ちないように）
    if not docs_all:
        log.warning("initialize_retriever: no documents loaded.")
        st.session_state.retriever = None
        return

    # チャンク分割
    splitter = CharacterTextSplitter(
        chunk_size=ct.CHUNK_SIZE,
        chunk_overlap=ct.CHUNK_OVERLAP,
        separator="\n",
    )
    chunks = []
    for d in docs_all:
        if d.metadata.get("doc_type") == "csv_merged":
            chunks.append(d)
        else:
            chunks.extend(splitter.split_documents([d]))


    # 上限が設定されていればカット（検証・軽量化用）
    if getattr(ct, "MAX_CHUNKS", 0) and ct.MAX_CHUNKS > 0:
        chunks = chunks[: ct.MAX_CHUNKS]

    log.info(f"initialize_retriever: loaded={len(docs_all)} -> chunks={len(chunks)}")

    # 埋め込み
    embeddings = OpenAIEmbeddings(model=getattr(ct, "EMBED_MODEL", "text-embedding-3-small"))

    # 永続化付き Chroma
    db = Chroma.from_documents(
        chunks,
        embedding=embeddings,
        persist_directory=getattr(ct, "CHROMA_DIR", ".chroma"),
        collection_name=getattr(ct, "CHROMA_COLLECTION", "company_inner_search"),
    )
    try:
        db.persist()
    except Exception:
        pass

    # retriever 構築（変数化）
    k = getattr(ct, "TOP_K", 5)
    retriever_type = getattr(ct, "RETRIEVER_TYPE", "mmr").lower()

    if retriever_type == "mmr":
        fetch_k = max(k * getattr(ct, "MMR_FETCH_K_MULTIPLIER", 5), 20)
        lambda_mult = getattr(ct, "MMR_LAMBDA_MULT", 0.5)
        st.session_state.retriever = db.as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": k,
                "fetch_k": fetch_k,     # 候補を広く拾って多様化
                "lambda_mult": lambda_mult,
            },
        )
    else:
        # similarity 検索
        st.session_state.retriever = db.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k},
        )

    log.info(
        f"initialize_retriever: retriever ready "
        f"(type={retriever_type}, k={k})"
    )

def initialize_session_state():
    """
    初期化データの用意
    """
    if "messages" not in st.session_state:
        # 「表示用」の会話ログを順次格納するリストを用意
        st.session_state.messages = []
        # 「LLMとのやりとり用」の会話ログを順次格納するリストを用意
        st.session_state.chat_history = []

def initialize_session_id():
    """セッションIDの作成（無ければ発行）"""
    if "session_id" not in st.session_state:
        st.session_state.session_id = uuid4().hex

def load_data_sources():
    """
    RAGの参照先となるデータソースの読み込み（ローカル優先。WEBは既定で無効）
    """
    logger = logging.getLogger(ct.LOGGER_NAME)

    docs_local = []
    docs_web = []

    # --- data ルート決定（constants の絶対パスが基本） ---
    data_root = ct.RAG_TOP_FOLDER_PATH
    if not os.path.isdir(data_root):
        # 念のためフォールバック：このファイルの隣の data、さらに CWD/data
        here = os.path.dirname(os.path.abspath(__file__))
        cand1 = os.path.join(here, "data")
        cand2 = os.path.join(os.getcwd(), "data")
        for cand in (cand1, cand2):
            if os.path.isdir(cand):
                data_root = cand
                break

    if not os.path.isdir(data_root):
        logger.warning(f"データフォルダが見つかりませんでした: {ct.RAG_TOP_FOLDER_PATH}")
    else:
        logger.info(f"ローカルデータ読み込み開始: {data_root}")
        recursive_file_check(data_root, docs_local)
        logger.info(f"ローカル読込: {len(docs_local)} 件")

    # --- WEB読み込み（既定OFF） ---
    if getattr(ct, "WEB_SOURCES_ENABLED", False) and getattr(ct, "WEB_URL_LOAD_TARGETS", None):
        for web_url in ct.WEB_URL_LOAD_TARGETS:
            try:
                loader = WebBaseLoader(web_url)
                web_docs = loader.load()
                docs_web.extend(web_docs)
            except Exception as e:
                logger.warning(f"WEB読込失敗: {web_url} -> {e}")
        logger.info(f"WEB読込: {len(docs_web)} 件（有効時のみ）")
    else:
        logger.info("WEBソース読み込みは無効化（WEB_SOURCES_ENABLED=False）。")

    total = len(docs_local) + len(docs_web)
    logger.info(f"読み込み合計: local={len(docs_local)}, web={len(docs_web)}, total={total}")

    # ★ ローカル優先で結合（WEBは無効なら0）
    return docs_local + docs_web

def recursive_file_check(path, docs_all):
    """
    RAGの参照先となるデータソースの読み込み

    Args:
        path: 読み込み対象のファイル/フォルダのパス
        docs_all: データソースを格納する用のリスト
    """
    # パスがフォルダかどうかを確認
    if os.path.isdir(path):
        # フォルダの場合、フォルダ内のファイル/フォルダ名の一覧を取得
        files = os.listdir(path)
        # 各ファイル/フォルダに対して処理
        for file in files:
            # ファイル/フォルダ名だけでなく、フルパスを取得
            full_path = os.path.join(path, file)
            # フルパスを渡し、再帰的にファイル読み込みの関数を実行
            recursive_file_check(full_path, docs_all)
    else:
        # パスがファイルの場合、ファイル読み込み
        file_load(path, docs_all)


def file_load(path, docs_all):
    file_extension = os.path.splitext(path)[1].lower()

    # まずは既定マップにある拡張子のみ
    if file_extension in ct.SUPPORTED_EXTENSIONS:
        # ---- CSV: 1ファイル=1ドキュメントに統合 ----
        if file_extension == ".csv":
            docs_all.extend(load_and_merge_csv(path))
            return

        # ---- TXT: 文字コードフォールバック ----
        if file_extension == ".txt":
            enc_trials = ["utf-8", "utf-8-sig", "cp932", "shift_jis"]
            last_err = None
            for enc in enc_trials:
                try:
                    loader = TextLoader(path, encoding=enc)
                    docs = loader.load()
                    logging.getLogger(ct.LOGGER_NAME).info(
                        f"TXT loaded with encoding={enc}: {path}"
                    )
                    docs_all.extend(docs)
                    return
                except Exception as e:
                    last_err = e
                    continue
            raise RuntimeError(
                f"Failed to load text with encodings {enc_trials}: {path}"
            ) from last_err

        loader_factory = ct.SUPPORTED_EXTENSIONS[file_extension]
        loader = loader_factory(path) if callable(loader_factory) else loader_factory(path)
        docs = loader.load()
        docs_all.extend(docs)

def load_and_merge_csv(path):
    """CSV を読み、各行を箇条書きに正規化して 1 ドキュメントへ統合"""
    enc_trials = ["utf-8", "utf-8-sig", "cp932", "shift_jis"]
    rows = None
    last_err = None
    for enc in enc_trials:
        try:
            with open(path, "r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            break
        except Exception as e:
            last_err = e
            continue
    if rows is None:
        raise RuntimeError(
            f"Failed to read CSV with encodings {enc_trials}: {path}"
        ) from last_err

    # ヘッダ名のゆらぎ対応
    def pick(d, keys):
        # 優先順 keys のいずれかを返す（大文字小文字ゆるめ）
        for k in keys:
            if k in d and d[k]:
                return str(d[k]).strip()
        lower = {k.lower(): k for k in d.keys()}
        for k in keys:
            lk = k.lower()
            if lk in lower and d[lower[lk]]:
                return str(d[lower[lk]]).strip()
        return ""

    name_keys  = ["氏名", "名前", "name"]
    dept_keys  = ["部署", "部門", "部局", "department"]
    title_keys = ["役職", "職位", "title"]
    mail_keys  = ["メール", "メールアドレス", "email"]
    id_keys    = ["社員ID", "従業員ID", "employee_id", "ID"]

    lines = []
    for r in rows:
        name  = pick(r, name_keys)
        dept  = pick(r, dept_keys)
        title = pick(r, title_keys)
        mail  = pick(r, mail_keys)
        empid = pick(r, id_keys)

        parts = []
        if name:  parts.append(f"氏名:{name}")
        if dept:  parts.append(f"部署:{dept}")
        if title: parts.append(f"役職:{title}")
        if mail:  parts.append(f"メール:{mail}")
        if empid: parts.append(f"社員ID:{empid}")

        if parts:
            lines.append("- " + " / ".join(parts))

    header = f"従業員データ（{os.path.basename(path)}）"
    text = header + "\n" + "\n".join(lines)

    meta = {
        "source": path,
        "doc_type": "csv_merged",
        "row_count": len(rows),
    }
    return [LCDocument(page_content=text, metadata=meta)]

def adjust_string(s):
    """
    Windows環境でRAGが正常動作するよう、Unicode正規化と
    cp932 で表現できない文字の除去を行う。
    文字列以外はそのまま返す。
    """
    if not isinstance(s, str):
        return s
    if sys.platform.startswith("win"):
        try:
            s = unicodedata.normalize("NFC", s)
            s = s.encode("cp932", "ignore").decode("cp932")
        except Exception:
            # 何かあっても落とさない
            pass
    return s