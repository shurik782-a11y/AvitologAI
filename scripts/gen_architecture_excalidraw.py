#!/usr/bin/env python3
"""Generate docs/architecture.excalidraw for Avitolog bot."""
from __future__ import annotations

import json
import random
from pathlib import Path

rng = random.Random(42)


def nid(p: str) -> str:
    return f"{p}_{rng.randint(10**8, 10**9 - 1)}"


def el(
    etype: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    stroke="#1e1e1e",
    bg="transparent",
    width=2,
    style="solid",
) -> dict:
    return {
        "id": nid(etype[:4]),
        "type": etype,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "angle": 0,
        "strokeColor": stroke,
        "backgroundColor": bg,
        "fillStyle": "solid",
        "strokeWidth": width,
        "strokeStyle": style,
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": {"type": 3} if etype in {"rectangle", "diamond"} else None,
        "seed": rng.randint(1, 10**9),
        "versionNonce": rng.randint(1, 10**9),
        "isDeleted": False,
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
    }


def rect(x, y, w, h, **kw):
    return el("rectangle", x, y, w, h, **kw)


def diamond(x, y, w, h, **kw):
    return el("diamond", x, y, w, h, **kw)


def text(x, y, content: str, *, size=16, align="left", stroke="#1e1e1e", w=None):
    lines = content.split("\n")
    tw = w if w is not None else max((len(L) for L in lines), default=1) * size * 0.52
    th = size * 1.3 * max(len(lines), 1)
    t = el("text", x, y, tw, th, stroke=stroke, width=1)
    t.update(
        {
            "text": content,
            "fontSize": size,
            "fontFamily": 1,
            "textAlign": align,
            "verticalAlign": "top",
            "containerId": None,
            "originalText": content,
            "autoResize": True,
            "lineHeight": 1.25,
            "roundness": None,
        }
    )
    return t


def label(box, content: str, *, size=15):
    return text(
        box["x"] + 12,
        box["y"] + 14,
        content,
        size=size,
        align="center",
        w=box["width"] - 24,
    )


def arrow(x1, y1, x2, y2, *, start=None, end=None, points=None, stroke="#1e1e1e"):
    a = el("arrow", x1, y1, max(abs(x2 - x1), 1), max(abs(y2 - y1), 1), stroke=stroke)
    a["points"] = points if points is not None else [[0, 0], [x2 - x1, y2 - y1]]
    a["lastCommittedPoint"] = None
    a["startBinding"] = {"elementId": start["id"], "focus": 0, "gap": 6} if start else None
    a["endBinding"] = {"elementId": end["id"], "focus": 0, "gap": 6} if end else None
    a["startArrowhead"] = None
    a["endArrowhead"] = "arrow"
    a["elbowed"] = False
    if start is not None:
        start["boundElements"].append({"id": a["id"], "type": "arrow"})
    if end is not None:
        end["boundElements"].append({"id": a["id"], "type": "arrow"})
    return a


def mid(b):
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


E: list[dict] = []

# Title
E.append(text(40, 24, "Avitolog — архитектура", size=32, stroke="#212529"))
E.append(
    text(
        40,
        70,
        "Мультипроект · чат/контекст на проект · метрики · креатив → утверждение → Avito Автозагрузка",
        size=16,
        stroke="#868e96",
    )
)

# ===================== 0. WORKSPACE / PROJECTS =====================
L0 = rect(40, 110, 1520, 200, bg="#e3fafc", stroke="#0c8599")
E.append(L0)
E.append(text(55, 120, "0. Workspace · проекты (изоляция)", size=17, stroke="#0c8599"))

