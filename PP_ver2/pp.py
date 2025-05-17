import streamlit as st
import google.generativeai as genai
import sqlite3
import os
from dotenv import load_dotenv
from google.api_core import retry
import time
from pathlib import Path

# セッション状態の初期化
if 'api_key_set' not in st.session_state:
    st.session_state.api_key_set = False

# 環境変数の読み込み
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# APIキーの取得とデバッグ情報
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

# Streamlit Cloudでの実行時の設定
if not GOOGLE_API_KEY and 'STREAMLIT_SHARING_MODE' in os.environ:
    # Streamlit Cloudの環境変数から取得
    GOOGLE_API_KEY = st.secrets.get("GOOGLE_API_KEY")
    if GOOGLE_API_KEY:
        st.session_state.api_key_set = True

# ローカル開発環境での実行時の設定
if not GOOGLE_API_KEY and not st.session_state.api_key_set:
    st.warning("このアプリはStreamlit Cloudでの実行を推奨します。")
    st.info("ローカルで実行する場合は、以下のいずれかの方法でAPIキーを設定してください：")
    st.info("以下の入力欄にAPIキーを直接入力")
    
    # 直接入力オプション
    api_key_input = st.text_input("Google API Keyを直接入力：", type="password")
    if api_key_input:
        GOOGLE_API_KEY = api_key_input
        st.session_state.api_key_set = True
    else:
        st.stop()

# Gemini APIの設定
genai.configure(api_key=GOOGLE_API_KEY)

# 利用可能なモデルの確認
try:
    models = genai.list_models()
    model_name = None
    for model in models:
        if 'generateContent' in model.supported_generation_methods:
            model_name = model.name
            break
    
    if not model_name:
        st.error("利用可能なGenerative AIモデルが見つかりませんでした。")
        st.stop()
        
except Exception as e:
    st.error(f"モデルリストの取得中にエラーが発生しました: {str(e)}")
    st.stop()

