import streamlit as st
import google.generativeai as genai
import sqlite3
import os
from dotenv import load_dotenv
from google.api_core import retry
import time
from pathlib import Path
from datetime import datetime
import random

# データベースファイルのパスを設定
def get_db_path():
    if 'STREAMLIT_SHARING_MODE' in os.environ:
        # Streamlit Cloud環境での保存先
        return Path.home() / '.streamlit' / 'learning_log.db'
    else:
        # ローカル環境での保存先
        return Path(__file__).parent / 'learning_log.db'

# データベースの初期化関数
def init_db():
    db_path = get_db_path()
    # データベースディレクトリの作成
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        
        # 学習ログテーブルの作成
        c.execute('''
            CREATE TABLE IF NOT EXISTS learning_log
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
             question TEXT,
             user_answer TEXT,
             correct_answer TEXT,
             is_correct BOOLEAN,
             genre TEXT)
        ''')
        
        # ジャンルごとの統計テーブル
        c.execute('''
            CREATE TABLE IF NOT EXISTS genre_stats
            (genre TEXT PRIMARY KEY,
             total_questions INTEGER DEFAULT 0,
             correct_answers INTEGER DEFAULT 0,
             last_updated DATETIME DEFAULT CURRENT_TIMESTAMP)
        ''')
        
        # 初期ジャンルの登録
        genres = [
            "古代（縄文・弥生・古墳時代）",
            "飛鳥・奈良時代",
            "平安時代",
            "鎌倉時代",
            "室町時代",
            "安土桃山時代",
            "江戸時代",
            "明治時代",
            "大正時代",
            "昭和時代",
            "平成・令和時代"
        ]
        
        for genre in genres:
            c.execute('''
                INSERT OR IGNORE INTO genre_stats (genre, total_questions, correct_answers)
                VALUES (?, 0, 0)
            ''', (genre,))
        
        conn.commit()
        
    except sqlite3.Error as e:
        st.error(f"データベースの初期化中にエラーが発生しました: {str(e)}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()
    return True

# ジャンルの正答率を取得
def get_genre_stats():
    conn = sqlite3.connect('learning_log.db')
    c = conn.cursor()
    c.execute('''
        SELECT genre, 
               total_questions, 
               correct_answers,
               CASE 
                   WHEN total_questions > 0 
                   THEN ROUND(CAST(correct_answers AS FLOAT) / total_questions * 100, 2)
                   ELSE 0 
               END as accuracy
        FROM genre_stats
        ORDER BY accuracy ASC
    ''')
    stats = c.fetchall()
    conn.close()
    return stats

# ジャンルの統計を更新
def update_genre_stats(genre, is_correct):
    conn = sqlite3.connect('learning_log.db')
    c = conn.cursor()
    c.execute('''
        UPDATE genre_stats 
        SET total_questions = total_questions + 1,
            correct_answers = correct_answers + ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE genre = ?
    ''', (1 if is_correct else 0, genre))
    conn.commit()
    conn.close()

# 問題生成時のジャンル選択（正答率が低いジャンルを優先）
def select_genre():
    stats = get_genre_stats()
    # 正答率が50%未満のジャンルを抽出
    weak_genres = [genre for genre, total, correct, accuracy in stats if accuracy < 50 and total > 0]
    
    if weak_genres and random.random() < 0.7:  # 70%の確率で苦手ジャンルから出題
        return random.choice(weak_genres)
    else:  # それ以外の場合はランダムに選択
        return random.choice([genre for genre, _, _, _ in stats])

# セッション状態の初期化
if 'api_key_set' not in st.session_state:
    st.session_state.api_key_set = False
if 'current_question' not in st.session_state:
    st.session_state.current_question = None
if 'correct_answer' not in st.session_state:
    st.session_state.correct_answer = None

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

# データベースの初期化
init_db()

# メインページのタイトル
st.title("PP - AIパーソナル学習アシスタント")

# サイドバーでモード選択
st.sidebar.title("学習モード選択")
mode = st.sidebar.radio(
    "モードを選択してください：",
    ["4択クイズ", "記述式クイズ", "学習ログ"]
)

# デバッグモードの切り替え
debug_mode = st.sidebar.checkbox("デバッグモード", value=False, key='debug_mode')

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

@retry.Retry(predicate=retry.if_exception_type(Exception))
def generate_quiz_with_retry():
    try:
        selected_genre = select_genre()
        prompt = f"""
        日本の歴史の「{selected_genre}」に関する4択問題を1つ生成してください。
        以下の形式で出力してください：
        質問：
        選択肢1：
        選択肢2：
        選択肢3：
        選択肢4：
        正解：（数字のみ）
        ジャンル：{selected_genre}
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
            return None, None
            
        if st.session_state.get('debug_mode', False):
            st.write("生成された内容:", response.text)
        
        return response.text, selected_genre
    except Exception as e:
        st.error(f"問題生成中にエラーが発生しました: {str(e)}")
        return None, None

def quiz_mode():
    # 統計情報の表示
    st.sidebar.subheader("ジャンル別正答率")
    stats = get_genre_stats()
    for genre, total, correct, accuracy in stats:
        if total > 0:
            st.sidebar.text(f"{genre}: {accuracy}% ({correct}/{total})")

    if st.button("新しい問題を生成"):
        quiz_text, genre = generate_quiz_with_retry()
        if quiz_text:
            try:
                lines = [line.strip() for line in quiz_text.split('\n') if line.strip()]
                
                question = next((line.replace('質問：', '').strip() for line in lines if '質問：' in line), None)
                options = [line.split('：')[1].strip() for line in lines if '選択肢' in line]
                correct = int(next((line.replace('正解：', '').strip() for line in lines if '正解：' in line), None))
                
                if question and len(options) == 4 and correct:
                    st.session_state.current_question = question
                    st.session_state.correct_answer = correct
                    st.session_state.options = options
                    st.session_state.current_genre = genre
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
                INSERT INTO learning_log (question, user_answer, correct_answer, is_correct, genre)
                VALUES (?, ?, ?, ?, ?)
            """, (st.session_state.current_question, user_answer, 
                  st.session_state.options[st.session_state.correct_answer-1], 
                  is_correct, st.session_state.current_genre))
            conn.commit()
            conn.close()
            
            # ジャンルの統計を更新
            update_genre_stats(st.session_state.current_genre, is_correct)
            
            if is_correct:
                st.success("正解です！")
            else:
                st.error(f"不正解です。正解は: {st.session_state.options[st.session_state.correct_answer-1]}")

