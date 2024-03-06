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

from tweet_functions import run_conversation

TWEET1_API_KEY = os.getenv('TWEET1_API_KEY')
TWEET1_API_KEY_SECRET = os.getenv('TWEET1_API_KEY_SECRET')
TWEET1_ACCESS_TOKEN = os.getenv('TWEET1_ACCESS_TOKEN')
TWEET1_ACCESS_TOKEN_SECRET = os.getenv('TWEET1_ACCESS_TOKEN_SECRET')
TWEET2_API_KEY = os.getenv('TWEET2_API_KEY')
TWEET2_API_KEY_SECRET = os.getenv('TWEET2_API_KEY_SECRET')
TWEET2_ACCESS_TOKEN = os.getenv('TWEET2_ACCESS_TOKEN')
TWEET2_ACCESS_TOKEN_SECRET = os.getenv('TWEET2_ACCESS_TOKEN_SECRET')
DATABASE_NAME = os.getenv('DATABASE_NAME')

REQUIRED_ENV_VARS = [
    "TWEET1_SYSTEM_PROMPT",
    "TWEET1_ORDER_PROMPT",
    "TWEET1_MAX_CHARACTER_COUNT",
    "TWEET1_OVERLAY_URL"
    "TWEET2_SYSTEM_PROMPT",
    "TWEET2_ORDER_PROMPT",
    "TWEET2_MAX_CHARACTER_COUNT",
    "TWEET2_OVERLAY_URL"
    "AI_MODEL",
    "TWEET_REGENERATE_ORDER",
    "TWEET_REGENERATE_COUNT",
]

DEFAULT_ENV_VARS = {}

# Firestore クライアントの初期化
try:
    db = firestore.Client(database=DATABASE_NAME)
except Exception as e:
    print(f"Error creating Firestore client: {e}")
    raise

def reload_settings():
    global nowDate, nowDateStr, jst, AI_MODEL, DEFAULT_USER_ID
    global TWEET_REGENERATE_ORDER, TWEET_REGENERATE_COUNT, TWEET_SYSTEM_PROMPT, tweet_order_prompt, TWEET_MAX_CHARACTER_COUNT
    global TWEET1_SYSTEM_PROMPT, TWEET1_ORDER_PROMPT, TWEET1_MAX_CHARACTER_COUNT, TWEET1_OVERLAY_URL, tweet1_order_prompt
    global TWEET2_SYSTEM_PROMPT, TWEET2_ORDER_PROMPT, TWEET2_MAX_CHARACTER_COUNT, TWEET2_OVERLAY_URL, tweet2_order_prompt
    jst = pytz.timezone('Asia/Tokyo')
    nowDate = datetime.now(jst)
    nowDateStr = nowDate.strftime('%Y年%m月%d日 %H:%M:%S')

    AI_MODEL = get_setting('AI_MODEL')
    TWEET1_SYSTEM_PROMPT = get_setting('TWEET1_SYSTEM_PROMPT')
    TWEET1_ORDER_PROMPT = get_setting('TWEET1_ORDER_PROMPT')
    if TWEET1_ORDER_PROMPT:
        TWEET1_ORDER_PROMPT = TWEET1_ORDER_PROMPT.split(',')
    else:
        TWEET1_ORDER_PROMPT = []
    TWEET1_MAX_CHARACTER_COUNT = int(get_setting('TWEET1_MAX_CHARACTER_COUNT') or 0)
    TWEET1_OVERLAY_URL = get_setting('TWEET1_OVERLAY_URL')
    TWEET2_SYSTEM_PROMPT = get_setting('TWEET2_SYSTEM_PROMPT')
    TWEET2_ORDER_PROMPT = get_setting('TWEET2_ORDER_PROMPT')
    if TWEET2_ORDER_PROMPT:
        TWEET2_ORDER_PROMPT = TWEET2_ORDER_PROMPT.split(',')
    else:
        TWEET2_ORDER_PROMPT = []
    TWEET2_MAX_CHARACTER_COUNT = int(get_setting('TWEET2_MAX_CHARACTER_COUNT') or 0)
    TWEET2_OVERLAY_URL = get_setting('TWEET2_OVERLAY_URL')
    TWEET_REGENERATE_ORDER = get_setting('TWEET_REGENERATE_ORDER')
    TWEET_REGENERATE_COUNT = int(get_setting('TWEET_REGENERATE_COUNT') or 5)
    DEFAULT_USER_ID = get_setting('DEFAULT_USER_ID')
    tweet1_order_prompt = random.choice(TWEET1_ORDER_PROMPT) 
    tweet1_order_prompt = tweet1_order_prompt.strip()
    tweet2_order_prompt = random.choice(TWEET2_ORDER_PROMPT)
    tweet2_order_prompt = tweet2_order_prompt.strip()
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

