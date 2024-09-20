import os
from io import BytesIO
import re
import random
import tweepy
from google.cloud import firestore
from datetime import datetime, time, timedelta
import time
import pytz
from flask import Flask, request, render_template, session, redirect, url_for, jsonify
import unicodedata
from twitter_text import parse_tweet
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import requests
from hashlib import md5
import base64
from flask_executor import Executor
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
import tiktoken
from urllib.parse import urljoin, quote_from_bytes, quote
import urllib.parse
from PIL import Image
from urlextract import URLExtract

from functions import chatgpt_functions, run_conversation
from insta import generate_insta
from tweet import generate_tweet

API_KEY = os.getenv('API_KEY')
API_KEY_SECRET = os.getenv('API_KEY_SECRET')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = os.getenv('ACCESS_TOKEN_SECRET')
DATABASE_NAME = os.getenv('DATABASE_NAME')
secret_key = os.getenv('SECRET_KEY')
admin_password = os.environ["ADMIN_PASSWORD"]

REQUIRED_ENV_VARS = [
    "SYSTEM_PROMPT",
    "ORDER_PROMPT",
    "PAINT_PROMPT",
    "AI_MODEL",
    "INSTA_AI_MODEL",
    "TWEET_AI_MODEL",
    "PARTIAL_MATCH_FILTER_WORDS",
    "FULL_MATCH_FILTER_WORDS",
    "READ_TEXT_COUNT",
    "READ_LINKS_COUNT",
    "MAX_TOKEN_NUM",
    "PAINTING_ON",
    "URL_FILTER_ON",
    "DEFAULT_USER_ID",
    "INSTA",
    "INSTA_SYSTEM_PROMPT",
    "INSTA_ORDER_PROMPT",
    "INSTA_MAX_CHARACTER_COUNT",
    "INSTA_OVERLAY_ON",
    "INSTA_OVERLAY_URL",
    "TWEET_REGENERATE_COUNT",
    "TWEET1",
    "TWEET1_SYSTEM_PROMPT",
    "TWEET1_ORDER_PROMPT",
    "TWEET1_MAX_CHARACTER_COUNT",
    "TWEET1_OVERLAY_ON",
    "TWEET1_OVERLAY_URL",
    "TWEET1_REGENERATE_ORDER",
    "TWEET2",
    "TWEET2_SYSTEM_PROMPT",
    "TWEET2_ORDER_PROMPT",
    "TWEET2_MAX_CHARACTER_COUNT",
    "TWEET2_OVERLAY_ON",
    "TWEET2_OVERLAY_URL",
    "TWEET2_REGENERATE_ORDER",
    "TWEET_SQ_PROMPT",
    "BUCKET_NAME",
    "FILE_AGE"
]