ws = rect(70, 155, 200, 120, bg="#99e9f2", stroke="#0c8599")
add_p = rect(300, 155, 180, 120, bg="#66d9e8", stroke="#0c8599")
proj = rect(510, 155, 520, 120, bg="#c5f6fa", stroke="#0b7285")
p_cfg = rect(1060, 155, 220, 50, bg="#99e9f2", stroke="#0c8599")
p_ctx = rect(1300, 155, 220, 50, bg="#99e9f2", stroke="#0c8599")
p_sys = rect(1060, 220, 220, 55, bg="#66d9e8", stroke="#0b7285")
p_chat = rect(1300, 220, 220, 55, bg="#66d9e8", stroke="#0b7285")
E.extend([ws, add_p, proj, p_cfg, p_ctx, p_sys, p_chat])
E.append(label(ws, "Workspace\nuser / org\nсписок проектов", size=14))
E.append(label(add_p, "+ Add Project\nимя · ниша\nAvito cabinet", size=14))
E.append(
    label(
        proj,
        "Project {id}\nизолированный контур: настройки · контекст ·\nsystem prompt · чат · jobs · метрики",
        size=14,
    )
)
E.append(label(p_cfg, "settings JSON\nмодель · тон · лимиты", size=13))
E.append(label(p_ctx, "context pack\nбренд · УТП · запреты", size=13))
E.append(label(p_sys, "system prompt\nправила авитолога", size=13))
E.append(label(p_chat, "project chat\nистория + thread", size=13))

E.append(arrow(ws["x"] + ws["width"], mid(ws)[1], add_p["x"], mid(add_p)[1], start=ws, end=add_p))
E.append(arrow(add_p["x"] + add_p["width"], mid(add_p)[1], proj["x"], mid(proj)[1], start=add_p, end=proj))
E.append(arrow(proj["x"] + proj["width"], proj["y"] + 30, p_cfg["x"], mid(p_cfg)[1], start=proj, end=p_cfg))
E.append(arrow(proj["x"] + proj["width"], proj["y"] + 90, p_sys["x"], mid(p_sys)[1], start=proj, end=p_sys))
E.append(arrow(p_cfg["x"] + p_cfg["width"], mid(p_cfg)[1], p_ctx["x"], mid(p_ctx)[1], start=p_cfg, end=p_ctx))
E.append(arrow(p_sys["x"] + p_sys["width"], mid(p_sys)[1], p_chat["x"], mid(p_chat)[1], start=p_sys, end=p_chat))

# ===================== 1. CLIENT =====================
L1 = rect(40, 340, 1520, 150, bg="#e7f5ff", stroke="#1971c2")
E.append(L1)
E.append(text(55, 350, "1. Клиент · Telegram Mini App", size=17, stroke="#1971c2"))

tg = rect(70, 385, 170, 80, bg="#a5d8ff", stroke="#1971c2")
home = rect(270, 385, 200, 80, bg="#74c0fc", stroke="#1864ab")
chat_ui = rect(500, 385, 230, 80, bg="#4dabf7", stroke="#1864ab")
rev = rect(760, 385, 230, 80, bg="#a5d8ff", stroke="#1971c2")
metrics_ui = rect(1020, 385, 220, 80, bg="#d0ebff", stroke="#1971c2")
ok = rect(1270, 385, 250, 80, bg="#d0ebff", stroke="#1971c2")
E.extend([tg, home, chat_ui, rev, metrics_ui, ok])
E.append(label(tg, "Telegram\ndeep-link", size=14))
E.append(label(home, "Projects home\nсписок / +проект", size=14))
E.append(label(chat_ui, "Chat UI\nв контексте проекта", size=14))
E.append(label(rev, "Утверждение\nтекст+фото · правки", size=14))
E.append(label(metrics_ui, "Метрики UI\nпо проекту / period", size=14))
E.append(label(ok, "Результат\nссылка Avito", size=14))

# ===================== 2. GATEWAY =====================
L2 = rect(40, 520, 1520, 120, bg="#fff9db", stroke="#f08c00")
E.append(L2)
E.append(text(55, 530, "2. Gateway", size=17, stroke="#f08c00"))

bot = rect(70, 560, 200, 60, bg="#ffec99", stroke="#f08c00")
api = rect(300, 560, 280, 60, bg="#ffe066", stroke="#e67700")
auth = rect(610, 560, 200, 60, bg="#ffec99", stroke="#f08c00")
q = rect(840, 560, 200, 60, bg="#fff3bf", stroke="#f08c00")
proj_api = rect(1080, 560, 440, 60, bg="#ffec99", stroke="#f08c00")
E.extend([bot, api, auth, q, proj_api])
E.append(label(bot, "Bot · aiogram", size=14))
E.append(label(api, "FastAPI · WebApp / jobs", size=14))
E.append(label(auth, "initData verify", size=14))
E.append(label(q, "Queue Redis", size=14))
E.append(label(proj_api, "API: /projects · /chats · /metrics · /jobs", size=14))