reload_settings()    

def response_filter(bot_reply):
    # パターン定義
    pattern102 = r"!\[.*\]\(.*\.jpg\)|!\[.*\]\(.*\.png\)"
    pattern103 = r"\[画像.*\]"
    pattern104 = r"\(.*\.jpg\)|\(.*\.png\)"
    pattern105 = r"!\[.*\]\(http.*\.(jpg|png)\)"
    pattern106 = r"\[参照元URL\]\((.*?)\)"
    pattern107 = r"\n(http[s]?://[^\s]+)"
    pattern108 = r"https://[^\s]+\.(jpg|png)"
    pattern109 = r"\[参照元\]\((.*?)\)"
    pattern110 = r"\[参照元[:：](https?://[^\]]+)\]"
    pattern111 = r"参照元: (http[s]?://[^\s]+)"
    pattern112 = r"「"
    pattern113 = r"」"
    pattern114 = r"【"
    pattern115 = r"】"
    pattern116 = r"\["
    pattern117 = r"\]"
    pattern118 = r"描いたイラストの"
    pattern119 = r"参照元："
    pattern120 = r"参照元➡️"
    pattern121 = r"参照元👉"
    pattern122 = r"参照元URL:"
    pattern123 = r"参照元はこちら:"
    pattern124 = r"詳細はこちら➡️"
    pattern125 = r"参照元はこちら➡️"
    pattern126 = r"参照元はこちら👉"
    pattern127 = r"参照元はこちら→"
    pattern128 = r"詳細[:：]"
    pattern129 = r"\\n"
    pattern130 = r"参照元[:：].*?\((https?://[^\)]+)\)"
    pattern201 = r"Tweet:"
    pattern202 = r"Full article:"
    pattern203 = r"learn more:"
    pattern204 = r"More info:"
    pattern205 = r"Tweeted with full URL:"
    pattern206 = r"Read more:"

    # パターンに基づいてテキストをフィルタリング
    bot_reply = re.sub(pattern102, "", bot_reply).strip()
    bot_reply = re.sub(pattern103, "", bot_reply).strip()
    bot_reply = re.sub(pattern104, "", bot_reply).strip()
    bot_reply = re.sub(pattern105, "", bot_reply).strip()
    bot_reply = re.sub(pattern106, r" \1", bot_reply).strip()
    bot_reply = re.sub(pattern107, r" \1", bot_reply).strip()
    bot_reply = re.sub(pattern108, "", bot_reply).strip()
    bot_reply = re.sub(pattern109, r" \1", bot_reply).strip()
    bot_reply = re.sub(pattern110, r" \1", bot_reply).strip()
    bot_reply = re.sub(pattern111, r" \1", bot_reply).strip()
    bot_reply = re.sub(pattern112, "　", bot_reply).strip()
    bot_reply = re.sub(pattern113, "", bot_reply).strip()
    bot_reply = re.sub(pattern114, "　", bot_reply).strip()
    bot_reply = re.sub(pattern115, "", bot_reply).strip()
    bot_reply = re.sub(pattern116, "　", bot_reply).strip()
    bot_reply = re.sub(pattern117, "", bot_reply).strip()
    bot_reply = re.sub(pattern118, "", bot_reply).strip()
    bot_reply = re.sub(pattern119, " ", bot_reply).strip()
    bot_reply = re.sub(pattern120, " ", bot_reply).strip()
    bot_reply = re.sub(pattern121, " ", bot_reply).strip()
    bot_reply = re.sub(pattern122, " ", bot_reply).strip()
    bot_reply = re.sub(pattern123, " ", bot_reply).strip()
    bot_reply = re.sub(pattern124, " ", bot_reply).strip()
    bot_reply = re.sub(pattern125, " ", bot_reply).strip()
    bot_reply = re.sub(pattern126, " ", bot_reply).strip()
    bot_reply = re.sub(pattern127, " ", bot_reply).strip()
    bot_reply = re.sub(pattern128, " ", bot_reply).strip()
    bot_reply = re.sub(pattern129, " ", bot_reply).strip()
    bot_reply = re.sub(pattern130, r" \1", bot_reply).strip()
    bot_reply = re.sub(pattern201, " ", bot_reply).strip()
    bot_reply = re.sub(pattern202, " ", bot_reply).strip()
    bot_reply = re.sub(pattern203, " ", bot_reply).strip()
    bot_reply = re.sub(pattern204, " ", bot_reply).strip()
    bot_reply = re.sub(pattern205, " ", bot_reply).strip()
    bot_reply = re.sub(pattern206, " ", bot_reply).strip()
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