DEFAULT_ENV_VARS = {
    'AI_MODEL': 'gpt-4o-mini',
    'INSTA_AI_MODEL': 'chatgpt-4o-latest',
    'TWEET_AI_MODEL': 'chatgpt-4o-latest',
    'SYSTEM_PROMPT': """
あなたはプロの編集者です。あなたはURLからURLリストを読み込んだりページの内容を読み込んだりイラストの生成を行うことができます。
下記の条件に従って読み込んだ文章を編集してください。
条件:
-冒頭に「選んだ」「検索した」等の記載は不要です。記事をなるべく長い感想文にしてください。
-生成した文章で、「描いたイラスト」「イラストにした」「イメージした」「イラスト完成」等、生成したイラストについて言及しないでください。
-記事に合った画像を生成してください。
-イラストを生成する際は英語でプロンプトを生成してください。
-文章の一番最後にハイパーリンク形式で参照元のURLを記載してください。
""",
    'ORDER_PROMPT': """
現在は日本時間の{nowDateStr}です。
次のURLからURLのリストを読み込んで以前とは異なるトピックのニュース記事を選んでください。
次に、選んだ記事のURLのページの内容を読み込んでから条件に従って文章を生成してください。
https://news.yahoo.co.jp/
""",
    'PAINT_PROMPT': """
Draw the above scene in Japanese Moe anime style. Please do not make it look like a live-action movie. Live-action images of people wearing cosplay or character costumes are also prohibited.
Please make the drawing style suitable for Japanese people.
Please give the entire Japanese Moe anime style illustration a sense of pulsation. Give the characters a sense of pulsation by changing their orientation and posture.
""",
    'PARTIAL_MATCH_FILTER_WORDS': 'https://www.yahoo.co.jp/,https://support.yahoo-net.jp/,https://rdr.yahoo.co.jp/,https://yahoo.jp/,https://www.sp-hinan.jp/,https://account.edit.yahoo.co.jp/,https://accounts.yahoo.co.jp/,https://login.yahoo.co.jp/,https://news.yahoo.co.jp/users/,https://news.yahoo.co.jp/purchase,https://news.yahoo.co.jp/settings/,https://news.yahoo.co.jp/flash,https://news.yahoo.co.jp/live,https://news.yahoo.co.jp/expert/,https://news.yahoo.co.jp/original/,https://news.yahoo.co.jp/polls/,https://news.yahoo.co.jp/ranking/,https://news.yahoo.co.jp/paidnews,https://news.yahoo.co.jp/categories,https://news.yahoo.co.jp/topics,https://news.yahoo.co.jp/comment-timeline', 
    'FULL_MATCH_FILTER_WORDS': 'https://news.yahoo.co.jp/',
    'READ_TEXT_COUNT': '2000',
    'READ_LINKS_COUNT': '2000',
    'MAX_TOKEN_NUM': '4000',
    'PAINTING_ON': 'True',
    'URL_FILTER_ON': 'True',
    'DEFAULT_USER_ID': 'default_user_id',
    'INSTA': 'False',
    'INSTA_SYSTEM_PROMPT': """
あなたは、インスタグラムの投稿者です。下記の条件に従ってインスタグラムに記事を投稿してください。 
条件: 
-小学生にもわかりやすく書いてください。 
-出力文は女性を思わせる口語体で記述してください。 
-文脈に応じて、任意の場所で絵文字を使ってください。 
-読み込んだ記事に対して記者の視点や記事の当事者ではなく、記事を読んだ読者視点でブログ記事を生成してください。 
-必ず記事内容に関連するキーワードのハッシュタグ(ツイートのような#を頭に付けた単語)を10個以上入れてください。
-冒頭に「選んだ」「検索した」等の記載は不要です。ブログ記事をなるべく長い感想文にしてください。  
-文章の一番最後にハイパーリンク形式で参照元のURLを記載してください。
""",
    'INSTA_ORDER_PROMPT': """
以下の記事をインスタグラムに記事として再整形して投稿してください。記事をなるべく長い感想文にしてください。必ず記事に関連するキーワードのハッシュタグ(ツイートのような#を頭に付けた単語)を10個以上入れてください。URLを省略せずに必ず含めてください。
""",
    'INSTA_MAX_CHARACTER_COUNT': '99999',
    'INSTA_OVERLAY_ON': 'True',    
    'INSTA_OVERLAY_URL': '',
    'TWEET_REGENERATE_COUNT': '7',
    'TWEET1': 'False',
    'TWEET1_SYSTEM_PROMPT': """
あなたは、Twitter投稿者です。 下記の条件に従ってツイートしてください。 
条件: 
-小学生にもわかりやすく書いてください。 
-出力文 は女性を思わせる口語体で記述してください。 
-文脈に応じて、任意の場所で絵文字を使ってください。絵文字を最低1個は含めてください。
ツイートする文字数は日本語で117文字以内にしてください。 
-ニュースに対して記者の視点やニュースの当事者ではなく、ニュースを読んだ読者視点で感想をツイートしてください。 
-投稿に合ったハッシュタグを付与してください。
-ツイートに参照元のURLを含めないでください。
""",
    'TWEET1_ORDER_PROMPT': """
以下の記事をツイートしてください。 文字数を250文字程度にしてください。
""",
    'TWEET1_MAX_CHARACTER_COUNT': '280',
    'TWEET1_OVERLAY_ON': 'True',   
    'TWEET1_OVERLAY_URL': '',
    'TWEET1_REGENERATE_ORDER': '以下の文章はツイートするのに長すぎました。文章を簡潔にするか省略してください。',
    'TWEET2': 'False',
    'TWEET2_SYSTEM_PROMPT': """
あなたは、Twitter投稿者です。
下記の条件に従ってツイートしてください。
条件:
-英語でツイートしてください。
-小学生にもわかりやすく書いてください。
-出力文 は女性を思わせる口語体で記述してください。
-文脈に応じて、任意の場所で絵文字を使ってください。ツイートする文字数はURLを除いて英語で240文字以内にしてください。
-ニュースに対して記者の視点やニュースの当事者ではなく、ニュースを読んだ読者視点で感想をツイートしてください。
-ツイートの一番最後にハイパーリンク形式で参照元のURLを記載してください。
""",
    'TWEET2_ORDER_PROMPT': """
あなたは、Twitter投稿者です。 下記の条件に従ってツイートしてください。 
条件: 
-小学生にもわかりやすく書いてください。 
-出力文 は女性を思わせる口語体で記述してください。 
-文脈に応じて、任意の場所で絵文字を使ってください。絵文字を最低1個は含めてください。
ツイートする文字数は日本語で117文字以内にしてください。 
-ニュースに対して記者の視点やニュースの当事者ではなく、ニュースを読んだ読者視点で感想をツイートしてください。 
-投稿に合ったハッシュタグを付与してください。
-ツイートに参照元のURLを含めないでください。
""",
    'TWEET2_MAX_CHARACTER_COUNT': '280',
    'TWEET2_OVERLAY_ON': 'True',   
    'TWEET2_OVERLAY_URL': '',
    'TWEET2_REGENERATE_ORDER': '以下の文章はツイートするのに長すぎました。文章を簡潔にするか省略してください。',
    'TWEET_SQ_PROMPT': """
現在は日本時間の{nowDateStr}です。
前回の自身の発言について自問自答してください。
""",
    'BUCKET_NAME': 'あなたがCloud Strageに作成したバケット名を入れてください。',
    'FILE_AGE': '1'
}