# ===================== 3. ORCHESTRATOR =====================
L3 = rect(40, 670, 1520, 200, bg="#ebfbee", stroke="#2f9e44")
E.append(L3)
E.append(text(55, 680, "3. Orchestrator (внутри project_id)", size=17, stroke="#2f9e44"))

brief = rect(70, 720, 140, 90, bg="#b2f2bb", stroke="#2f9e44")
analyze = rect(240, 720, 150, 90, bg="#8ce99a", stroke="#2f9e44")
create = rect(420, 720, 160, 90, bg="#69db7c", stroke="#2f9e44")
review = diamond(620, 710, 170, 110, bg="#c3fae8", stroke="#0ca678")
revise = rect(840, 720, 160, 90, bg="#96f2d7", stroke="#0ca678")
publish = rect(1040, 720, 160, 90, bg="#51cf66", stroke="#2b8a3e")
done = rect(1240, 720, 130, 90, bg="#d3f9d8", stroke="#2f9e44")
emit = rect(1400, 720, 130, 90, bg="#b2f2bb", stroke="#2f9e44")
E.extend([brief, analyze, create, review, revise, publish, done, emit])
E.append(label(brief, "BRIEF\nиз чата", size=13))
E.append(label(analyze, "ANALYZE\n+ project ctx", size=13))
E.append(label(create, "CREATE\nтекст+фото", size=13))
E.append(label(review, "REVIEW?\nда/правки", size=13))
E.append(label(revise, "REVISE\nprompt", size=13))
E.append(label(publish, "PUBLISH\nАвтозагрузка", size=13))
E.append(label(done, "DONE", size=13))
E.append(label(emit, "emit\nmetrics", size=13))

# ===================== 4. AI =====================
L4 = rect(40, 900, 900, 240, bg="#f8f0fc", stroke="#9c36b5")
E.append(L4)
E.append(text(55, 910, "4. AI · prompt assembly per project", size=17, stroke="#9c36b5"))

brain = rect(70, 945, 260, 170, bg="#eebefa", stroke="#9c36b5")
vision = rect(360, 945, 210, 70, bg="#da77f2", stroke="#9c36b5")
flux = rect(360, 1035, 210, 70, bg="#e599f7", stroke="#9c36b5")
finder = rect(600, 945, 300, 70, bg="#f3d9fa", stroke="#9c36b5")
rules = rect(600, 1035, 300, 70, bg="#f3d9fa", stroke="#9c36b5")
E.extend([brain, vision, flux, finder, rules])
E.append(
    label(
        brain,
        "Claude Sonnet\nsys = project.system_prompt\n+ context pack\n+ chat history\n+ Avito rules",
        size=13,
    )
)
E.append(label(vision, "Vision · фото-пример", size=13))
E.append(label(flux, "Flux · генерация", size=13))
E.append(label(finder, "Photo Finder · поиск фото", size=13))
E.append(label(rules, "Rules Engine · лимиты Avito", size=13))

# ===================== 5. INTEGRATIONS + METRICS =====================
L5 = rect(980, 900, 580, 240, bg="#fff5f5", stroke="#e03131")
E.append(L5)
E.append(text(995, 910, "5. Data · Integrations · Metrics", size=17, stroke="#e03131"))

pg = rect(1010, 945, 240, 80, bg="#ffa8a8", stroke="#e03131")
s3 = rect(1280, 945, 240, 80, bg="#ffc9c9", stroke="#e03131")
avito = rect(1010, 1045, 240, 70, bg="#ff8787", stroke="#c92a2a")
met = rect(1280, 1045, 240, 70, bg="#fcc2d7", stroke="#c2255c")
E.extend([pg, s3, avito, met])
E.append(
    label(
        pg,
        "Postgres\nprojects · chats · msgs\njobs · drafts · events",
        size=12,
    )
)
E.append(label(s3, "S3 · медиа / фиды", size=13))
E.append(label(avito, "Avito Autoload API", size=13))
E.append(label(met, "Metrics store\nagg + dashboard", size=13))

