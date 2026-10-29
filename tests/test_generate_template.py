import requests

data = {
    "mission": "test",
    "sender_name": "test",
    "sender_company": "test",
    "offer": "test",
    "call_to_action": "test",
}
files = {"contacts_file": ("test.csv", b"email,first_name\ntest@example.com,Test", "text/csv")}
try:
    r = requests.post("http://localhost:5000/api/generate", data=data, files=files)
    print(r.status_code)
    print(r.json())
except Exception as e:
    print(e)
