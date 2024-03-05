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
import tiktoken
from PIL import Image

from functions import run_conversation

TWEET2_API_KEY = os.getenv('TWEET2_API_KEY')
TWEET2_API_KEY_SECRET = os.getenv('TWEET2_API_KEY_SECRET')
TWEET2_ACCESS_TOKEN = os.getenv('TWEET2_ACCESS_TOKEN')
TWEET2_ACCESS_TOKEN_SECRET = os.getenv('TWEET2_ACCESS_TOKEN_SECRET')
DATABASE_NAME = os.getenv('DATABASE_NAME')

REQUIRED_ENV_VARS = [
    "TWEET2_SYSTEM_PROMPT",
    "TWEET2_ORDER_PROMPT",
    "AI_MODEL",
    "REGENERATE_ORDER",
    "REGENERATE_COUNT",
    "MAX_CHARACTER_COUNT",
    "TWEET2_OVERLAY_URL"
]

DEFAULT_ENV_VARS = {
    'TWEET2_SYSTEM_PROMPT': """
あなたは、Twitter投稿者です。与えられたメッセージを英語で翻訳してツイートしてください。URLは省略しないでください。
""",
    'TWEET2_ORDER_PROMPT': """
以下のツイートを英語に翻訳して、URLは翻訳せずにそのままツイートしてください。
翻訳後の文字数を250文字程度にしてください。URLを省略せずに必ず含めてください。
""",
    'TWEET2_OVERLAY_URL': ''
}
auth = tweepy.OAuthHandler(TWEET2_API_KEY, TWEET2_API_KEY_SECRET)
auth.set_access_token(TWEET2_ACCESS_TOKEN, TWEET2_ACCESS_TOKEN_SECRET)
api = tweepy.API(auth)

client = tweepy.Client(
    consumer_key = TWEET2_API_KEY,
    consumer_secret = TWEET2_API_KEY_SECRET,
    access_token = TWEET2_ACCESS_TOKEN,
    access_token_secret = TWEET2_ACCESS_TOKEN_SECRET
)

# Firestore クライアントの初期化
try:
    db = firestore.Client(database=DATABASE_NAME)
except Exception as e:
    print(f"Error creating Firestore client: {e}")
    raise

def reload_settings():
    global TWEET2_SYSTEM_PROMPT, TWEET2_ORDER_PROMPT, nowDate, nowDateStr, jst, AI_MODEL, REGENERATE_ORDER, REGENERATE_COUNT
    global DEFAULT_USER_ID, order_prompt, MAX_CHARACTER_COUNT, TWEET2_OVERLAY_URL
    jst = pytz.timezone('Asia/Tokyo')
    nowDate = datetime.now(jst)
    nowDateStr = nowDate.strftime('%Y年%m月%d日 %H:%M:%S')

    AI_MODEL = get_setting('AI_MODEL')
    TWEET2_SYSTEM_PROMPT = get_setting('TWEET2_SYSTEM_PROMPT')
    TWEET2_ORDER_PROMPT = get_setting('TWEET2_ORDER_PROMPT')
    if TWEET2_ORDER_PROMPT:
        TWEET2_ORDER_PROMPT = TWEET2_ORDER_PROMPT.split(',')
    else:
        TWEET2_ORDER_PROMPT = []
    REGENERATE_ORDER = get_setting('REGENERATE_ORDER')
    REGENERATE_COUNT = int(get_setting('REGENERATE_COUNT') or 5)
    MAX_CHARACTER_COUNT = int(get_setting('MAX_CHARACTER_COUNT') or 0)
    DEFAULT_USER_ID = get_setting('DEFAULT_USER_ID')
    TWEET2_OVERLAY_URL = get_setting('TWEET2_OVERLAY_URL')
    order_prompt = random.choice(TWEET2_ORDER_PROMPT)  # ORDER配列からランダムに選択
    order_prompt = order_prompt.strip()  # 先頭と末尾の改行コードを取り除く
    if '{nowDateStr}' in order_prompt:
        order_prompt = order_prompt.format(nowDateStr=nowDateStr)

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

reload_settings()    

def response_filter(bot_reply):
    # パターン定義
    pattern1 = r"Tweet:"
    pattern2 = r"Full article:"
    pattern3 = r"learn more:"
    pattern4 = r"More info:"
    pattern5 = r"Tweeted with full URL:"
    pattern6 = r"Read more:"

    # パターンに基づいてテキストをフィルタリング

    bot_reply = re.sub(pattern1, " ", bot_reply).strip()
    bot_reply = re.sub(pattern2, " ", bot_reply).strip()
    bot_reply = re.sub(pattern3, " ", bot_reply).strip()
    bot_reply = re.sub(pattern4, " ", bot_reply).strip()
    bot_reply = re.sub(pattern5, " ", bot_reply).strip()
    bot_reply = re.sub(pattern6, " ", bot_reply).strip()
    response = re.sub(r"\n{2,}", "\n", bot_reply)

    return response.rstrip('\n')


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

def generate_tweet2(user_id, bot_reply, retry_count=0, public_img_url=[]):
    r_bot_reply = bot_reply
    print(f"initiated tweet2. user ID: {user_id}, retry_count: {retry_count}, bot_reply: {bot_reply}, public_img_url: {public_img_url}")
            
    if retry_count >= REGENERATE_COUNT:
        print("tweet2 Exceeded maximum retry attempts.")
        return

    # OpenAI API へのリクエスト
    messages_for_api = [
        {'role': 'system', 'content': TWEET2_SYSTEM_PROMPT}
    ]
    
    if retry_count == 0:    
        messages_for_api.append({'role': 'user', 'content': order_prompt + "\n" + bot_reply})
    else:
        # Retry
        messages_for_api.append({'role': 'user', 'content': REGENERATE_ORDER + "\n" + bot_reply})
    
    print(f"tweet2 initiate re run_conversation. messages_for_api: {messages_for_api}")
    response = run_conversation(AI_MODEL, messages_for_api)
    bot_reply = response.choices[0].message.content
    print(f"before filtered bot_reply: {bot_reply}")
    bot_reply = response_filter(bot_reply)
        
    print(f"tweet2 bot_reply: {bot_reply}, public_img_url: {public_img_url}")
    character_count = int(parse_tweet(bot_reply).weightedLength)
    print(f"tweet2 character_count: {character_count}")
    extract_url = extract_urls_with_indices(bot_reply)

    if extract_url:
        print(f"extract_url:{extract_url}")
        extracted_url = extract_url[0]['url']
    else:
        print(f"URL is not include tweet.")
        generate_tweet2(user_id, r_bot_reply, retry_count + 1, public_img_url)
        return
        
    if 1 <= character_count <= MAX_CHARACTER_COUNT:
        if public_img_url:
            # Download image from URL
            base_img = get_image_with_retry(public_img_url)
            overlay_img = get_image_with_retry(TWEET2_OVERLAY_URL)
            combined_img = overlay_transparent_image(base_img, overlay_img)
            # オーバーレイされた画像をアップロード
            img_data = BytesIO()
            combined_img.save(img_data, format='PNG')
            img_data.seek(0)
            media = api.media_upload(filename='image.png', file=img_data)
            # Tweet with image
            response = client.create_tweet(text=bot_reply, media_ids=[media.media_id])
            print(f"tweet2 response : {response} and image")
        else:
            response = client.create_tweet(text = bot_reply)
            print(f"final tweet2 response : {response}")
    else:
        print(f"character_count is {character_count}. tweet2 is retrying...")
        generate_tweet2(user_id, bot_reply, retry_count + 1, public_img_url)
    return