# Firestore クライアントの初期化
try:
    db = firestore.Client(database=DATABASE_NAME)
except Exception as e:
    print(f"Error creating Firestore client: {e}")
    raise

def reload_settings():
    print("execute reload_settings")
    global SYSTEM_PROMPT, ORDER_PROMPT, PAINT_PROMPT, nowDate, nowDateStr, jst, AI_MODEL, INSTA_AI_MODEL, TWEET_AI_MODEL, PARTIAL_MATCH_FILTER_WORDS, FULL_MATCH_FILTER_WORDS
    global READ_TEXT_COUNT,READ_LINKS_COUNT, MAX_TOKEN_NUM, PAINTING_ON, DEFAULT_USER_ID, order_prompt, URL_FILTER_ON
    global INSTA, INSTA_SYSTEM_PROMPT, INSTA_ORDER_PROMPT, INSTA_MAX_CHARACTER_COUNT, INSTA_OVERLAY_ON, INSTA_OVERLAY_URL, insta_order_prompt
    global TWEET_REGENERATE_COUNT
    global TWEET1, TWEET1_SYSTEM_PROMPT, TWEET1_ORDER_PROMPT, TWEET1_MAX_CHARACTER_COUNT, TWEET1_OVERLAY_ON, TWEET1_OVERLAY_URL, tweet1_order_prompt, TWEET1_REGENERATE_ORDER
    global TWEET2, TWEET2_SYSTEM_PROMPT, TWEET2_ORDER_PROMPT, TWEET2_MAX_CHARACTER_COUNT, TWEET2_OVERLAY_ON, TWEET2_OVERLAY_URL, tweet2_order_prompt, TWEET2_REGENERATE_ORDER
    global TWEET_SQ_PROMPT, tweet_sq_prompt
    global LINE_REPLY, BUCKET_NAME, FILE_AGE
    jst = pytz.timezone('Asia/Tokyo')
    nowDate = datetime.now(jst)
    nowDateStr = nowDate.strftime('%Y年%m月%d日 %H:%M:%S')

    AI_MODEL = get_setting('AI_MODEL')
    INSTA_AI_MODEL = get_setting('INSTA_AI_MODEL')
    TWEET_AI_MODEL = get_setting('TWEET_AI_MODEL')
    SYSTEM_PROMPT = get_setting('SYSTEM_PROMPT')
    ORDER_PROMPT = get_setting('ORDER_PROMPT')
    if ORDER_PROMPT:
        ORDER_PROMPT = ORDER_PROMPT.split(',')
    else:
        ORDER_PROMPT = []
    PAINT_PROMPT = get_setting('PAINT_PROMPT')
    PARTIAL_MATCH_FILTER_WORDS = get_setting('PARTIAL_MATCH_FILTER_WORDS')
    if PARTIAL_MATCH_FILTER_WORDS:
        PARTIAL_MATCH_FILTER_WORDS = PARTIAL_MATCH_FILTER_WORDS.split(',')
    else:
        PARTIAL_MATCH_FILTER_WORDS = []
    FULL_MATCH_FILTER_WORDS = get_setting('FULL_MATCH_FILTER_WORDS')
    if FULL_MATCH_FILTER_WORDS:
        FULL_MATCH_FILTER_WORDS = FULL_MATCH_FILTER_WORDS.split(',')
    else:
        FULL_MATCH_FILTER_WORDS = []
    READ_TEXT_COUNT = int(get_setting('READ_TEXT_COUNT') or 1000)
    READ_LINKS_COUNT = int(get_setting('READ_LINKS_COUNT') or 2000)
    MAX_TOKEN_NUM = int(get_setting('MAX_TOKEN_NUM') or 0)
    PAINTING_ON = get_setting('PAINTING_ON')
    URL_FILTER_ON = get_setting('URL_FILTER_ON')
    DEFAULT_USER_ID = get_setting('DEFAULT_USER_ID')
    INSTA = get_setting('INSTA')
    INSTA_SYSTEM_PROMPT = get_setting('INSTA_SYSTEM_PROMPT')
    INSTA_ORDER_PROMPT = get_setting('INSTA_ORDER_PROMPT')
    if INSTA_ORDER_PROMPT:
        INSTA_ORDER_PROMPT = INSTA_ORDER_PROMPT.split(',')
    else:
        INSTA_ORDER_PROMPT = []
    INSTA_MAX_CHARACTER_COUNT = int(get_setting('INSTA_MAX_CHARACTER_COUNT') or 0)
    INSTA_OVERLAY_ON = get_setting('INSTA_OVERLAY_ON')
    INSTA_OVERLAY_URL = get_setting('INSTA_OVERLAY_URL')
    TWEET_REGENERATE_COUNT = int(get_setting('TWEET_REGENERATE_COUNT') or 5)
    TWEET1 = get_setting('TWEET1')
    TWEET1_SYSTEM_PROMPT = get_setting('TWEET1_SYSTEM_PROMPT')
    TWEET1_ORDER_PROMPT = get_setting('TWEET1_ORDER_PROMPT')
    if TWEET1_ORDER_PROMPT:
        TWEET1_ORDER_PROMPT = TWEET1_ORDER_PROMPT.split(',')
    else:
        TWEET1_ORDER_PROMPT = []
    TWEET1_MAX_CHARACTER_COUNT = int(get_setting('TWEET1_MAX_CHARACTER_COUNT') or 0)
    TWEET1_OVERLAY_ON = get_setting('TWEET1_OVERLAY_ON')    
    TWEET1_OVERLAY_URL = get_setting('TWEET1_OVERLAY_URL')
    TWEET1_REGENERATE_ORDER = get_setting('TWEET1_REGENERATE_ORDER')
    TWEET2 = get_setting('TWEET2')
    TWEET2_SYSTEM_PROMPT = get_setting('TWEET2_SYSTEM_PROMPT')
    TWEET2_ORDER_PROMPT = get_setting('TWEET2_ORDER_PROMPT')
    if TWEET2_ORDER_PROMPT:
        TWEET2_ORDER_PROMPT = TWEET2_ORDER_PROMPT.split(',')
    else:
        TWEET2_ORDER_PROMPT = []
    TWEET2_MAX_CHARACTER_COUNT = int(get_setting('TWEET2_MAX_CHARACTER_COUNT') or 0)
    TWEET2_OVERLAY_ON = get_setting('TWEET2_OVERLAY_ON')
    TWEET2_OVERLAY_URL = get_setting('TWEET2_OVERLAY_URL')
    TWEET2_REGENERATE_ORDER = get_setting('TWEET2_REGENERATE_ORDER')
    BUCKET_NAME = get_setting('BUCKET_NAME')
    FILE_AGE = get_setting('FILE_AGE')
    order_prompt = random.choice(ORDER_PROMPT)
    order_prompt = order_prompt.strip()
    if INSTA_ORDER_PROMPT:
        insta_order_prompt = random.choice(INSTA_ORDER_PROMPT)
        insta_order_prompt = insta_order_prompt.strip() 
        if '{nowDateStr}' in insta_order_prompt:
            insta_order_prompt = insta_order_prompt.format(nowDateStr=nowDateStr)
    if TWEET1_ORDER_PROMPT:
        tweet1_order_prompt = random.choice(TWEET1_ORDER_PROMPT)
        tweet1_order_prompt = tweet1_order_prompt.strip() 
        if '{nowDateStr}' in tweet1_order_prompt:
            tweet1_order_prompt = tweet1_order_prompt.format(nowDateStr=nowDateStr)
    if TWEET2_ORDER_PROMPT:
        tweet2_order_prompt = random.choice(TWEET2_ORDER_PROMPT)
        tweet2_order_prompt = tweet2_order_prompt.strip() 
        if '{nowDateStr}' in tweet2_order_prompt:
            tweet2_order_prompt = tweet2_order_prompt.format(nowDateStr=nowDateStr)
    TWEET_SQ_PROMPT = get_setting('TWEET_SQ_PROMPT')
    if TWEET_SQ_PROMPT:
        TWEET_SQ_PROMPT = TWEET_SQ_PROMPT.split(',')
    else:
        TWEET_SQ_PROMPT = []
    tweet_sq_prompt = random.choice(ORDER_PROMPT)
    tweet_sq_prompt = tweet_sq_prompt.strip()
    
    if '{nowDateStr}' in order_prompt:
        order_prompt = order_prompt.format(nowDateStr=nowDateStr)
        
    if '{nowDateStr}' in tweet_sq_prompt:
        tweet_sq_prompt = tweet_sq_prompt.format(nowDateStr=nowDateStr)

