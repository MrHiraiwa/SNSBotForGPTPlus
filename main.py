import os
from io import BytesIO
import re
import random
import tweepy
from google.cloud import firestore
from datetime import datetime, time, timedelta
import pytz
from flask import Flask, request, render_template, session, redirect, url_for, jsonify
import unicodedata
from twitter_text import parse_tweet, extract_urls_with_indices
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
# from note import generate_note
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
    "PARTIAL_MATCH_FILTER_WORDS",
    "FULL_MATCH_FILTER_WORDS",
    "READ_TEXT_COUNT",
    "READ_LINKS_COUNT",
    "MAX_TOKEN_NUM",
    "PAINTING_ON",
    "URL_FILTER_ON",
    "MAX_CHARACTER_COUNT",
    "DEFAULT_USER_ID",
    "NOTE",
    "NOTE_SYSTEM_PROMPT",
    "NOTE_ORDER_PROMPT",
    "NOTE_MAX_CHARACTER_COUNT",
    "NOTE_OVERLAY_URL",
    "TWEET_REGENERATE_ORDER",
    "TWEET_REGENERATE_COUNT",
    "TWEET1",
    "TWEET1_SYSTEM_PROMPT",
    "TWEET1_ORDER_PROMPT",
    "TWEET1_MAX_CHARACTER_COUNT",
    "TWEET1_OVERLAY_URL",
    "TWEET2",
    "TWEET2_SYSTEM_PROMPT",
    "TWEET2_ORDER_PROMPT",
    "TWEET2_MAX_CHARACTER_COUNT",
    "TWEET2_OVERLAY_URL"
]

