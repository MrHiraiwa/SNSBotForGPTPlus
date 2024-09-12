import os
from openai import OpenAI
import time
from datetime import datetime, timedelta
import pytz
import requests
from bs4 import BeautifulSoup
from bs4.element import Comment
import io
import uuid
import functions_config as cf
import json
from google.cloud import firestore
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from urllib.parse import urljoin, quote, quote
import urllib.parse

DATABASE_NAME = os.getenv('DATABASE_NAME')

openai_api_key = os.getenv('OPENAI_API_KEY')
gpt_client = OpenAI(api_key=openai_api_key)

try:
    db = firestore.Client(database=DATABASE_NAME)
except Exception as e:
    print(f"Error creating Firestore client: {e}")
    raise

public_url = []
public_url_original = []
    
user_id = []
jst = pytz.timezone('Asia/Tokyo')
nowDate = datetime.now(jst)
nowDateStr = nowDate.strftime('%Y年%m月%d日 %H:%M:%S')

def create_firestore_document_id_from_url(url):
    return urllib.parse.quote_plus(url)
    
def check_url_in_firestore(url, user_id):
    url_encoded = create_firestore_document_id_from_url(url)
    user_doc_ref = db.collection(u'users').document(user_id)
    url_doc_ref = user_doc_ref.collection('scraped_urls').document(url_encoded)

    doc = url_doc_ref.get()
    return doc.exists

# Seleniumの設定
options = Options()
options.add_argument("--headless")  
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

# ユーザーエージェントを偽装する
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")

driver = webdriver.Chrome(options=options)  

def link_results(query):
    return google_search.results(query,10)

def tag_visible(element):
    if element.parent.name in ['style', 'script', 'head', 'title', 'meta', '[document]']:
        return False
    if isinstance(element, Comment):
        return False
    return True

def scrape_links_and_text(url, read_links_count, user_id, partial_match_filter_words, full_match_filter_words):
    print(f"partial_match_filter_words: {partial_match_filter_words}, full_match_filter_words: {full_match_filter_words}")
    retries = 3  # 最大リトライ回数
    for attempt in range(retries):
        try:
            # 指定したURLに移動
            driver.get(url)

            # 任意の要素がロードされるまで待つ
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            # スクロールしてページの追加ロードを待つ
            last_height = driver.execute_script("return document.body.scrollHeight")
            while True:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(10)  # 追加コンテンツのロードを待つ
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            result = ""

            # 初期フレームのリンクを取得
            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")
            links = soup.find_all('a')
            for link in links:
                link_url = urljoin(url, link.get('href', ''))
                text = link.text.strip()
                if not any(filtered_text in text for filtered_text in partial_match_filter_words) and not any(filtered_url in link_url for filtered_url in partial_match_filter_words) and not check_url_in_firestore(link_url, user_id):
                    if text not in full_match_filter_words and link_url not in full_match_filter_words:
                        result += f"{link_url} : {text}\n"

            # iframe内のリンクを取得
            iframes = driver.find_elements(By.TAG_NAME, 'iframe')
            for i in range(len(iframes)):
                driver.switch_to.frame(iframes[i])
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                iframe_html = driver.page_source
                iframe_soup = BeautifulSoup(iframe_html, "html.parser")
                iframe_links = iframe_soup.find_all('a')
                for link in iframe_links:
                    link_url = urljoin(url, link.get('href', ''))
                    text = link.text.strip()
                    if not any(filtered_text in text for filtered_text in partial_match_filter_words) and not any(filtered_url in link_url for filtered_url in partial_match_filter_words) and not check_url_in_firestore(link_url, user_id):
                        if text not in full_match_filter_words and link_url not in full_match_filter_words:
                            result += f"{link_url} : {text}\n"
                        
                # iframe内のテキストも取得
                iframe_texts = iframe_soup.findAll(text=True)
                visible_texts = filter(tag_visible, iframe_texts)
                result += " ".join(t.strip() for t in visible_texts)

                driver.switch_to.default_content()

            if not result:
                raise Exception("No links found matching the criteria")


            return  f"SYSTEM:以下は{url}の読み込み結果です。詳細の確認のため1番上のURLを読み込んでください。\n" + result[:read_links_count]

        except Exception as e:
            if attempt < retries - 1:  # 最後の試みではない場合
                time.sleep(10)  # 10秒待って再試行
                continue
            else:
                print(f"An error occurred: {e}")
                time.sleep(10)  # 10秒待って再試行
                return  f"SYSTEM:{url}の読み込みに失敗しました。10秒経過したのでURLのリストの読み込みを再度試みてください。"