def get_setting(key):
    #print(f"key: {key}")
    doc_ref = db.collection(u'settings').document('app_settings')
    doc = doc_ref.get()

    if doc.exists:
        doc_dict = doc.to_dict()
        if key not in doc_dict:
            # If the key does not exist in the document, use the default value
            default_value = DEFAULT_ENV_VARS.get(key, "")
            doc_ref.set({key: default_value}, merge=True)  # Add the new setting to the database
            print(f"default_value: {default_value}")
            return default_value
        else:
            return doc_dict.get(key)
    else:
        # If the document does not exist, create it using the default settings
        save_default_settings()
        return DEFAULT_ENV_VARS.get(key, "")

def get_setting_user(user_id, key):
    doc_ref = db.collection(u'users').document(user_id) 
    doc = doc_ref.get()

    if doc.exists:
        doc_dict = doc.to_dict()
        if key not in doc_dict:
            doc_ref.set({'start_free_day': start_free_day}, merge=True)
            return ''
        else:
            return doc_dict.get(key)
    else:
        return ''


def save_default_settings():
    doc_ref = db.collection(u'settings').document('app_settings')
    try:
        doc_ref.set(DEFAULT_ENV_VARS, merge=True)
        print("Default settings successfully saved to Firestore")
    except Exception as e:
        print(f"Error saving default settings to Firestore: {e}")

