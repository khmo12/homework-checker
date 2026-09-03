from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if api_key:
    print("API 키 로드 성공! 길이:", len(api_key))
else:
    print("API 키를 찾지 못했습니다. .env 파일을 확인하세요.")