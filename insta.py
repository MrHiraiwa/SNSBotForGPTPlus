import os
from io import BytesIO
import re
import random
from google.cloud import firestore
from datetime import datetime, time, timedelta
import pytz
from flask import Flask, request, render_template, session, redirect, url_for, jsonify
import unicodedata
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import requests
import tiktoken
from PIL import Image
from instapy import InstaPy

from note_functions import run_conversation

INSTA_USERNAME = os.getenv('INSTA_USERNAME')
INSTA_PASSWORD = os.getenv('INSTA_PASSWORD')

session = InstaPy(username='INSTA_USERNAME', password='INSTA_PASSWORD')

DATABASE_NAME = os.getenv('DATABASE_NAME')

REQUIRED_ENV_VARS = [
    "NOTE_SYSTEM_PROMPT",
    "NOTE_ORDER_PROMPT",
    "NOTE_OVERLAY_URL",
    "AI_MODEL"
]

DEFAULT_ENV_VARS = {}

EMAIL = 'your email'
PASSWORD = 'your password'
USER_ID = 'your user_id'

TITLE = 'Sample'
CONTENT_PATH = 'content.txt'
TAG_LIST = ['sample_tag']


# Firestore クライアントの初期化
try:
    db = firestore.Client(database=DATABASE_NAME)
except Exception as e:
    print(f"Error creating Firestore client: {e}")
    raise

def reload_settings():
    global nowDate, nowDateStr, jst, AI_MODEL, DEFAULT_USER_ID
    global NOTE_SYSTEM_PROMPT, NOTE_ORDER_PROMPT, NOTE_OVERLAY_URL
    jst = pytz.timezone('Asia/Tokyo')
    nowDate = datetime.now(jst)
    nowDateStr = nowDate.strftime('%Y年%m月%d日 %H:%M:%S')

    AI_MODEL = get_setting('AI_MODEL')
    NOTE_SYSTEM_PROMPT = get_setting('NOTE_SYSTEM_PROMPT')
    NOTE_ORDER_PROMPT = get_setting('NOTE_ORDER_PROMPT')
    if NOTE_ORDER_PROMPT:
        NOTE_ORDER_PROMPT = NOTE_ORDER_PROMPT.split(',')
    else:
        NOTE_ORDER_PROMPT = []
    NOTE_OVERLAY_URL = get_setting('NOTE_OVERLAY_URL')
    DEFAULT_USER_ID = get_setting('DEFAULT_USER_ID')
    note_order_prompt = random.choice(NOTE_ORDER_PROMPT) 
    note_order_prompt = note_order_prompt.strip()
    if '{nowDateStr}' in note_order_prompt:
        note_order_prompt = note_order_prompt.format(nowDateStr=nowDateStr)

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

def generate_note(user_id, bot_reply, public_img_url=[]):
    r_bot_reply = bot_reply
    extract_url = extract_urls_with_indices(bot_reply)
    print(f"initiated note. user ID: {user_id}, retry_count: {retry_count}, bot_reply: {bot_reply}, public_img_url: {public_img_url}")
    note_system_prompt = NOTE_SYSTEM_PROMPT
    note_overlay_url = NOTE_OVERLAY_URL
            
    # OpenAI API へのリクエスト
    messages_for_api = [
        {'role': 'system', 'content': note_system_prompt}
    ]
        
    messages_for_api.append({'role': 'user', 'content': note_order_prompt + "\n" + bot_reply})
    
    print(f"note initiate run_conversation. messages_for_api: {messages_for_api}")
    response = run_conversation(AI_MODEL, messages_for_api)
    bot_reply = response.choices[0].message.content
    print(f"before filtered bot_reply: {bot_reply}")
    bot_reply = response_filter(bot_reply)
        
    print(f"note bot_reply: {bot_reply}, public_img_url: {public_img_url}")
    character_count = int(parse_tweet(bot_reply).weightedLength)
    print(f"note character_count: {character_count}")
        
    if public_img_url:
        # Download image from URL
        base_img = get_image_with_retry(public_img_url)
        overlay_img = get_image_with_retry(note_overlay_url)
        combined_img = overlay_transparent_image(base_img, overlay_img)
        # オーバーレイされた画像をアップロード
        img_data = BytesIO()
        combined_img.save(img_data, format='PNG')
        img_data.seek(0)
        media = api.media_upload(filename='image.png', file=img_data)
        # note with image
        note = Note(email=NOTE_EMAIL, password=NOTE_PASSWORD, user_id=NOTE_USERID)
        print(note.create_article(title=TITLE, file_name=CONTENT_PATH, input_tag_list=TAG_LIST))
    else:
        note = Note(email=NOTE_EMAIL, password=NOTE_PASSWORD, user_id=NOTE_USERID)
        print(note.create_article(title=TITLE, file_name=CONTENT_PATH, input_tag_list=TAG_LIST))
    return
