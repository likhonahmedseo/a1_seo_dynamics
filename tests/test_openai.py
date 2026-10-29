import os

# Read .env file directly — bypass dotenv caching
with open('.env', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            os.environ[k.strip()] = v.strip()

api_key = os.environ.get('OPENAI_API_KEY', '')
print(f'Key loaded: {api_key[:14]}...{api_key[-6:]}')
print(f'Key length: {len(api_key)} chars')

from openai import OpenAI

try:
    client = OpenAI(api_key=api_key)
    models = list(client.models.list())
    print(f'KEY VALID - {len(models)} models accessible')
    resp = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{'role': 'user', 'content': 'Reply with exactly: CONNECTED AND WORKING'}],
        max_tokens=10,
    )
    print(f'GPT RESPONSE: {resp.choices[0].message.content.strip()}')
    print('\n>>> ALL SYSTEMS GO - OpenAI API is fully working <<<')
except Exception as e:
    print(f'\n>>> FAILED: {e}')