def update_setting(key, value):
    doc_ref = db.collection(u'settings').document('app_settings')
    doc_ref.update({key: value})

def get_encrypted_message(message, hashed_secret_key):
    cipher = AES.new(hashed_secret_key, AES.MODE_ECB)
    message = message.encode('utf-8')
    padding = 16 - len(message) % 16
    message += bytes([padding]) * padding
    enc_message = base64.b64encode(cipher.encrypt(message))
    return enc_message.decode()

def get_decrypted_message(enc_message, hashed_secret_key):
    try:
        cipher = AES.new(hashed_secret_key, AES.MODE_ECB)
        enc_message = base64.b64decode(enc_message.encode('utf-8'))
        message = cipher.decrypt(enc_message)
        padding = message[-1]
        if padding > 16:
            raise ValueError("Invalid padding value")
        message = message[:-padding]
        return message.decode().rstrip("\0")
    except Exception as e:
        print(f"Error decrypting message: {e}")
        return None  

reload_settings()

app = Flask(__name__)
app.secret_key = os.getenv('secret_key', default='YOUR-DEFAULT-SECRET-KEY')
hash_object = SHA256.new(data=(secret_key or '').encode('utf-8'))
hashed_secret_key = hash_object.digest()
app.secret_key = os.getenv('secret_key', default='YOUR-DEFAULT-SECRET-KEY')
encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")

executor = Executor(app)

@app.route('/reset_logs', methods=['POST'])
def reset_logs():
    if 'is_admin' not in session or not session['is_admin']:
        return redirect(url_for('login'))
    else:
        try:
            users_ref = db.collection(u'users')
            users = users_ref.stream()
            for user in users:
                user_ref = users_ref.document(user.id)
                user_ref.delete()
            return 'All user data reset successfully', 200
        except Exception as e:
            print(f"Error resetting user data: {e}")
            return 'Error resetting user data', 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    reload_settings()  
    attempts_doc_ref = db.collection(u'settings').document('admin_attempts')
    attempts_doc = attempts_doc_ref.get()
    attempts_info = attempts_doc.to_dict() if attempts_doc.exists else {}

    attempts = attempts_info.get('attempts', 0)
    lockout_time = attempts_info.get('lockout_time', None)

    # ロックアウト状態をチェック
    if lockout_time:
        if datetime.now(jst) < lockout_time:
            return render_template('login.html', message='Too many failed attempts. Please try again later.')
        else:
            # ロックアウト時間が過ぎたらリセット
            attempts = 0
            lockout_time = None

    if request.method == 'POST':
        password = request.form.get('password')

        if password == admin_password:
            session['is_admin'] = True
            # ログイン成功したら試行回数とロックアウト時間をリセット
            attempts_doc_ref.set({'attempts': 0, 'lockout_time': None})
            return redirect(url_for('settings'))
        else:
            attempts += 1
            lockout_time = datetime.now(jst) + timedelta(minutes=10) if attempts >= 5 else None
            attempts_doc_ref.set({'attempts': attempts, 'lockout_time': lockout_time})
            return render_template('login.html', message='Incorrect password. Please try again.')
        
    return render_template('login.html')

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'is_admin' not in session or not session['is_admin']:
        return redirect(url_for('login'))
    current_settings = {key: get_setting(key) or DEFAULT_ENV_VARS.get(key, '') for key in REQUIRED_ENV_VARS}

    if request.method == 'POST':
        for key in REQUIRED_ENV_VARS:
            value = request.form.get(key)
            if value:
                update_setting(key, value)
        return redirect(url_for('settings'))
    return render_template(
    'settings.html', 
    settings=current_settings, 
    default_settings=DEFAULT_ENV_VARS, 
    required_env_vars=REQUIRED_ENV_VARS
    )

