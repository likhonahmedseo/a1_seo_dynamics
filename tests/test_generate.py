import requests

data = {
    "mission": "test",
    "sender_name": "test",
    "sender_company": "test",
    "offer": "test",
    "call_to_action": "test",
}
files = {"contacts_file": ("test.csv", b"email,first_name\ntest@example.com,Test", "text/csv")}
r = requests.post("http://localhost:5000/api/generate-ai", data=data, files=files)
for line in r.iter_lines():
    if line:
        print(line.decode('utf-8'))
