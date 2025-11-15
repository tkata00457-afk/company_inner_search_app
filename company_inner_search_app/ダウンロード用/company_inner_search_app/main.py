import os
import streamlit as st

# .env 読み込み（無ければスキップ）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ModuleNotFoundError:
    pass

def get_secret(name: str) -> str:
    v = os.getenv(name)
    if v:
        return v.strip()
    try:
        v = st.secrets.get(name)
    except Exception:
        v = None
    return (v or "").strip()

OPENAI_API_KEY = get_secret("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    st.error("APIキーが設定されていません。 .env か .streamlit/secrets.toml に OPENAI_API_KEY を入れてください。")
    st.stop()
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# ==== ライブラリ ====
import logging
import traceback

import constants as ct
logger = logging.getLogger(ct.LOGGER_NAME)

import components as cn
import utils
from initialize import initialize

# ==== ページ設定 ====
st.set_page_config(
    page_title=ct.APP_NAME,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==== 初期化 ====
try:
    initialize()
except Exception as e:
    logger.exception(e)
    st.error(utils.build_error_message(ct.INITIALIZE_ERROR_MESSAGE), icon=ct.ERROR_ICON)
    st.exception(e)
    st.code(traceback.format_exc())
    st.stop()

# ==== 画面構成（タイトル×1／ラジオ×1）====
# メイン：タイトル
cn.display_app_title()

# サイドバー：利用目的＋使い方（ここで1回だけ）
with st.sidebar:
    st.subheader("利用目的")
    selected_mode = cn.display_select_mode(key="mode_radio_sb")  # ← componentsと同じキー名
    st.divider()
    st.subheader("使い方")
    cn.display_sidebar_help()

# 初回だけ挨拶＋注意書き
if not st.session_state.get("messages"):
    cn.display_initial_ai_message()

# ==== 会話ログ ====
try:
    cn.display_conversation_log()
except Exception as e:
    logger.error(f"{ct.CONVERSATION_LOG_ERROR_MESSAGE}\n{e}")
    st.error(utils.build_error_message(ct.CONVERSATION_LOG_ERROR_MESSAGE), icon=ct.ERROR_ICON)
    st.stop()

# ==== チャット入力 ====
chat_message = st.chat_input(ct.CHAT_INPUT_HELPER_TEXT)

# ==== 送信時処理 ====
if chat_message:
    logger.info({"message": chat_message, "application_mode": selected_mode})

    with st.chat_message("user"):
        st.markdown(chat_message)

    # 回答生成
    with st.spinner(ct.SPINNER_TEXT):
        try:
            llm_response = utils.get_llm_response(chat_message)
        except Exception as e:
            logger.error(f"{ct.GET_LLM_RESPONSE_ERROR_MESSAGE}\n{e}")
            st.error(utils.build_error_message(ct.GET_LLM_RESPONSE_ERROR_MESSAGE), icon=ct.ERROR_ICON)
            st.stop()

    # 回答表示
    with st.chat_message("assistant"):
        try:
            if selected_mode == ct.ANSWER_MODE_1:
                content = cn.display_search_llm_response(llm_response)
            else:
                content = cn.display_contact_llm_response(llm_response)
            logger.info({"message": content, "application_mode": selected_mode})
        except Exception as e:
            logger.error(f"{ct.DISP_ANSWER_ERROR_MESSAGE}\n{e}")
            st.error(utils.build_error_message(ct.DISP_ANSWER_ERROR_MESSAGE), icon=ct.ERROR_ICON)
            st.stop()

    # ログを追記
    st.session_state.messages.append({"role": "user", "content": chat_message})
    st.session_state.messages.append({"role": "assistant", "content": content})