def create_firestore_document_id_from_url(url):
    return urllib.parse.quote_plus(url)

def add_url_to_firestore(url, user_id):
    url_encoded = create_firestore_document_id_from_url(url)
    user_doc_ref = db.collection(u'users').document(user_id)
    url_doc_ref = user_doc_ref.collection('scraped_urls').document(url_encoded)

    delete_at = datetime.now() + timedelta(weeks=1)
    url_doc_ref.set({
        'url': url,
        'added_at': datetime.now(),
        'delete_at': delete_at
    })

def delete_expired_urls(user_id):
    # Firestoreの初期化（必要に応じて）
    # firebase_admin.initialize_app()

    user_doc_ref = db.collection(u'users').document(user_id)
    urls_ref = user_doc_ref.collection('scraped_urls')

    # 現在の日時を取得
    now = datetime.now()

    # 'delete_at'が現在時刻よりも前のドキュメントを検索
    query = urls_ref.where('delete_at', '<=', now)
    expired_urls = query.stream()

    # 各ドキュメントを削除
    for url_doc in expired_urls:
        print(f"Deleting URL: {url_doc.id}")
        url_doc.reference.delete()

def prune_old_messages(user_data, max_token_num):
    total_chars = sum([len(encoding.encode(msg['content'])) for msg in user_data['messages']])
    while total_chars > max_token_num and len(user_data['messages']) > 3:
        removed_message = user_data['messages'].pop(0)  # 最初のメッセージを削除
        total_chars -= len(encoding.encode(removed_message['content']))
    return user_data

def overlay_transparent_image(base_image, overlay_image, position=(0, 0)):
    base_image.paste(overlay_image, position, overlay_image)
    return base_image

def get_image_with_retry(url, max_retries=3, backoff_factor=0.3):
    session = requests.Session()
    retries = Retry(total=max_retries, backoff_factor=backoff_factor, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))

    try:
        response = session.get(url)
        response.raise_for_status()  # これにより、応答がHTTPエラーコードの場合に例外が発生します
        return Image.open(BytesIO(response.content))
    except requests.exceptions.RequestException as e:
        print(f"Error fetching image from {url}: {e}")
        return None


@app.route('/create')
def create():
    reload_settings()
    
    user_id = DEFAULT_USER_ID
    
    future = executor.submit(generate_doc, user_id, 0, None)  # Futureオブジェクトを受け取ります
    try:
        future.result()
    except Exception as e:
        print(f"Error: {e}")  # エラーメッセージを表示します
        return jsonify({"status": "Creation started"}), 200
    return jsonify({"status": "Creation started"}), 200

def response_filter(bot_reply):
    # パターン定義
    pattern102 = r"!\[.*\]\(.*\.jpg\)|!\[.*\]\(.*\.png\)"
    pattern103 = r"\[画像.*\]"
    pattern104 = r"\(.*\.jpg\)|\(.*\.png\)"
    pattern105 = r"!\[.*\]\(http.*\.(jpg|png)\)"

    # パターンに基づいてテキストをフィルタリング
    bot_reply = re.sub(pattern102, "", bot_reply).strip()
    bot_reply = re.sub(pattern103, "", bot_reply).strip()
    bot_reply = re.sub(pattern104, "", bot_reply).strip()
    bot_reply = re.sub(pattern105, "", bot_reply).strip()
    response = re.sub(r"\n{2,}", "\n", bot_reply)

    return response.rstrip('\n')

