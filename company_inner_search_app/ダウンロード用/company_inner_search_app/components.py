"""
このファイルは、画面表示に特化した関数定義のファイルです。
"""

############################################################
# ライブラリの読み込み
############################################################
import streamlit as st
import constants as ct
import utils

# ヘルパー関数を追加
def _fmt_source_with_page(meta: dict) -> str:
    """metadata から 'source' と 'page' を取り、ユーザ向けの表示文字列を作る"""
    src = meta.get("source", "")
    if not src:
        return ""
    page = meta.get("page", None)
    if isinstance(page, int):
        return f"{src}（p.{page + 1}）"
    return src


# ---- サイドバー：アプリタイトル（メインと重複させない） ----
def display_app_title():
    st.markdown(f"## {ct.APP_NAME}")

# ---- サイドバー：利用目的ラジオ（常にここで1回だけ）----
def display_select_mode(label="利用目的", key="mode_radio_sb"):
    # 既定値を先に入れておく（キー未作成時のみ）
    if key not in st.session_state:
        st.session_state[key] = ct.ANSWER_MODE_2  # 既定は「社内問い合わせ」

    option = st.radio(
        label,
        [ct.ANSWER_MODE_1, ct.ANSWER_MODE_2],
        key=key,  # ← 固定キー。main側でもこのキー名を使う
    )
    st.session_state.mode = option
    return option

# ---- サイドバー：「使い方」（常に両方の説明を表示）----
def display_sidebar_help():
    st.markdown(
        f"""
**「{ct.ANSWER_MODE_1}」を選択した場合**  
入力内容と関連性が高い社内文書のありかを検索できます。  

**入力例**  
社員の育成方針に関するMTGの議事録

---

**「{ct.ANSWER_MODE_2}」を選択した場合**  
質問・要望に対して、社内文書の情報をもとに回答を得られます。  

**入力例**  
人事部に所属している従業員情報を一覧化して
"""
    )

# ---- メイン：初回の挨拶（注意書きを直下に追加）----
def display_initial_ai_message():
    with st.chat_message("assistant"):
        st.markdown(
            "こんにちは。私は社内文書の情報をもとに回答する生成AIチャットボットです。"
            "左のサイドバーで利用目的を選び、画面下部のチャット欄からメッセージを送信してください。"
        )
        st.info("具体的に入力したほうが期待通りの回答を得やすいです。")

# ---- メイン：会話ログの表示（堅牢化）----
def display_conversation_log():
    for message in st.session_state.get("messages", []):
        role = message.get("role", "assistant")
        with st.chat_message(role):
            if role == "user":
                st.markdown(message.get("content", ""))
                continue

            content = message.get("content", {})
            if isinstance(content, str):
                st.markdown(content)
                continue

            mode = content.get("mode")

            # ===== 社内文書検索（パス提示系） =====
            if mode == ct.ANSWER_MODE_1:
                if content.get("main_message"):
                    st.markdown(content["main_message"])

                if not content.get("no_file_path_flg", False):
                    main_path = content.get("main_file_path")
                    if main_path:
                        st.success(main_path, icon=utils.get_source_icon(main_path))

                    if content.get("sub_message"):
                        st.markdown(content["sub_message"])
                    for sub in content.get("sub_choices", []):
                        src = sub.get("source") if isinstance(sub, dict) else sub
                        if src:
                            st.info(src, icon=utils.get_source_icon(src))
                else:
                    st.markdown(content.get("answer", ""))

            # ===== 社内問い合わせ（回答＋情報源） =====
            else:
                st.markdown(content.get("answer", ""))
                file_list = content.get("file_info_list") or []
                if file_list:
                    st.divider()
                    st.markdown(f"##### {content.get('message', '情報源')}")
                    for src in file_list:
                        if src:
                            st.info(src, icon=utils.get_source_icon(src))

# ---- LLM表示：社内文書検索 ----
def display_search_llm_response(llm_response):
    """
    「社内文書検索」モードにおける LLM レスポンスを表示（ページ番号対応）。
    """
    docs = llm_response.get("context", []) or []

    # メイン候補
    main_msg = "入力内容に関する情報は、以下のファイルに含まれている可能性があります。"
    st.markdown(main_msg)

    if docs:
        main_doc = docs[0]
        label_main = _fmt_source_with_page(getattr(main_doc, "metadata", {}))
        if label_main:
            st.success(label_main, icon=utils.get_source_icon(label_main))

        # サブ候補（2番手以降）
        if len(docs) > 1:
            st.markdown("関連する候補もあります：")
            for sub_doc in docs[1:]:
                label_sub = _fmt_source_with_page(getattr(sub_doc, "metadata", {}))
                if label_sub:
                    st.info(label_sub, icon=utils.get_source_icon(label_sub))
    else:
        # 参照なし（ヒット無し）の場合は、回答テキストが来ていれば表示
        st.markdown(llm_response.get("answer", ""))

    # 既存の会話ログ形式に合わせて返す（互換維持）
    content = {
        "mode": ct.ANSWER_MODE_1,
        "main_message": main_msg,
    }
    if docs:
        content["main_file_path"] = getattr(docs[0], "metadata", {}).get("source", "")
        if "page" in getattr(docs[0], "metadata", {}):
            content["main_page_number"] = getattr(docs[0], "metadata", {}).get("page", None)
        # サブ候補（UI 表示は上でやっているが、ログにも残す）
        subs = []
        for d in docs[1:]:
            meta = getattr(d, "metadata", {})
            label = meta.get("source", "")
            if "page" in meta and isinstance(meta["page"], int):
                label = f"{label}（p.{meta['page'] + 1}）"
            subs.append({"source": label})
        if subs:
            content["sub_message"] = "関連候補"
            content["sub_choices"] = subs
    else:
        content["no_file_path_flg"] = True
        content["answer"] = llm_response.get("answer", "")

    return content

# ---- LLM表示：社内問い合わせ ----
def display_contact_llm_response(llm_response):
    """
    「社内問い合わせ」モード用の表示。
    回答テキスト＋参照情報源（パス/URL とページ）を整形して返す。
    """
    answer = llm_response.get("answer", "")
    docs = llm_response.get("context", []) or []

    # 情報源（重複を排除し、ページ番号があれば付与）
    file_info_list = []
    seen = set()
    for d in docs:
        try:
            label = _fmt_source_with_page(getattr(d, "metadata", {}))
        except Exception:
            label = ""
        if label and label not in seen:
            seen.add(label)
            file_info_list.append(label)

    # 画面表示
    st.markdown(answer)
    if file_info_list:
        st.divider()
        st.markdown("##### 情報源")
        for src in file_info_list:
            st.info(src, icon=utils.get_source_icon(src))

    # 会話ログへ積むための構造（既存の呼び出しと互換）
    return {
        "mode": ct.ANSWER_MODE_2,
        "answer": answer,
        "message": "情報源",
        "file_info_list": file_info_list,
    }