DEFAULT_ENV_VARS = {
    'AI_MODEL': 'gpt-3.5-turbo-0125',
    'SYSTEM_PROMPT': """
あなたは、ブログ投稿者です。あなたはURLからURLリストを読み込んだりページのの内容を読み込んだりできます。
下記の条件に従ってツイートしてください。
条件:
-小学生にもわかりやすく書いてください。
-出力文 は女性を思わせる口語体で記述してください。
-文脈に応じて、任意の場所で絵文字を使ってください。
-読み込んだ記事に対して記者の視点や記事の当事者ではなく、記事を読んだ読者視点で感想を生成してください。
-冒頭に「選んだ」「検索した」等の記載は不要です。記事をなるべく長い感想文にしてください。
-生成した文章で、「描いたイラスト」「イラストにした」「イメージした」「イラスト完成」等、生成したイラストについて言及しないでください。
-記事に合った画像を生成してください。
文章の一番最後に「参照元：」のラベルに続けて参照元のURLを記載してください。
""",
    'ORDER_PROMPT': """
現在は日本時間の{nowDateStr}です。
次のURLからURLのリストを読み込んで一番上の記事を選び、URLのページを読み込んでから条件に従って文章を生成してください。一番上の記事が前回の記事の内容に近い内容であった場合は次の記事を選択してください。
https://trends.google.co.jp/trends/trendingsearches/realtime?geo=JP&category=all
""",
    'PAINT_PROMPT': """
上記の場面を日本の萌えアニメスタイルのイラストで描いてください。実写風には絶対にしないでください。コスプレやキャラクターの着ぐるみを着た実写風画像も禁止です。
日本人向けの画風にしてください。
日本の萌えアニメ風イラストの全体に脈動感を持たせてください。登場人物は向きや姿勢を変えるなどして脈動感を与えてください。
""",
    'PARTIAL_MATCH_FILTER_WORDS': 'google.com,google.co.jp,www.iwate-np.co.jp,fashion-press.net,prtimes.jp,designlearn.co.jp,www.goal.com', 
    'FULL_MATCH_FILTER_WORDS': '最新ブラウザ,gamebiz【ゲームビズ】,PR TIMES,日テレNEWS NNN,産経ニュース,ナゾロジー,日経メディカル,朝日新聞デジタル,NHKニュース,KBC九州朝日放送,北海道新聞,EE Times Japan,下野新聞社,ファミ通App,株探（かぶたん）,スポーツナビ,電撃ホビーウェブ,スポーツナビ,マテリアルフロー･プラス,Yahoo!ニュース,ライブドアニュース,日本経済新聞,Kufura,スポーツ報知,日本農業新聞,4Gamer,日刊スポーツ,tnc.co.jp,日刊スポーツ,広島ホームテレビ,au Webポータル,ファミ通,スポニチ Sponichi Annex,トラベル Watch,朝日新聞GLOBE＋,ペルソナチャンネル,読売新聞オンライン,静岡新聞,中国新聞デジタル,TBS NEWS DIG,秋田魁新報,GAME Watch,ロイター,毎日新聞,ナタリー,HOBBY Watch,goo ニュース,ハフポスト,Nordot,くるまのニュース,ORICON NEWS,ITmedia,サンスポ,hobby Watch,デイリースポーツ,TBSテレビ,楽天ブログ,Billboard JAPAN,AV Watch,NHK,神戸新聞,Forbes JAPAN,Bloomberg.co.jp,西宮市,Elle,Natalie',
    'READ_TEXT_COUNT': '1500',
    'READ_LINKS_COUNT': '2000',
    'MAX_TOKEN_NUM': '1500',
    'PAINTING_ON': 'True',
    'URL_FILTER_ON': 'True',
    'DEFAULT_USER_ID': 'default_user_id',
    'NOTE': 'False',
    'NOTE_SYSTEM_PROMPT': """
あなたは、ブログ投稿者です。与えられたメッセージを英語で翻訳してツイートしてください。URLは省略しないでください。
""",
    'NOTE_ORDER_PROMPT': """
以下の記事をツイートしてください。
文字数を250文字程度にしてください。URLを省略せずに必ず含めてください。
""",
    'NOTE_MAX_CHARACTER_COUNT': '280',
    'NOTE_OVERLAY_URL': '',
    'TWEET_REGENERATE_ORDER': '以下の文章はツイートするのに長すぎました。ハッシュタグがある場合はハッシュタグを1つ減らしてください。加えて文章を簡潔にするか省略し、文字数を減らしてツイートしてください。URLは省略しないでください。',
    'TWEET_REGENERATE_COUNT': '5',
    'TWEET1': 'False',
    'TWEET1_SYSTEM_PROMPT': """
あなたは、Twitter投稿者です。
下記の条件に従ってツイートしてください。
条件:
-小学生にもわかりやすく書いてください。
-出力文 は女性を思わせる口語体で記述してください。
-文脈に応じて、任意の場所で絵文字を使ってください。ツイートする文字数はURLを除いて日本語で117文字以内にしてください。
-ニュースに対して記者の視点やニュースの当事者ではなく、ニュースを読んだ読者視点で感想をツイートしてください。
ツイートの一番最後にハイパーリンク形式で参照元のURLを記載してください。
""",
    'TWEET1_ORDER_PROMPT': """
以下の記事をツイートしてください。
文字数を250文字程度にしてください。URLを省略せずに必ず含めてください。
""",
    'TWEET1_MAX_CHARACTER_COUNT': '280',
    'TWEET1_OVERLAY_URL': '',
    'TWEET2': 'False',
    'TWEET2_SYSTEM_PROMPT': """
あなたは、Twitter投稿者です。
下記の条件に従ってツイートしてください。
条件:
-英語でツイートしてください。
-小学生にもわかりやすく書いてください。
-出力文 は女性を思わせる口語体で記述してください。
-文脈に応じて、任意の場所で絵文字を使ってください。ツイートする文字数はURLを除いて英語で250文字以内にしてください。
-ニュースに対して記者の視点やニュースの当事者ではなく、ニュースを読んだ読者視点で感想をツイートしてください。
ツイートの一番最後にハイパーリンク形式で参照元のURLを記載してください。
""",
    'TWEET2_ORDER_PROMPT': """
以下の記事を英語でツイートしてください。URLは翻訳せずにそのままツイートしてください。
文字数を250文字程度にしてください。URLを省略せずに必ず含めてください。
""",
    'TWEET2_MAX_CHARACTER_COUNT': '280',
    'TWEET2_OVERLAY_URL': ''
}

# Firestore クライアントの初期化
try:
    db = firestore.Client(database=DATABASE_NAME)
except Exception as e:
    print(f"Error creating Firestore client: {e}")
    raise
    
