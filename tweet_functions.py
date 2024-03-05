import os
from openai import OpenAI
from datetime import datetime, time, timedelta
import pytz
import requests
from bs4 import BeautifulSoup
from google.cloud import storage
import io
import uuid
import functions_config as cf
import json
import wikipedia

google_api_key = os.getenv("GOOGLE_API_KEY")
google_cse_id = os.getenv("GOOGLE_CSE_ID")

openai_api_key = os.getenv('OPENAI_API_KEY')
gpt_client = OpenAI(api_key=openai_api_key)
public_url = []
public_url_original = []
    
user_id = []

def get_googlesearch(words, num=3, start_index=1, search_lang='lang_ja'):
    base_url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": google_api_key,
        "cx": google_cse_id,
        "q": words,
        "num": num,
        "start": start_index,
        "lr": search_lang
    }

    response = requests.get(base_url, params=params)
    response.raise_for_status()

    search_results = response.json()

    # 検索結果を文字列に整形
    formatted_results = ""
    for item in search_results.get("items", []):
        title = item.get("title")
        link = item.get("link")
        snippet = item.get("snippet")
        formatted_results += f"タイトル: {title}\nリンク: {link}\n概要: {snippet}\n\n"

    return f"SYSTEM:Webページを検索しました。{words}と関係のありそうなURLを読み込んでください。\n" + formatted_results


def search_wikipedia(prompt):
    try:
        wikipedia.set_lang("ja")
        search_result = wikipedia.page(prompt)
        summary = search_result.summary
        page_url = search_result.url

        # 結果を1000文字に切り詰める
        if len(summary) > 1000:
            summary = summary[:1000] + "..."

        return f"SYSTEM: 以下は{page_url}の読み込み結果です。情報を提示するときは情報とともに参照元URLアドレスも案内してください。\n{summary}"
    except wikipedia.exceptions.DisambiguationError as e:
        return f"SYSTEM: 曖昧さ解消が必要です。オプション: {e.options}"
    except wikipedia.exceptions.PageError:
        return "SYSTEM: ページが見つかりませんでした。"


def scraping(link):
    contents = ""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36",
    }
    
    try:
        response = requests.get(link, headers=headers, timeout=5)
        response.raise_for_status()
        response.encoding = response.apparent_encoding  # または特定のエンコーディングを指定
        html = response.text
    except requests.RequestException as e:
        return f"SYSTEM: リンクの読み込み中にエラーが発生しました: {e}"

    soup = BeautifulSoup(html, features="html.parser")

    # Remove all 'a' tags
    for a in soup.findAll('a'):
        a.decompose()

    content = soup.select_one("article, .post, .content")

    if content is None or content.text.strip() == "":
        content = soup.select_one("body")

    if content is not None:
        contents = ' '.join(content.text.split()).replace("。 ", "。\n").replace("! ", "!\n").replace("? ", "?\n").strip()

        # 結果を1000文字に切り詰める
        if len(contents) > 1000:
            contents = contents[:1000] + "..."

    return f"SYSTEM:以下は{link}の読み込み結果です。情報を提示するときは情報とともに参照元URLアドレスも案内してください。\n" + contents

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

def tweet_chatgpt_functions(GPT_MODEL, messages_for_api, USER_ID, PAINT_PROMPT="", max_attempts=5):
    public_url_original = None
    user_id = USER_ID
    paint_prompt = PAINT_PROMPT
    attempt = 0
    i_messages_for_api = messages_for_api.copy()

    search_wikipedia_called = False
    scraping_called = False
    get_googlesearch_called = False

    while attempt < max_attempts:
        response = run_conversation_f(GPT_MODEL, i_messages_for_api)
        if response:
            function_call = response.choices[0].message.function_call
            if function_call:
                if function_call.name == "search_wikipedia" and not search_wikipedia_called:
                    search_wikipedia_called = True
                    arguments = json.loads(function_call.arguments)
                    bot_reply = search_wikipedia(arguments["prompt"])
                    i_messages_for_api.append({"role": "assistant", "content": bot_reply})
                    attempt += 1
                elif function_call.name == "scraping" and not scraping_called:
                    scraping_called = True
                    arguments = json.loads(function_call.arguments)
                    bot_reply = scraping(arguments["link"])
                    i_messages_for_api.append({"role": "assistant", "content": bot_reply})
                    attempt += 1
                elif function_call.name == "get_googlesearch" and not get_googlesearch_called:
                    get_googlesearch_called = True
                    arguments = json.loads(function_call.arguments)
                    bot_reply = get_googlesearch(arguments["words"])
                    i_messages_for_api.append({"role": "assistant", "content": bot_reply})
                    attempt += 1
                else:
                    response = run_conversation(GPT_MODEL, i_messages_for_api)
                    if response:
                        bot_reply = response.choices[0].message.content
                    else:
                        bot_reply = "An error occurred while processing the question"
                    return bot_reply, public_url_original, username                    
            else:
                return response.choices[0].message.content, public_url_original, username
        else:
            return "An error occurred while processing the question", public_url_original, username
    
    return bot_reply, public_url_original, username
