"""
このファイルは、画面表示以外の様々な関数定義のファイルです。
"""

# .env 読み込み（存在しない環境でも安全にスキップ）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ModuleNotFoundError:
    pass

############################################################
# ライブラリの読み込み
############################################################
import os
import logging
import streamlit as st

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain

import constants as ct

logger = logging.getLogger(ct.LOGGER_NAME)

############################################################
# ユーティリティ
############################################################
def get_source_icon(source: str) -> str:
    """参照元に応じたアイコンを返す"""
    if isinstance(source, str) and source.startswith("http"):
        return ct.LINK_SOURCE_ICON
    return ct.DOC_SOURCE_ICON

def build_error_message(message: str) -> str:
    """共通のエラー文を合成"""
    return "\n".join([message, ct.COMMON_ERROR_MESSAGE])

def _get_llm() -> ChatOpenAI:
    """LLMインスタンス作成（モデル名・温度は constants から取得、無ければ既定値）"""
    model = getattr(ct, "MODEL", "gpt-4o-mini")
    temperature = float(getattr(ct, "TEMPERATURE", 0.2))
    timeout = int(getattr(ct, "OPENAI_TIMEOUT", 60))
    # langchain_openai は model=... で指定（model_name ではない）
    return ChatOpenAI(model=model, temperature=temperature, timeout=timeout)

def _safe_chat_history(max_turns: int = 6):
    """
    表示用ログ(st.session_state.messages)から LangChain 形式の履歴を構築。
    （壊れていても安全に空配列を返す）
    """
    msgs = []
    for m in st.session_state.get("messages", []):
        role = m.get("role")
        if role == "user":
            msgs.append(HumanMessage(content=m.get("content", "")))
        elif role == "assistant":
            c = m.get("content", "")
            # アシスタント側は dict のことがあるので answer を優先して拾う
            if isinstance(c, dict):
                c = c.get("answer", "") or str(c)
            msgs.append(AIMessage(content=c))
    return msgs[-max_turns:]

############################################################
# プロンプト（constants の文面を活用）
############################################################
# クエリ言い換え（履歴を踏まえた検索クエリを生成）
_CONTEXTUALIZE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", getattr(ct, "SYSTEM_PROMPT_CREATE_INDEPENDENT_TEXT",
                        "会話履歴と質問から検索に最適な日本語クエリを1行で出力してください。")),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)

# 回答生成：モードに応じて後で差し替え（DOC_SEARCH / INQUIRY）
def _qa_prompt_for_mode(mode: str) -> ChatPromptTemplate:
    if mode == getattr(ct, "ANSWER_MODE_1", "社内文書検索"):
        sys = getattr(ct, "SYSTEM_PROMPT_DOC_SEARCH",
                    "与えられたコンテキストだけを根拠に、関連ドキュメントの所在を日本語で端的に示してください。")
    else:
        sys = getattr(ct, "SYSTEM_PROMPT_INQUIRY",
                    "与えられたコンテキストだけを根拠に、質問へ日本語で簡潔かつ正確に回答してください。"
                    "コンテキストに無いことは『わかりません』と述べてください。")
    return ChatPromptTemplate.from_messages(
        [
            ("system", sys),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )

############################################################
# 主要関数
############################################################
def get_llm_response(chat_message: str) -> dict:
    """
    画面側から呼ばれるエントリポイント。
    必ず {'answer': <str>, 'context': <list[Document]>} を返す。
    """
    if not chat_message or not chat_message.strip():
        return {"answer": "入力が空です。内容を具体的に入力してください。", "context": []}

    retriever = st.session_state.get("retriever")
    if retriever is None:
        raise RuntimeError("Retriever が初期化されていません。initialize() が完了しているか確認してください。")

    llm = _get_llm()
    chat_history = _safe_chat_history()

    # 履歴対応リトリーバ（質問の言い換え）
    hist_aware_ret = create_history_aware_retriever(
        llm=llm,
        retriever=retriever,
        prompt=_CONTEXTUALIZE_PROMPT,
    )

    # 回答プロンプト（モード別）
    mode = st.session_state.get("mode", getattr(ct, "ANSWER_MODE_2", "社内問い合わせ"))
    qa_prompt = _qa_prompt_for_mode(mode)

    # ドキュメントを詰めて回答生成
    stuff_chain = create_stuff_documents_chain(llm=llm, prompt=qa_prompt)

    # RAG（検索→詰め込み→回答）
    rag_chain = create_retrieval_chain(hist_aware_ret, stuff_chain)

    try:
        result = rag_chain.invoke({"input": chat_message, "chat_history": chat_history})
        # 期待形：{'answer': str, 'context': list[Document], ...}
        answer = result.get("answer", "")
        context = result.get("context", []) or []
        if not isinstance(context, list):
            context = list(context)
        return {"answer": answer, "context": context}
    except Exception as e:
        logger.exception(e)
        # 例外は main 側で拾って画面に出す想定
        raise