def reload_settings():
    global SYSTEM_PROMPT, ORDER_PROMPT, PAINT_PROMPT, nowDate, nowDateStr, jst, AI_MODEL, PARTIAL_MATCH_FILTER_WORDS, FULL_MATCH_FILTER_WORDS
    global READ_TEXT_COUNT,READ_LINKS_COUNT, MAX_TOKEN_NUM, PAINTING_ON, DEFAULT_USER_ID, order_prompt, URL_FILTER_ON
    global NOTE, NOTE_SYSTEM_PROMPT, NOTE_ORDER_PROMPT, NOTE_MAX_CHARACTER_COUNT, NOTE_OVERLAY_URL, note_order_prompt
    global TWEET_REGENERATE_ORDER, TWEET_REGENERATE_COUNT
    global TWEET1, TWEET1_SYSTEM_PROMPT, TWEET1_ORDER_PROMPT, TWEET1_MAX_CHARACTER_COUNT, TWEET1_OVERLAY_URL, tweet1_order_prompt
    global TWEET2, TWEET2_SYSTEM_PROMPT, TWEET2_ORDER_PROMPT, TWEET2_MAX_CHARACTER_COUNT, TWEET2_OVERLAY_URL, tweet2_order_prompt
    jst = pytz.timezone('Asia/Tokyo')
    nowDate = datetime.now(jst)
    nowDateStr = nowDate.strftime('%Y年%m月%d日 %H:%M:%S')

    AI_MODEL = get_setting('AI_MODEL')
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
    NOTE = get_setting('NOTE')
    NOTE_SYSTEM_PROMPT = get_setting('NOTE_SYSTEM_PROMPT')
    NOTE_ORDER_PROMPT = get_setting('NOTE_ORDER_PROMPT')
    if NOTE_ORDER_PROMPT:
        NOTE_ORDER_PROMPT = NOTE_ORDER_PROMPT.split(',')
    else:
        NOTE_ORDER_PROMPT = []
    NOTE_MAX_CHARACTER_COUNT = int(get_setting('NOTE_MAX_CHARACTER_COUNT') or 0)
    NOTE_OVERLAY_URL = get_setting('NOTE_OVERLAY_URL')
    TWEET_REGENERATE_ORDER = get_setting('REGENERATE_ORDER')
    TWEET_REGENERATE_COUNT = int(get_setting('TWEET_REGENERATE_COUNT') or 5)
    TWEET1 = get_setting('TWEET1')
    TWEET1_SYSTEM_PROMPT = get_setting('TWEET1_SYSTEM_PROMPT')
    TWEET1_ORDER_PROMPT = get_setting('TWEET1_ORDER_PROMPT')
    if TWEET1_ORDER_PROMPT:
        TWEET1_ORDER_PROMPT = TWEET1_ORDER_PROMPT.split(',')
    else:
        TWEET1_ORDER_PROMPT = []
    TWEET1_MAX_CHARACTER_COUNT = int(get_setting('TWEET1_MAX_CHARACTER_COUNT') or 0)
    TWEET1_OVERLAY_URL = get_setting('TWEET1_OVERLAY_URL')
    TWEET2 = get_setting('TWEET2')
    TWEET2_SYSTEM_PROMPT = get_setting('TWEET2_SYSTEM_PROMPT')
    TWEET2_ORDER_PROMPT = get_setting('TWEET2_ORDER_PROMPT')
    if TWEET2_ORDER_PROMPT:
        TWEET2_ORDER_PROMPT = TWEET2_ORDER_PROMPT.split(',')
    else:
        TWEET2_ORDER_PROMPT = []
    TWEET2_MAX_CHARACTER_COUNT = int(get_setting('TWEET2_MAX_CHARACTER_COUNT') or 0)
    TWEET2_OVERLAY_URL = get_setting('TWEET2_OVERLAY_URL')
    order_prompt = random.choice(ORDER_PROMPT)
    order_prompt = order_prompt.strip()
    note_order_prompt = random.choice(NOTE_ORDER_PROMPT)
    note_order_prompt = note_order_prompt.strip() 
    tweet1_order_prompt = random.choice(TWEET1_ORDER_PROMPT)
    tweet1_order_prompt = tweet1_order_prompt.strip() 
    tweet2_order_prompt = random.choice(TWEET2_ORDER_PROMPT)
    tweet2_order_prompt = tweet2_order_prompt.strip() 
    
    if '{nowDateStr}' in order_prompt:
        order_prompt = order_prompt.format(nowDateStr=nowDateStr)
    if '{nowDateStr}' in note_order_prompt:
        note_order_prompt = note_order_prompt.format(nowDateStr=nowDateStr)
    if '{nowDateStr}' in tweet1_order_prompt:
        tweet1_order_prompt = tweet1_order_prompt.format(nowDateStr=nowDateStr)
    if '{nowDateStr}' in tweet2_order_prompt:
        tweet2_order_prompt = tweet2_order_prompt.format(nowDateStr=nowDateStr)