# データベースの初期化
def init_db():
    conn = sqlite3.connect('learning_log.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS learning_log
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
         question TEXT,
         user_answer TEXT,
         correct_answer TEXT,
         is_correct BOOLEAN)
    ''')
    conn.commit()
    conn.close()

# アプリの状態管理
if 'current_question' not in st.session_state:
    st.session_state.current_question = None
if 'correct_answer' not in st.session_state:
    st.session_state.correct_answer = None

# データベースの初期化
init_db()

# サイドバーでモード選択
st.sidebar.title("学習モード選択")
mode = st.sidebar.radio(
    "モードを選択してください：",
    ["4択クイズ", "記述式クイズ", "学習ログ"]
)

# メインページのタイトル
st.title("PP - AIパーソナル学習アシスタント")

@retry.Retry(predicate=retry.if_exception_type(Exception))
def generate_quiz_with_retry():
    prompt = """
    日本の歴史に関する4択問題を1つ生成してください。
    以下の形式で出力してください：
    質問：
    選択肢1：
    選択肢2：
    選択肢3：
    選択肢4：
    正解：（数字のみ）
    """
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")  # Gemini 2.0 Flashモデルを使用
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 40,
                "max_output_tokens": 1024,
            }
        )
        return response.text if response.text else None
    except Exception as e:
        st.error(f"問題生成中にエラーが発生しました: {str(e)}")
        return None

def generate_quiz():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with st.spinner('問題を生成中です...'):
                result = generate_quiz_with_retry()
                if result:
                    return result
                time.sleep(1)  # 短い待機時間を設定
        except Exception as e:
            if attempt < max_retries - 1:
                st.warning(f"再試行中... ({attempt + 1}/{max_retries})")
                time.sleep(2)  # リトライ前の待機時間
            else:
                st.error("問題の生成に失敗しました。しばらく待ってから再度お試しください。")
                return None
    return None

def quiz_mode():
    if st.button("新しい問題を生成"):
        quiz_text = generate_quiz()
        if quiz_text:
            try:
                lines = quiz_text.split('\n')
                lines = [line.strip() for line in lines if line.strip()]  # 空行を除去
                
                question = next((line.replace('質問：', '').strip() for line in lines if '質問：' in line), None)
                options = [line.split('：')[1].strip() for line in lines if '選択肢' in line]
                correct = next((int(line.replace('正解：', '').strip()) for line in lines if '正解：' in line), None)
                
                if question and len(options) == 4 and correct:
                    st.session_state.current_question = question
                    st.session_state.correct_answer = correct
                    st.session_state.options = options
                else:
                    st.error("問題の形式が正しくありません。もう一度生成してください。")
            except Exception as e:
                st.error(f"問題の解析中にエラーが発生しました: {str(e)}")

    if st.session_state.current_question:
        st.write(st.session_state.current_question)
        user_answer = st.radio("答えを選んでください：", st.session_state.options)
        
        if st.button("回答する"):
            selected_index = st.session_state.options.index(user_answer) + 1
            is_correct = selected_index == st.session_state.correct_answer
            
            # 結果をデータベースに保存
            conn = sqlite3.connect('learning_log.db')
            c = conn.cursor()
            c.execute("""
                INSERT INTO learning_log (question, user_answer, correct_answer, is_correct)
                VALUES (?, ?, ?, ?)
            """, (st.session_state.current_question, user_answer, 
                  st.session_state.options[st.session_state.correct_answer-1], is_correct))
            conn.commit()
            conn.close()
            
            if is_correct:
                st.success("正解です！")
            else:
                st.error(f"不正解です。正解は: {st.session_state.options[st.session_state.correct_answer-1]}")

# 記述式クイズモード
@retry.Retry(predicate=retry.if_exception_type(Exception))
def generate_written_quiz():
    try:
        prompt = """
        日本の歴史に関する記述式の問題を1つ生成してください。
        必ず以下の形式で出力してください：

        質問：[ここに問題文]
        正解：[ここに解答]

        注意：
        - 質問と正解の形式は厳密に守ってください
        - 質問と正解の前には必ず「質問：」「正解：」というプレフィックスを付けてください
        - 1つの質問と1つの正解のみを生成してください
        """
        
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.7,
                "top_p": 0.8,
                "top_k": 40,
                "max_output_tokens": 1024,
            }
        )
        
        if not response.text:
            st.error("問題の生成に失敗しました。")
            return None
            
        # デバッグモードの場合のみ表示
        if st.session_state.get('debug_mode', False):
            st.write("生成された内容:", response.text)
        
        return response.text
    except Exception as e:
        st.error(f"問題生成中にエラーが発生しました: {str(e)}")
        return None

def written_quiz_mode():
    # デバッグモードの切り替え
    debug_mode = st.sidebar.checkbox("デバッグモード", value=False, key='debug_mode')

    if st.button("新しい問題を生成"):
        with st.spinner('記述式問題を生成中...'):
            quiz_text = generate_written_quiz()
            if quiz_text:
                try:
                    # 改行で分割して空行を除去
                    lines = [line.strip() for line in quiz_text.split('\n') if line.strip()]
                    
                    # デバッグモードの場合のみ表示
                    if debug_mode:
                        st.write("分割された行:", lines)
                    
                    # 質問と正解を探す
                    question = None
                    answer = None
                    
                    for line in lines:
                        if line.startswith('質問：'):
                            question = line.replace('質問：', '').strip()
                        elif line.startswith('正解：'):
                            answer = line.replace('正解：', '').strip()
                    
                    # デバッグモードの場合のみ表示
                    if debug_mode:
                        st.write("抽出された質問:", question)
                        st.write("抽出された回答:", answer)
                    
                    if question and answer:
                        st.session_state.current_question = question
                        st.session_state.correct_answer = answer
                    else:
                        st.error("問題の形式が正しくありません。もう一度生成してください。")
                        st.error("期待される形式：")
                        st.code("質問：[問題文]\n正解：[解答]")
                except Exception as e:
                    st.error(f"問題の解析中にエラーが発生しました: {str(e)}")
                    if debug_mode:
                        st.error("詳細なエラー情報:")
                        st.code(str(e))

    if st.session_state.current_question:
        st.write(st.session_state.current_question)
        user_answer = st.text_area("答えを入力してください：")
        
        if st.button("回答する"):
            # 結果をデータベースに保存
            conn = sqlite3.connect('learning_log.db')
            c = conn.cursor()
            c.execute("""
                INSERT INTO learning_log (question, user_answer, correct_answer, is_correct)
                VALUES (?, ?, ?, ?)
            """, (st.session_state.current_question, user_answer, 
                  st.session_state.correct_answer, 
                  user_answer.strip().lower() == st.session_state.correct_answer.strip().lower()))
            conn.commit()
            conn.close()
            
            st.write("模範解答:", st.session_state.correct_answer)
            
            # 回答の評価（簡易版）
            if user_answer.strip().lower() == st.session_state.correct_answer.strip().lower():
                st.success("正解です！")
            else:
                st.error("不正解です。")

# 学習ログモード
def show_learning_log():
    st.subheader("学習履歴")
    
    conn = sqlite3.connect('learning_log.db')
    c = conn.cursor()
    logs = c.execute("""
        SELECT timestamp, question, user_answer, correct_answer, is_correct 
        FROM learning_log 
        ORDER BY timestamp DESC
    """).fetchall()
    conn.close()
    
    for log in logs:
        with st.expander(f"問題: {log[1][:50]}..."):
            st.write(f"回答日時: {log[0]}")
            st.write(f"あなたの回答: {log[2]}")
            st.write(f"正解: {log[3]}")
            st.write("結果: " + ("正解" if log[4] else "不正解"))

# モードに応じた表示
if mode == "4択クイズ":
    quiz_mode()
elif mode == "記述式クイズ":
    written_quiz_mode()
else:
    show_learning_log()