# ===================== ARROWS =====================
E.append(arrow(mid(home)[0], home["y"], mid(ws)[0], ws["y"] + ws["height"], start=home, end=ws, stroke="#0c8599"))
E.append(arrow(mid(chat_ui)[0], chat_ui["y"], mid(p_chat)[0], p_chat["y"] + p_chat["height"], start=chat_ui, end=p_chat, stroke="#0c8599"))
E.append(
    arrow(
        mid(metrics_ui)[0],
        metrics_ui["y"] + metrics_ui["height"],
        mid(met)[0],
        met["y"],
        start=metrics_ui,
        end=met,
        stroke="#c2255c",
    )
)

E.append(arrow(*mid(tg), bot["x"] + 60, bot["y"], start=tg, end=bot))
E.append(arrow(mid(home)[0], home["y"] + home["height"], api["x"] + 40, api["y"], start=home, end=api))
E.append(arrow(mid(chat_ui)[0], chat_ui["y"] + chat_ui["height"], mid(api)[0], api["y"], start=chat_ui, end=api))
E.append(arrow(bot["x"] + bot["width"], mid(bot)[1], api["x"], mid(api)[1], start=bot, end=api))
E.append(arrow(api["x"] + api["width"], mid(api)[1], auth["x"], mid(auth)[1], start=api, end=auth))
E.append(arrow(auth["x"] + auth["width"], mid(auth)[1], q["x"], mid(q)[1], start=auth, end=q))
E.append(arrow(q["x"] + q["width"], mid(q)[1], proj_api["x"], mid(proj_api)[1], start=q, end=proj_api))

E.append(arrow(mid(chat_ui)[0] + 40, chat_ui["y"] + chat_ui["height"], mid(brief)[0], brief["y"], start=chat_ui, end=brief, stroke="#2f9e44"))
E.append(arrow(brief["x"] + brief["width"], mid(brief)[1], analyze["x"], mid(analyze)[1], start=brief, end=analyze))
E.append(arrow(analyze["x"] + analyze["width"], mid(analyze)[1], create["x"], mid(create)[1], start=analyze, end=create))
E.append(arrow(create["x"] + create["width"], mid(create)[1], review["x"], mid(review)[1], start=create, end=review))
E.append(arrow(review["x"] + review["width"], mid(review)[1], publish["x"], mid(publish)[1], start=review, end=publish, stroke="#2f9e44"))
E.append(arrow(publish["x"] + publish["width"], mid(publish)[1], done["x"], mid(done)[1], start=publish, end=done))
E.append(arrow(done["x"] + done["width"], mid(done)[1], emit["x"], mid(emit)[1], start=done, end=emit))

E.append(arrow(mid(review)[0], review["y"], mid(rev)[0], rev["y"] + rev["height"], start=review, end=rev, stroke="#1971c2"))
E.append(arrow(rev["x"] + rev["width"] / 2, rev["y"] + rev["height"], mid(revise)[0], revise["y"], start=rev, end=revise, stroke="#0ca678"))
x0 = mid(revise)[0]
x1 = mid(create)[0]
E.append(
    arrow(
        x0,
        revise["y"] + revise["height"],
        x1,
        create["y"] + create["height"],
        start=revise,
        end=create,
        points=[[0, 0], [0, 40], [x1 - x0, 40], [x1 - x0, 0]],
        stroke="#0ca678",
    )
)
E.append(text(700, 830, "цикл правок", size=13, stroke="#0ca678"))
E.append(text(820, 690, "одобрено", size=13, stroke="#2f9e44"))

# project config → AI
E.append(arrow(mid(p_sys)[0], p_sys["y"] + p_sys["height"], brain["x"] + 40, brain["y"], start=p_sys, end=brain, stroke="#9c36b5"))
E.append(arrow(mid(p_ctx)[0], p_ctx["y"] + p_ctx["height"], brain["x"] + 180, brain["y"], start=p_ctx, end=brain, stroke="#9c36b5"))
E.append(arrow(mid(p_chat)[0], p_chat["y"] + p_chat["height"], brain["x"] + 120, brain["y"], start=p_chat, end=brain, stroke="#9c36b5"))