def written_quiz_mode():
    # 統計情報の表示
    st.sidebar.subheader("ジャンル別正答率")
    stats = get_genre_stats()
    for genre, total, correct, accuracy in stats:
        if total > 0:
            st.sidebar.text(f"{genre}: {accuracy}% ({correct}/{total})")

    if st.button("新しい問題を生成"):
        with st.spinner('記述式問題を生成中...'):
            quiz_text, genre = generate_quiz_with_retry()
            if quiz_text:
                try:
                    lines = [line.strip() for line in quiz_text.split('\n') if line.strip()]
                    
                    question = next((line.replace('質問：', '').strip() for line in lines if '質問：' in line), None)
                    answer = next((line.replace('正解：', '').strip() for line in lines if '正解：' in line), None)
                    
                    if question and answer:
                        st.session_state.current_question = question
                        st.session_state.correct_answer = answer
                        st.session_state.current_genre = genre
                    else:
                        st.error("問題の形式が正しくありません。もう一度生成してください。")
                except Exception as e:
                    st.error(f"問題の解析中にエラーが発生しました: {str(e)}")

    if st.session_state.current_question:
        st.write(st.session_state.current_question)
        user_answer = st.text_area("答えを入力してください：")
        
        if st.button("回答する"):
            # 結果をデータベースに保存
            conn = sqlite3.connect('learning_log.db')
            c = conn.cursor()
            c.execute("""
                INSERT INTO learning_log (question, user_answer, correct_answer, is_correct, genre)
                VALUES (?, ?, ?, ?, ?)
            """, (st.session_state.current_question, user_answer, 
                  st.session_state.correct_answer, 
                  user_answer.strip().lower() == st.session_state.correct_answer.strip().lower(),
                  st.session_state.current_genre))
            conn.commit()
            conn.close()
            
            # ジャンルの統計を更新
            is_correct = user_answer.strip().lower() == st.session_state.correct_answer.strip().lower()
            update_genre_stats(st.session_state.current_genre, is_correct)
            
            st.write("模範解答:", st.session_state.correct_answer)
            
            if is_correct:
                st.success("正解です！")
            else:
                st.error("不正解です。")

def show_learning_log():
    st.subheader("学習履歴")
    
    try:
        db_path = get_db_path()
        if not db_path.exists():
            st.info("学習履歴はまだありません。")
            return
            
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        logs = c.execute("""
            SELECT timestamp, question, user_answer, correct_answer, is_correct, genre
            FROM learning_log 
            ORDER BY timestamp DESC
        """).fetchall()
        
        if not logs:
            st.info("学習履歴はまだありません。")
            return
            
        for log in logs:
            with st.expander(f"{log[5]} - {log[1][:50]}..."):
                st.write(f"回答日時: {log[0]}")
                st.write(f"ジャンル: {log[5]}")
                st.write(f"問題: {log[1]}")
                st.write(f"あなたの回答: {log[2]}")
                st.write(f"正解: {log[3]}")
                st.write("結果: " + ("正解" if log[4] else "不正解"))
                
    except sqlite3.Error as e:
        st.error(f"学習履歴の取得中にエラーが発生しました: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

# モードに応じた表示
if mode == "4択クイズ":
    quiz_mode()
elif mode == "記述式クイズ":
    written_quiz_mode()
else:
    show_learning_log()
