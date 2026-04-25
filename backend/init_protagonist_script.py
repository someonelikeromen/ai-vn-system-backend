import urllib.request, json, sys

BASE = "http://localhost:8000"

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return json.loads(r.read())

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())

# 1. 列出小说
novels_data = get("/api/novels/")
novels = novels_data.get("novels", [])
print("=== 现有小说 ===")
for n in novels:
    print(f"  {n['novel_id']} | {n['title']}")
if not novels:
    print("  (无小说，需要先创建)")

sys.exit(0)
