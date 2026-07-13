import { useEffect, useMemo, useRef, useState } from "react";
import { api, fileToDataUrl } from "./api.js";

export default function App() {
  const [view, setView] = useState("projects");
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [creative, setCreative] = useState(null);
  const [memories, setMemories] = useState([]);
  const [settings, setSettings] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [photos, setPhotos] = useState([]);
  const [genImages, setGenImages] = useState(true);
  const bottomRef = useRef(null);

  const project = useMemo(
    () => projects.find((p) => p.id === projectId) || null,
    [projects, projectId]
  );

  async function refreshProjects() {
    const list = await api.listProjects();
    setProjects(list);
    return list;
  }

  useEffect(() => {
    refreshProjects().catch((e) => setError(e.message));
    api.getSettings().then(setSettings).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, creative, view]);

  async function openProject(id) {
    setProjectId(id);
    setView("chat");
    setError("");
    setBusy(true);
    try {
      const [msgs, mems] = await Promise.all([api.getMessages(id), api.getMemories(id)]);
      setMessages(msgs);
      setMemories(mems);
      setCreative(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function createProject(form) {
    setBusy(true);
    setError("");
    try {
      const p = await api.createProject(form);
      await refreshProjects();
      await openProject(p.id);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveProject(form) {
    if (!projectId) return;
    setBusy(true);
    try {
      await api.updateProject(projectId, form);
      await refreshProjects();
      setError("");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function sendChat() {
    if (!projectId || (!draft.trim() && photos.length === 0)) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.chat(projectId, {
        content: draft.trim(),
        images: photos,
        generate_images: genImages,
        revise_of_creative_id: creative?.id || null,
      });
      setMessages((m) => [...m, ...res.messages]);
      setCreative(res.creative);
      setDraft("");
      setPhotos([]);
      setMemories(await api.getMemories(projectId));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function onPickFiles(files) {
    const list = Array.from(files || []).slice(0, 4);
    const urls = await Promise.all(list.map(fileToDataUrl));
    setPhotos((prev) => [...prev, ...urls].slice(0, 4));
  }

  async function approve() {
    if (!projectId || !creative) return;
    setBusy(true);
    try {
      const c = await api.approve(projectId, creative.id);
      setCreative(c);
      setMessages(await api.getMessages(projectId));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveSettings(form) {
    setBusy(true);
    try {
      const s = await api.saveSettings(form);
      setSettings(s);
      setError("");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function loadMetrics() {
    setBusy(true);
    try {
      setMetrics(await api.getMetrics(projectId));
      setView("metrics");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header className="top">
        <div>
          <div className="brand">AvitologAI</div>
          <div className="sub">{project ? project.name : "выберите проект"}</div>
        </div>
        {busy && <span className="pill">работаю…</span>}
      </header>

      {error && <div className="banner error">{error}</div>}

      <main className="main">
        {view === "projects" && (
          <ProjectsView projects={projects} onOpen={openProject} onCreate={createProject} />
        )}
        {view === "chat" && project && (
          <ChatView
            messages={messages}
            creative={creative}
            draft={draft}
            setDraft={setDraft}
            photos={photos}
            setPhotos={setPhotos}
            genImages={genImages}
            setGenImages={setGenImages}
            onPickFiles={onPickFiles}
            onSend={sendChat}
            onApprove={approve}
            bottomRef={bottomRef}
            busy={busy}
          />
        )}
        {view === "project" && project && (
          <ProjectSettingsView
            project={project}
            memories={memories}
            onSave={saveProject}
            onAddMemory={async (content) => {
              await api.addMemory(projectId, { kind: "preference", content });
              setMemories(await api.getMemories(projectId));
            }}
          />
        )}
        {view === "settings" && settings && (
          <AppSettingsView settings={settings} onSave={saveSettings} />
        )}
        {view === "metrics" && metrics && <MetricsView metrics={metrics} />}
      </main>

      <nav className="nav">
        <button className={view === "projects" ? "active" : ""} onClick={() => setView("projects")}>
          Проекты
        </button>
        <button
          className={view === "chat" ? "active" : ""}
          disabled={!projectId}
          onClick={() => projectId && openProject(projectId)}
        >
          Чат
        </button>
        <button
          className={view === "project" ? "active" : ""}
          disabled={!projectId}
          onClick={() => setView("project")}
        >
          Настройки
        </button>
        <button className={view === "settings" ? "active" : ""} onClick={() => setView("settings")}>
          API
        </button>
        <button className={view === "metrics" ? "active" : ""} onClick={loadMetrics}>
          Метрики
        </button>
      </nav>
    </div>
  );
}

function ProjectsView({ projects, onOpen, onCreate }) {
  const [name, setName] = useState("");
  const [theme, setTheme] = useState("");
  return (
    <section className="stack">
      <h1>Проекты</h1>
      <p className="muted">У каждого проекта свой чат, настройки, память и метрики.</p>
      <div className="card form">
        <label>
          Название
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Например: Диваны МСК" />
        </label>
        <label>
          Тема / ниша
          <input value={theme} onChange={(e) => setTheme(e.target.value)} placeholder="мебель, автозапчасти…" />
        </label>
        <button
          className="primary"
          disabled={!name.trim()}
          onClick={() => {
            onCreate({ name: name.trim(), theme, ideas: "", constraints: "" });
            setName("");
            setTheme("");
          }}
        >
          + Создать проект
        </button>
      </div>
      <div className="list">
        {projects.map((p) => (
          <button key={p.id} className="card row" onClick={() => onOpen(p.id)}>
            <div>
              <strong>{p.name}</strong>
              <div className="muted">{p.theme || "без темы"}</div>
            </div>
            <span className="chev">›</span>
          </button>
        ))}
        {!projects.length && <div className="muted">Пока пусто — создайте первый проект.</div>}
      </div>
    </section>
  );
}

function ChatView({
  messages,
  creative,
  draft,
  setDraft,
  photos,
  setPhotos,
  genImages,
  setGenImages,
  onPickFiles,
  onSend,
  onApprove,
  bottomRef,
  busy,
}) {
  return (
    <section className="chat">
      <div className="messages">
        {messages.map((m) => (
          <div key={m.id} className={`bubble ${m.role}`}>
            <div className="role">{m.role === "user" ? "Вы" : "Авитолог"}</div>
            <div className="body">{m.content}</div>
            {!!m.attachments?.length && (
              <div className="thumbs">
                {m.attachments.map((a, i) =>
                  a.url && !String(a.url).includes("…") ? (
                    <img key={i} src={a.url} alt="" />
                  ) : null
                )}
              </div>
            )}
          </div>
        ))}
        {creative && (
          <div className="card creative">
            <h3>{creative.title || "Креатив"}</h3>
            <pre>{creative.description}</pre>
            {!!creative.images?.length && (
              <div className="thumbs">
                {creative.images.map((img, i) => (
                  <img key={i} src={img.url} alt="" />
                ))}
              </div>
            )}
            <div className="actions">
              <button className="primary" disabled={creative.status === "approved" || busy} onClick={onApprove}>
                {creative.status === "approved" ? "Утверждено" : "Утвердить"}
              </button>
              <span className="muted">Правки — напишите свободным текстом ниже</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="composer">
        {!!photos.length && (
          <div className="thumbs">
            {photos.map((p, i) => (
              <button key={i} className="thumb-wrap" onClick={() => setPhotos(photos.filter((_, j) => j !== i))}>
                <img src={p} alt="" />
              </button>
            ))}
          </div>
        )}
        <div className="composer-row">
          <label className="file">
            📷
            <input
              type="file"
              accept="image/*"
              multiple
              hidden
              onChange={(e) => onPickFiles(e.target.files)}
            />
          </label>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Задание или правки…"
            rows={2}
          />
          <button className="primary" disabled={busy} onClick={onSend}>
            →
          </button>
        </div>
        <label className="check">
          <input type="checkbox" checked={genImages} onChange={(e) => setGenImages(e.target.checked)} />
          Генерировать фото (OpenRouter image model)
        </label>
      </div>
    </section>
  );
}

function ProjectSettingsView({ project, memories, onSave, onAddMemory }) {
  const [form, setForm] = useState({
    name: project.name,
    theme: project.theme || "",
    ideas: project.ideas || "",
    constraints: project.constraints || "",
  });
  const [mem, setMem] = useState("");
  useEffect(() => {
    setForm({
      name: project.name,
      theme: project.theme || "",
      ideas: project.ideas || "",
      constraints: project.constraints || "",
    });
  }, [project]);

  return (
    <section className="stack">
      <h1>Настройки проекта</h1>
      <div className="card form">
        <label>
          Название
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label>
          Тема
          <textarea value={form.theme} onChange={(e) => setForm({ ...form, theme: e.target.value })} rows={2} />
        </label>
        <label>
          Идеи
          <textarea value={form.ideas} onChange={(e) => setForm({ ...form, ideas: e.target.value })} rows={3} />
        </label>
        <label>
          Ограничения
          <textarea
            value={form.constraints}
            onChange={(e) => setForm({ ...form, constraints: e.target.value })}
            rows={3}
          />
        </label>
        <button className="primary" onClick={() => onSave(form)}>
          Сохранить
        </button>
      </div>
      <h2>Память проекта</h2>
      <p className="muted">Правки и частые действия сохраняются автоматически; можно добавить вручную.</p>
      <div className="card form">
        <input value={mem} onChange={(e) => setMem(e.target.value)} placeholder="Всегда короткие заголовки…" />
        <button
          disabled={!mem.trim()}
          onClick={async () => {
            await onAddMemory(mem.trim());
            setMem("");
          }}
        >
          Добавить в память
        </button>
      </div>
      <div className="list">
        {memories.map((m) => (
          <div key={m.id} className="card">
            <div className="pill">{m.kind} · ×{m.hits}</div>
            <div>{m.content}</div>
          </div>
        ))}
        {!memories.length && <div className="muted">Память пока пустая.</div>}
      </div>
    </section>
  );
}

function AppSettingsView({ settings, onSave }) {
  const [form, setForm] = useState({
    openrouter_api_key: "",
    orchestrator_model: settings.orchestrator_model,
    vision_model: settings.vision_model,
    image_model: settings.image_model,
    orchestrator_instruction: settings.orchestrator_instruction,
  });

  useEffect(() => {
    setForm((f) => ({
      ...f,
      orchestrator_model: settings.orchestrator_model,
      vision_model: settings.vision_model,
      image_model: settings.image_model,
      orchestrator_instruction: settings.orchestrator_instruction,
    }));
  }, [settings]);

  return (
    <section className="stack">
      <h1>OpenRouter</h1>
      <p className="muted">
        Ключ: {settings.openrouter_api_key_set ? settings.openrouter_api_key_masked : "не задан"}. Оркестратор —
        быстрая/бесплатная модель; отдельно — модель картинок.
      </p>
      <div className="card form">
        <label>
          API key
          <input
            type="password"
            value={form.openrouter_api_key}
            onChange={(e) => setForm({ ...form, openrouter_api_key: e.target.value })}
            placeholder="sk-or-…"
          />
        </label>
        <label>
          Оркестратор (free/fast)
          <input
            value={form.orchestrator_model}
            onChange={(e) => setForm({ ...form, orchestrator_model: e.target.value })}
            placeholder="openrouter/free"
          />
        </label>
        <label>
          Vision (фото во входе)
          <input
            value={form.vision_model}
            onChange={(e) => setForm({ ...form, vision_model: e.target.value })}
            placeholder="openrouter/free"
          />
        </label>
        <label>
          Image model
          <input
            value={form.image_model}
            onChange={(e) => setForm({ ...form, image_model: e.target.value })}
            placeholder="black-forest-labs/flux.2-flex"
          />
        </label>
        <label>
          Инструкция оркестратора
          <textarea
            rows={8}
            value={form.orchestrator_instruction}
            onChange={(e) => setForm({ ...form, orchestrator_instruction: e.target.value })}
          />
        </label>
        <button className="primary" onClick={() => onSave(form)}>
          Сохранить
        </button>
        <div className="hints">
          <button type="button" onClick={() => setForm({ ...form, orchestrator_model: "openrouter/free" })}>
            free router
          </button>
          <button
            type="button"
            onClick={() => setForm({ ...form, orchestrator_model: "google/gemini-2.5-flash" })}
          >
            fast gemini
          </button>
        </div>
      </div>
    </section>
  );
}

function MetricsView({ metrics }) {
  const entries = Object.entries(metrics.totals || {}).sort((a, b) => b[1] - a[1]);
  return (
    <section className="stack">
      <h1>Метрики</h1>
      <div className="grid">
        {entries.map(([k, v]) => (
          <div key={k} className="card metric">
            <div className="muted">{k}</div>
            <strong>{v}</strong>
          </div>
        ))}
        {!entries.length && <div className="muted">Пока нет событий.</div>}
      </div>
    </section>
  );
}