def generate_tweet(tweet_no, user_id, bot_reply, retry_count=0, public_img_url=[]):
    r_bot_reply = bot_reply
    print(f"initiated {tweet_no}. user ID: {user_id}, retry_count: {retry_count}, bot_reply: {bot_reply}, public_img_url: {public_img_url}")
    if tweet_no == 'tweet1':
        TWEET_SYSTEM_PROMPT = TWEET1_SYSTEM_PROMPT
        tweet_order_prompt = tweet1_order_prompt
        TWEET_MAX_CHARACTER_COUNT = TWEET1_MAX_CHARACTER_COUNT
        auth = tweepy.OAuthHandler(TWEET1_API_KEY, TWEET1_API_KEY_SECRET)
        auth.set_access_token(TWEET1_ACCESS_TOKEN, TWEET1_ACCESS_TOKEN_SECRET)
        api = tweepy.API(auth)

        client = tweepy.Client(
            consumer_key = TWEET1_API_KEY,
            consumer_secret = TWEET1_API_KEY_SECRET,
            access_token = TWEET1_ACCESS_TOKEN,
            access_token_secret = TWEET1_ACCESS_TOKEN_SECRET
        )
    else:
        TWEET_SYSTEM_PROMPT = TWEET2_SYSTEM_PROMPT
        tweet_order_prompt = tweet2_order_prompt
        TWEET_MAX_CHARACTER_COUNT = TWEET2_MAX_CHARACTER_COUNT
        auth = tweepy.OAuthHandler(TWEET2_API_KEY, TWEET2_API_KEY_SECRET)
        auth.set_access_token(TWEET2_ACCESS_TOKEN, TWEET2_ACCESS_TOKEN_SECRET)
        api = tweepy.API(auth)

        client = tweepy.Client(
            consumer_key = TWEET2_API_KEY,
            consumer_secret = TWEET2_API_KEY_SECRET,
            access_token = TWEET2_ACCESS_TOKEN,
            access_token_secret = TWEET2_ACCESS_TOKEN_SECRET
        )
            
    if retry_count >= TWEET_REGENERATE_COUNT:
        print(f"{tweet_no} Exceeded maximum retry attempts.")
        return

    # OpenAI API へのリクエスト
    messages_for_api = [
        {'role': 'system', 'content': TWEET_SYSTEM_PROMPT}
    ]
    
    if retry_count == 0:    
        messages_for_api.append({'role': 'user', 'content': tweet_order_prompt + "\n" + bot_reply})
    else:
        # Retry
        messages_for_api.append({'role': 'user', 'content': TWEET_REGENERATE_ORDER + "\n" + bot_reply})
    
    print(f"{tweet_no} initiate re run_conversation. messages_for_api: {messages_for_api}")
    response = run_conversation(AI_MODEL, messages_for_api)
    bot_reply = response.choices[0].message.content
    print(f"before filtered bot_reply: {bot_reply}")
    bot_reply = response_filter(bot_reply)
        
    print(f"{tweet_no} bot_reply: {bot_reply}, public_img_url: {public_img_url}")
    character_count = int(parse_tweet(bot_reply).weightedLength)
    print(f"{tweet_no} character_count: {character_count}")
    extract_url = extract_urls_with_indices(bot_reply)

    if extract_url:
        print(f"extract_url:{extract_url}")
        extracted_url = extract_url[0]['url']
    else:
        print(f"URL is not include tweet.")
        generate_tweet(tweet_no, user_id, r_bot_reply, retry_count + 1, public_img_url)
        return
        
    if 1 <= character_count <= TWEET_MAX_CHARACTER_COUNT:
            
        if public_img_url:
            # Download image from URL
            base_img = get_image_with_retry(public_img_url)
            overlay_img = get_image_with_retry(TWEET_OVERLAY_URL)
            combined_img = overlay_transparent_image(base_img, overlay_img)
            # オーバーレイされた画像をアップロード
            img_data = BytesIO()
            combined_img.save(img_data, format='PNG')
            img_data.seek(0)
            media = api.media_upload(filename='image.png', file=img_data)
            # Tweet with image
            response = client.create_tweet(text=bot_reply, media_ids=[media.media_id])
            print(f"{tweet_no} response : {response} and image")
        else:
            response = client.create_tweet(text = bot_reply)
            print(f"final {tweet_no} response : {response}")
    else:
        print(f"character_count is {character_count}. {tweet_no} is retrying...")
        generate_tweet(tweet_no, user_id, bot_reply, retry_count + 1, public_img_url)
    return
