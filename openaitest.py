from dotenv import load_dotenv
from openai import OpenAI
import os

# .env 파일 로드
load_dotenv()

# 환경변수에서 API 키 가져오기
api_key = os.getenv("OPENAI_API_KEY")
if api_key is None:
    raise ValueError("API 키가 설정되지 않았습니다. .env 파일을 확인해주세요.")

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=api_key)

def chat_with_gpt(prompt):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content  # 최신 API에서는 이렇게 호출

# 테스트 실행
user_input = "라즈베리파이에 대해 알려줘."
response = chat_with_gpt(user_input)
print("ChatGPT 응답:", response)