def generate_doc(user_id, retry_count, bot_reply, r_public_img_url=[]):
    print(f"initiated doc. user ID: {user_id}, retry_count: {retry_count}, bot_reply: {bot_reply}, r_public_img_url: {r_public_img_url}")
    doc_ref = db.collection(u'users').document(user_id)
    print(f"Firestore document reference obtained {doc_ref}")
            
    user_doc = doc_ref.get()
    updated_date = nowDate
    daily_usage = 0
    public_img_url = []
    removed_assistant_messages = []
    if user_doc.exists:
        print(f"already exist user doc.  user ID: {user_id}")
        user_data = user_doc.to_dict()
        updated_date = user_data['updated_date']
        updated_date = updated_date.astimezone(jst)
        daily_usage = user_data['daily_usage']
        print(f"updated_date: {updated_date}, nowDate: {nowDate}")
        if nowDate.date() != updated_date.date():
            daily_usage = 0
        else:
            daily_usage = user_data['daily_usage'] + 1
    else:
        print(f"create new user doc. user ID: {user_id}")
        user_data = {
            'messages': [],
            'updated_date': nowDate,
            'daily_usage': 0,
            'start_free_day': datetime.now(jst),
            'last_image_url': ""
        }

    # OpenAI API へのリクエスト
    messages_for_api = [
        {'role': 'system', 'content': SYSTEM_PROMPT}
    ]
    for msg in user_data['messages']:
        decrypted_content = get_decrypted_message(msg['content'], hashed_secret_key)
        messages_for_api.append({'role': msg['role'], 'content': decrypted_content})
        
    # この行はループの外で一度だけ行う
    messages_for_api.append({'role': 'user', 'content': order_prompt})

    # 各メッセージのエンコードされた文字数を合計
    total_chars = sum([len(encoding.encode(msg['content'])) for msg in messages_for_api])

    # トークン数が制限を超えていれば、最古のメッセージから削除
    while total_chars > MAX_TOKEN_NUM and len(messages_for_api) > 3:
        removed_message = messages_for_api.pop(3)  # 最初の3つはシステムとアシスタントのメッセージなので保持
        total_chars -= len(encoding.encode(removed_message['content']))
        # もし削除されたメッセージがassistantのものなら、一時リストに追加
        if removed_message['role'] == 'assistant':
            removed_assistant_messages.append(removed_message)
    if bot_reply is None:
        bot_reply, public_img_url = chatgpt_functions(AI_MODEL, messages_for_api, user_id, PAINT_PROMPT, READ_TEXT_COUNT, READ_LINKS_COUNT, PARTIAL_MATCH_FILTER_WORDS, FULL_MATCH_FILTER_WORDS, PAINTING_ON)
        if bot_reply == "":
            print("Error: not bot_reply")
            return
        if isinstance(bot_reply, tuple):
            bot_reply = bot_reply[0]
        
    else:
        print(f"initiate re run_conversation. messages_for_api: {messages_for_api}")
        response = run_conversation(AI_MODEL, messages_for_api)
        bot_reply = response.choices[0].message.content
        public_img_url = r_public_img_url
    bot_reply = response_filter(bot_reply)
    print(f"bot_reply: {bot_reply}, public_img_url: {public_img_url}")
    extractor = URLExtract()
    extract_url = extractor.find_urls(bot_reply)
    if not extract_url:
        print(f"URL is not include doc.")
        generate_doc(user_id, retry_count + 1, None)
        return

    if INSTA == 'True':
        generate_insta(user_id, bot_reply, public_img_url)
    if TWEET1 == 'True':
        generate_tweet("tweet1", user_id, bot_reply, 0, public_img_url)
    time.sleep(10)
    if TWEET2 == 'True':
        generate_tweet("tweet2", user_id, bot_reply, 0, public_img_url)

    if URL_FILTER_ON == 'True':
        if extract_url:
            print(f"extract_url: {extract_url}")
            # リストの最初のURLをエンコードする
            #encoded_url = quote(extract_url[0])
            encoded_url = extract_url[0]
            add_url_to_firestore(encoded_url, user_id)
        
        delete_expired_urls('user_id')
    print(f"user_data: {user_data}")

    #botの返信を追加
    removed_assistant_messages.append({'role': 'assistant', 'content': bot_reply})
    # ユーザーデータにremoved_assistant_messagesを再追加
    if removed_assistant_messages:
        # 保存されたassistantメッセージをFirestoreに戻す
        user_data['messages'] = []
        for msg in removed_assistant_messages:
            # メッセージを暗号化して保存
            encrypted_message = get_encrypted_message(msg['content'], hashed_secret_key)
            user_data['messages'].append({'role': 'assistant', 'content': encrypted_message})
   
    user_data['daily_usage'] = daily_usage
    user_data['updated_date'] = nowDate
    user_data['last_image_url'] = public_img_url
    doc_ref.set(user_data, merge=True)
    print(f"save user doc. user ID: {user_id}")
    return