def get_setting(key):
    doc_ref = db.collection(u'settings').document('app_settings')
    doc = doc_ref.get()

    if doc.exists:
        doc_dict = doc.to_dict()
        if key not in doc_dict:
            # If the key does not exist in the document, use the default value
            default_value = DEFAULT_ENV_VARS.get(key, "")
            doc_ref.set({key: default_value}, merge=True)  # Add the new setting to the database
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
    doc_ref.set(DEFAULT_ENV_VARS, merge=True)

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
encoding = tiktoken.encoding_for_model(AI_MODEL)

# Firestore クライアントの初期化
try:
    db = firestore.Client(database=DATABASE_NAME)
except Exception as e:
    print(f"Error creating Firestore client: {e}")
    raise

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

def generate_doc(user_id, retry_count, bot_reply, r_public_img_url=[]):
    print(f"initiated doc. user ID: {user_id}, retry_count: {retry_count}, bot_reply: {bot_reply}, r_public_img_url: {r_public_img_url}")
    doc_ref = db.collection(u'users').document(user_id)
    print(f"Firestore document reference obtained {doc_ref}")
            
    user_doc = doc_ref.get()
    updated_date = nowDate
    daily_usage = 0
    public_img_url = []
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
    
    if bot_reply is None:    
        messages_for_api.append({'role': 'user', 'content': order_prompt})
    else:
        # Retry
        messages_for_api.append({'role': 'user', 'content': REGENERATE_ORDER + "\n" + bot_reply})

    # 各メッセージのエンコードされた文字数を合計
    total_chars = sum([len(encoding.encode(msg['content'])) for msg in messages_for_api])

    # トークン数が制限を超えていれば、最古のメッセージから削除
    while total_chars > MAX_TOKEN_NUM and len(messages_for_api) > 3:
        removed_message = messages_for_api.pop(3)  # 最初の3つはシステムとアシスタントのメッセージなので保持
        total_chars -= len(encoding.encode(removed_message['content']))
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
        
    print(f"bot_reply: {bot_reply}, public_img_url: {public_img_url}")
    character_count = int(parse_tweet(bot_reply).weightedLength)
    print(f"character_count: {character_count}")
    extractor = URLExtract()
    extract_url = extractor.find_urls(bot_reply)
    if not extract_url:
        print(f"URL is not include doc.")
        generate_doc(user_id, retry_count + 1, None)
        return
        
    if TWEET1 == 'True':
        generate_tweet("tweet1", user_id, bot_reply, 0, public_img_url)
    if TWEET2 == 'True':
        generate_tweet("tweet2", user_id, bot_reply, 0, public_img_url)

    if URL_FILTER_ON == 'True':
        if extract_url:
            print(f"extract_url: {extract_url}")
            # リストの最初のURLをエンコードする
            encoded_url = quote(extract_url[0])
            add_url_to_firestore(encoded_url, user_id)
        
        delete_expired_urls('user_id')
    print(f"user_data: {user_data}")
            
    # ユーザー(order_prompt)とボットのメッセージを暗号化してFirestoreに保存
    # order_promptの保存は不要と判断しコメントアウト
    # user_data['messages'].append({'role': 'user', 'content': get_encrypted_message(order_prompt, hashed_secret_key)})
    user_data['messages'].append({'role': 'assistant', 'content': get_encrypted_message(bot_reply, hashed_secret_key)})         
    user_data['daily_usage'] = daily_usage
    user_data['updated_date'] = nowDate
    user_data['last_image_url'] = public_img_url
    doc_ref.set(user_data, merge=True)
    print(f"save user doc. user ID: {user_id}")
    return
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
