import openai

# OpenAI API 키 입력
openai.api_key = "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"

def chat_with_gpt(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4",  # 최신 모델 사용 가능
        messages=[{"role": "user", "content": prompt}]
    )
    return response["choices"][0]["message"]["content"]

# 테스트 실행
user_input = "라즈베리파이에 대해 알려줘."
response = chat_with_gpt(user_input)
print("ChatGPT 응답:", response)
