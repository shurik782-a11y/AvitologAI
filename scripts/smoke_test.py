from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
assert c.get("/api/health").json()["status"] == "ok"
r = c.post("/api/projects", json={"name": "TestProj"})
print("create", r.status_code)
p = r.json()
assert p["onboarding_status"] == "awaiting_brief"
msgs = c.get(f"/api/projects/{p['id']}/messages").json()
print("seed", msgs[0]["content"][:40])
assert "Давайте выполним настройку" in msgs[0]["content"]
feed = c.get(f"/api/projects/{p['id']}/avito-feed.xml", params={"token": p["avito_feed_token"]})
print("feed", feed.status_code, feed.headers.get("content-type"))
b = c.get("/api/billing/summary").json()
print("billing", b.get("label") or b)
print("ALL_OK")
