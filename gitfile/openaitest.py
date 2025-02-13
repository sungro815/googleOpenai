from dotenv import load_dotenv
from openai import OpenAI
import os

# OpenAI API 키 입력
load_dotenv()
client = OpenAI(api_key="OPENAI_API_KEY")

def chat_with_gpt(prompt):
    response = client.chat.completions.create(
        model="gpt-4",  # 최신 모델 사용 가능
        messages=[{"role": "user", "content": prompt}]
    )
    return response["choices"][0]["message"]["content"]

# 테스트 실행
user_input = "라즈베리파이에 대해 알려줘."
response = chat_with_gpt(user_input)
print("ChatGPT 응답:", response)