E.append(arrow(mid(analyze)[0], analyze["y"] + analyze["height"], brain["x"] + 60, brain["y"], start=analyze, end=brain))
E.append(arrow(mid(create)[0], create["y"] + create["height"], mid(vision)[0], vision["y"], start=create, end=vision))
E.append(arrow(brain["x"] + brain["width"], brain["y"] + 40, vision["x"], mid(vision)[1], start=brain, end=vision))
E.append(arrow(mid(vision)[0], vision["y"] + vision["height"], mid(flux)[0], flux["y"], start=vision, end=flux))
E.append(arrow(vision["x"] + vision["width"], mid(vision)[1], finder["x"], mid(finder)[1], start=vision, end=finder))
E.append(arrow(mid(finder)[0], finder["y"] + finder["height"], mid(rules)[0], rules["y"], start=finder, end=rules))

E.append(arrow(mid(proj_api)[0], proj_api["y"] + proj_api["height"], mid(pg)[0], pg["y"], start=proj_api, end=pg, stroke="#e03131"))
E.append(arrow(mid(publish)[0], publish["y"] + publish["height"], mid(avito)[0], avito["y"], start=publish, end=avito, stroke="#c92a2a"))
E.append(arrow(mid(emit)[0], emit["y"] + emit["height"], mid(met)[0], met["y"], start=emit, end=met, stroke="#c2255c"))
E.append(arrow(done["x"] + 40, done["y"], mid(ok)[0], ok["y"] + ok["height"], start=done, end=ok, stroke="#1971c2"))
E.append(arrow(create["x"] + create["width"], create["y"] + create["height"], s3["x"], s3["y"], start=create, end=s3, stroke="#e03131"))

# ===================== METRICS DETAIL =====================
L6 = rect(40, 1170, 1520, 160, bg="#fff0f6", stroke="#c2255c")
E.append(L6)
E.append(text(55, 1180, "6. Метрики (per project + global)", size=17, stroke="#c2255c"))

m1 = rect(70, 1215, 230, 90, bg="#fcc2d7", stroke="#c2255c")
m2 = rect(330, 1215, 230, 90, bg="#faa2c1", stroke="#c2255c")
m3 = rect(590, 1215, 230, 90, bg="#fcc2d7", stroke="#c2255c")
m4 = rect(850, 1215, 230, 90, bg="#faa2c1", stroke="#c2255c")
m5 = rect(1110, 1215, 400, 90, bg="#ffdeeb", stroke="#c2255c")
E.extend([m1, m2, m3, m4, m5])
E.append(label(m1, "Воронка\nbrief→approve→publish", size=13))
E.append(label(m2, "Качество\n% правок · итерации", size=13))
E.append(label(m3, "Стоимость\ntokens · Flux · ₽", size=13))
E.append(label(m4, "Avito\nуспех/ошибки фида", size=13))
E.append(label(m5, "events: job.* chat.* publish.*\nrollup → dashboard WebApp", size=13))

# ===================== DATA MODEL NOTE =====================
dm = rect(40, 1360, 1520, 150, bg="#f8f9fa", stroke="#495057", width=1)
E.append(dm)
E.append(text(55, 1375, "Модель данных (кратко)", size=18, stroke="#212529"))
E.append(
    text(
        55,
        1410,
        "User → Workspace → Project(settings, system_prompt, context_pack, avito_creds)\n"
        "Project → ChatThread → Message(role, content, attachments)\n"
        "Project → Job(state machine) → CreativeVersion(text, photos) → PublishAttempt(feed, avito_ids)\n"
        "Project → MetricEvent → daily rollups (funnel, cost, quality)",
        size=14,
        stroke="#495057",
        w=1480,
    )
)

# LLM + stack
leg = rect(40, 1540, 1520, 140, bg="#f3f0ff", stroke="#5f3dc4", width=1)
E.append(leg)
E.append(text(55, 1555, "LLM · стек", size=18, stroke="#5f3dc4"))
E.append(
    text(
        55,
        1590,
        "Claude Sonnet = мозг (sys prompt проекта + context + история чата). Vision / Flux / Photo Finder — по шагам пайплайна.\n"
        "Python · aiogram 3 · FastAPI · React/Vite Mini App · Postgres · Redis · S3 · Claude · fal.ai · Avito Autoload API",
        size=14,
        stroke="#5f3dc4",
        w=1480,
    )
)

out = Path(__file__).resolve().parents[1] / "docs" / "architecture.excalidraw"
out.parent.mkdir(parents=True, exist_ok=True)
doc = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": E,
    "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
    "files": {},
}
out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Wrote {out} · {len(E)} elements")