def generate_doc_sq(user_id, retry_count, bot_reply, r_public_img_url=[]):
    print(f"initiated doc. user ID: {user_id}, retry_count: {retry_count}, bot_reply: {bot_reply}, r_public_img_url: {r_public_img_url}")
    doc_ref = db.collection(u'users').document(user_id)
    print(f"Firestore document reference obtained {doc_ref}")
            
    user_doc = doc_ref.get()
    updated_date = nowDate
    daily_usage = 0
    public_img_url = []
    removed_assistant_messages = []
    if user_doc.exists:
        print(f"already exist user doc.  user ID: {user_id}")
        user_data = user_doc.to_dict()
        updated_date = user_data['updated_date']
        updated_date = updated_date.astimezone(jst)
        daily_usage = user_data['daily_usage']
        print(f"updated_date: {updated_date}, nowDate: {nowDate}")
        if nowDate.date() != updated_date.date():
            daily_usage = 0
        else:
            daily_usage = user_data['daily_usage'] + 1
    else:
        print(f"create new user doc. user ID: {user_id}")
        user_data = {
            'messages': [],
            'updated_date': nowDate,
            'daily_usage': 0,
            'start_free_day': datetime.now(jst),
            'last_image_url': ""
        }

    # OpenAI API へのリクエスト
    messages_for_api = [
        {'role': 'system', 'content': SYSTEM_PROMPT}
    ]
    for msg in user_data['messages']:
        decrypted_content = get_decrypted_message(msg['content'], hashed_secret_key)
        messages_for_api.append({'role': msg['role'], 'content': decrypted_content})
        
    # この行はループの外で一度だけ行う
    messages_for_api.append({'role': 'user', 'content': tweet_sq_prompt})

    # 各メッセージのエンコードされた文字数を合計
    total_chars = sum([len(encoding.encode(msg['content'])) for msg in messages_for_api])

    # トークン数が制限を超えていれば、最古のメッセージから削除
    while total_chars > MAX_TOKEN_NUM and len(messages_for_api) > 3:
        removed_message = messages_for_api.pop(3)  # 最初の3つはシステムとアシスタントのメッセージなので保持
        total_chars -= len(encoding.encode(removed_message['content']))
        # もし削除されたメッセージがassistantのものなら、一時リストに追加
        if removed_message['role'] == 'assistant':
            removed_assistant_messages.append(removed_message)
    if bot_reply is None:
        bot_reply, public_img_url = chatgpt_functions(AI_MODEL, messages_for_api, user_id, PAINT_PROMPT, READ_TEXT_COUNT, READ_LINKS_COUNT, PARTIAL_MATCH_FILTER_WORDS, FULL_MATCH_FILTER_WORDS, "False")
        if bot_reply == "":
            print("Error: not bot_reply")
            return
        if isinstance(bot_reply, tuple):
            bot_reply = bot_reply[0]
        
    else:
        print(f"initiate re run_conversation. messages_for_api: {messages_for_api}")
        response = run_conversation(AI_MODEL, messages_for_api)
        bot_reply = response.choices[0].message.content
        public_img_url = r_public_img_url
    bot_reply = response_filter(bot_reply)
    print(f"bot_reply: {bot_reply}, public_img_url: {public_img_url}")
    extractor = URLExtract()
    extract_url = extractor.find_urls(bot_reply)
    if not extract_url:
        print(f"URL is not include doc.")
        generate_doc(user_id, retry_count + 1, None)
        return

    #if TWEET1 == 'True':
    #    generate_tweet("tweet1", user_id, bot_reply, 0, public_img_url)
    #time.sleep(10)
    #if TWEET2 == 'True':
    #    generate_tweet("tweet2", user_id, bot_reply, 0, public_img_url)

    if URL_FILTER_ON == 'True':
        if extract_url:
            print(f"extract_url: {extract_url}")
            # リストの最初のURLをエンコードする
            #encoded_url = quote(extract_url[0])
            encoded_url = extract_url[0]
            add_url_to_firestore(encoded_url, user_id)
        
        delete_expired_urls('user_id')
    print(f"user_data: {user_data}")

    #botの返信を追加
    removed_assistant_messages.append({'role': 'assistant', 'content': bot_reply})
    # ユーザーデータにremoved_assistant_messagesを再追加
    if removed_assistant_messages:
        # 保存されたassistantメッセージをFirestoreに戻す
        user_data['messages'] = []
        for msg in removed_assistant_messages:
            # メッセージを暗号化して保存
            encrypted_message = get_encrypted_message(msg['content'], hashed_secret_key)
            user_data['messages'].append({'role': 'assistant', 'content': encrypted_message})
   
    user_data['daily_usage'] = daily_usage
    user_data['updated_date'] = nowDate
    user_data['last_image_url'] = public_img_url
    doc_ref.set(user_data, merge=True)
    print(f"save user doc. user ID: {user_id}")
    return

@app.route('/self_questioning')
def self_questioning():
    reload_settings()
    
    user_id = DEFAULT_USER_ID
    
    future = executor.submit(generate_doc_sq, user_id, 0, None)  # Futureオブジェクトを受け取ります
    try:
        future.result()
    except Exception as e:
        print(f"Error: {e}")  # エラーメッセージを表示します
        return jsonify({"status": "Creation started"}), 200
    return jsonify({"status": "Creation started"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
