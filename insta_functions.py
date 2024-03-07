import os
from openai import OpenAI

openai_api_key = os.getenv('OPENAI_API_KEY')
gpt_client = OpenAI(api_key=openai_api_key)
    
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