def scraping(url, read_text_count, user_id):
    retries = 3  # Maximum number of retries
    for attempt in range(retries):
        try:
            # 指定したURLに移動
            driver.get(url)

            # 任意の要素がロードされるまで待つ
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            texts = soup.findAll(text=True)
            visible_texts = filter(tag_visible, texts)
            result = " ".join(t.strip() for t in visible_texts)

            # Remove extra whitespace by splitting and joining
            result = ' '.join(result.split())
            print(result[:read_text_count])
            return f"SYSTEM:現在、日本時刻で{nowDateStr}です。以下は{url}の読み込み結果です。先ほど読み込んだページの内容からイメージを詳細に思い描いて画像を生成してください。画像生成の実行には長い文章を指定して、より具体的な画像が生成されるようにしてください。\n" + result[:read_text_count]  

        except Exception as e:
            if attempt < retries - 1:  # if it's not the last attempt
                time.sleep(10)  # wait for 10 seconds before retrying
                continue
            else:
                print(f"An error occurred: {e}")
                time.sleep(10)  # wait for 10 seconds before retrying
                return  f"SYSTEM:{url}の読み込みに失敗しました。10秒経過したので再度試みてください。"  

def generate_image(prompt, paint_prompt, user_id, PAINTING_ON):
    image_result = ""
    if PAINTING_ON  == 'False':
        return "SYSTEM: 現在、日本時刻で" + nowDateStr + "です。イラストを生成しました。先ほど読み込んだページの情報を元に、できるだけ文章量を膨らませて文章を生成してください。ページの情報が現在日時よりも古かった場合は終わった情報として文章を生成してください。文章の一番最後にハイパーリンク形式で参照元のURLを記載してください。![画像](https://dummy.net/dummy.jpg)", image_result
    i_prompt = prompt + "\n" + paint_prompt
    print(f"generate_image prompt:{prompt}")
    try:
        response = gpt_client.images.generate(
            model="dall-e-3",
            prompt=i_prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_result = response.data[0].url
        print(f"image_result: {image_result}")
        return "SYSTEM: 現在、日本時刻で" + nowDateStr + "です。イラストを生成しました。先ほど読み込んだページの情報を元に、できるだけ文章量を膨らませて文章を生成してください。ページの情報が現在日時よりも古かった場合は終わった情報として文章を生成してください。文章の一番最後にハイパーリンク形式で参照元のURLを記載してください。![画像](https://dummy.net/dummy.jpg)", image_result
    except Exception as e:
        if "content_policy_violation" in str(e):
            return "SYSTEM: 先ほど読み込んだページの内容からイメージを詳細に思い描いて画像を再生成してください。画像生成の実行には長い文章を指定して、より具体的な画像が生成されるようにしてください。", image_result
        time.sleep(10)
        print(f"Errors : {e}")
        return f"SYSTEM: 画像生成にエラーが発生しました。{prompt}の内容で再度画像を生成してください。", image_result

def run_conversation(GPT_MODEL, messages):
    try:
        response = gpt_client.chat.completions.create(
            model=GPT_MODEL,
            messages=messages,
        )
        return response  # レスポンス全体を返す
    except Exception as e:
        print(f"An error occurred: {e}")
        return None  # エラー時には None を返す

def run_conversation_f(GPT_MODEL, messages):
    try:
        response = gpt_client.chat.completions.create(
            model=GPT_MODEL,
            messages=messages,
            functions=cf.functions,
            function_call="auto",
        )
        return response  # レスポンス全体を返す
    except Exception as e:
        print(f"An error occurred: {e}")
        return None  # エラー時には None を返す

def chatgpt_functions(GPT_MODEL, messages_for_api, USER_ID, PAINT_PROMPT, READ_TEXT_COUNT, READ_LINKS_COUNT, PARTIAL_MATCH_FILTER_WORDS, FULL_MATCH_FILTER_WORDS, PAINTING_ON='False', max_attempts=10):
    image_result = ""
    user_id = USER_ID
    paint_prompt = PAINT_PROMPT
    attempt = 0
    read_links_count = READ_LINKS_COUNT
    read_text_count = READ_TEXT_COUNT
    i_messages_for_api = messages_for_api.copy()
    generate_image_called = False
    scraping_called = False
    scrape_links_and_text_called = False
    partial_match_filter_words = PARTIAL_MATCH_FILTER_WORDS
    full_match_filter_words = FULL_MATCH_FILTER_WORDS

    while attempt < max_attempts:
        print(f"GPT_MODEL: {GPT_MODEL}, i_messages_for_api: {i_messages_for_api}")
        response = run_conversation_f(GPT_MODEL, i_messages_for_api)
        print(f"first response: {response}")
        if response:
            function_call = response.choices[0].message.function_call
            if function_call:
                print(f"function_call: {function_call}")
                if function_call.name == "generate_image" and not generate_image_called:
                    generate_image_called = True
                    arguments = json.loads(function_call.arguments)
                    if isinstance(arguments["prompt"], list):
                        arguments["prompt"] = " ".join(arguments["prompt"])
                    bot_reply, image_result = generate_image(arguments["prompt"], paint_prompt, user_id, PAINTING_ON)
                    i_messages_for_api.append({"role": "user", "content": bot_reply})
                    print(f"generate_image: {bot_reply}")
                    if image_result == ""and PAINTING_ON == 'True':
                        generate_image_called = False
                    attempt += 1
                elif function_call.name == "scraping" and not scraping_called:
                    scraping_called = True
                    arguments = json.loads(function_call.arguments)
                    bot_reply = scraping(arguments["link"], read_text_count, user_id)
                    i_messages_for_api.append({"role": "user", "content": bot_reply})
                    print(f"scraping: {bot_reply}")
                    attempt += 1
                elif function_call.name == "scrape_links_and_text" and not scrape_links_and_text_called:
                    scrape_links_and_text_called = True
                    arguments = json.loads(function_call.arguments)
                    bot_reply = scrape_links_and_text(arguments["link"], read_links_count, user_id, partial_match_filter_words, full_match_filter_words)
                    i_messages_for_api.append({"role": "user", "content": bot_reply})
                    print("<----------------フィルタ対象の文章はここから---------------->")
                    print(f"scrape_links_and_text: {bot_reply}")
                    print("<----------------フィルタ対象の文章はここまで---------------->")
                    attempt += 1
                else:
                    if generate_image_called == False and PAINTING_ON  == 'True':
                        print("generate_image_called: False")
                        i_messages_for_api.append({"role": "user", "content": "SYSTEM: 先ほど読み込んだページの内容からイメージを詳細に思い描いて画像を生成してください。画像生成の実行には長い文章を指定して、より具体的な画像が生成されるようにしてください。"})
                        attempt += 1
                    else:
                        print(f"GPT_MODEL: {GPT_MODEL}, i_messages_for_api: {i_messages_for_api}")
                        response = run_conversation(GPT_MODEL, i_messages_for_api)
                        print(f"else response: {response}")
                        if response:
                            bot_reply = response.choices[0].message.content, image_result
                        else:
                            bot_reply = "An error occurred while processing the question"
                        return bot_reply, image_result   
            else:
                attempt += 1
                if scraping_called == False and scrape_links_and_text_called == False:
                    i_messages_for_api.append({"role": "user", "content": "SYSTEM: ページ読み込み機能や検索機能を一つも呼び出していないため、指示に基づきURLからのページの読み込み、又は検索を実施してください。"})
                elif generate_image_called == False and PAINTING_ON  == 'True':
                    i_messages_for_api.append({"role": "user", "content": "SYSTEM: 先ほど読み込んだページの内容からイメージを詳細に思い描いて画像を生成してください。画像生成の実行には長い文章を指定して、より具体的な画像が生成されるようにしてください。"})                    
                else:
                    if image_result == "" and PAINTING_ON  == 'True':
                        print("Error attempt: not image.")
                        
                        return "", image_result
                    
                    return response.choices[0].message.content, image_result
        else:
            print("Error attempt: not response.")
            
            return "", image_result
    print(f"attempt: {attempt}")
    if image_result == "":
        print("Error attempt: not image.")
        
        return "", image_result
    
    return bot_reply, image_result
