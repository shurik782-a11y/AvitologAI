import { useEffect, useMemo, useRef, useState } from "react";
import { api, fileToDataUrl } from "./api.js";

const NAV = [
  { id: "settings", label: "Настройки" },
  { id: "publications", label: "Публикации" },
  { id: "docs", label: "Документация" },
];

export default function App() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(null);
  const [section, setSection] = useState("chat");
  const [settingsSub, setSettingsSub] = useState(null); // orch | image | vision | null
  const [defaults, setDefaults] = useState(null);
  const [messages, setMessages] = useState([]);
  const [creative, setCreative] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [photos, setPhotos] = useState([]);
  const [genImages, setGenImages] = useState(true);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const bottomRef = useRef(null);
  const pickerRef = useRef(null);

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
    api
      .getSettings()
      .then(setDefaults)
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, creative, section]);

  useEffect(() => {
    function onDoc(e) {
      if (pickerRef.current && !pickerRef.current.contains(e.target)) setPickerOpen(false);
    }
    document.addEventListener("pointerdown", onDoc);
    return () => document.removeEventListener("pointerdown", onDoc);
  }, []);

  async function selectProject(id) {
    setProjectId(id);
    setPickerOpen(false);
    setNavOpen(false);
    setSection("chat");
    setSettingsSub(null);
    setError("");
    setBusy(true);
    try {
      const msgs = await api.getMessages(id);
      setMessages(msgs);
      setCreative(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function createProject() {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      const p = await api.createProject({ name: newName.trim() });
      setNewName("");
      setNewOpen(false);
      await refreshProjects();
      await selectProject(p.id);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveProjectFields(patch) {
    if (!projectId) return;
    setBusy(true);
    try {
      const updated = await api.updateProject(projectId, patch);
      setProjects((list) => list.map((p) => (p.id === updated.id ? updated : p)));
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
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
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

  function go(sectionId) {
    if ((sectionId === "settings" || sectionId === "chat") && !projectId) {
      setError("Сначала выберите проект справа сверху");
      setPickerOpen(true);
      return;
    }
    setSection(sectionId);
    setSettingsSub(null);
    setNavOpen(false);
    setError("");
  }

  const pickerLabel = project ? project.name : "Выберите проект";

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar-left">
          <button className="icon-btn mobile-only" onClick={() => setNavOpen((v) => !v)} aria-label="Меню">
            ☰
          </button>
          <div className="brand">AvitologAI</div>
        </div>

        <div className="picker" ref={pickerRef}>
          <button
            className={`picker-btn ${project ? "has-project" : ""}`}
            onClick={() => setPickerOpen((v) => !v)}
          >
            <span className="picker-label">{pickerLabel}</span>
            <span className="picker-caret">▾</span>
          </button>
          {pickerOpen && (
            <div className="picker-menu">
              <button
                className="picker-item new"
                onClick={() => {
                  setPickerOpen(false);
                  setNewOpen(true);
                }}
              >
                + Новый проект
              </button>
              <div className="picker-sep" />
              {projects.map((p) => (
                <button
                  key={p.id}
                  className={`picker-item ${p.id === projectId ? "active" : ""}`}
                  onClick={() => selectProject(p.id)}
                >
                  {p.name}
                </button>
              ))}
              {!projects.length && <div className="picker-empty">Пока нет проектов</div>}
            </div>
          )}
        </div>
      </header>

      <div className="body">
        <aside className={`sidebar ${navOpen ? "open" : ""}`}>
          <nav className="side-nav">
            <button className={section === "chat" ? "side-link active" : "side-link"} onClick={() => go("chat")}>
              Чат
            </button>
            {NAV.map((item) => (
              <button
                key={item.id}
                className={section === item.id || (item.id === "settings" && settingsSub) ? "side-link active" : "side-link"}
                onClick={() => go(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <div className="side-foot">
            {busy ? <span className="pulse">Синхронизация…</span> : <span>Проект изолирован</span>}
          </div>
        </aside>
        {navOpen && <div className="scrim mobile-only" onClick={() => setNavOpen(false)} />}

        <main className="content">
          {error && <div className="toast error">{error}</div>}

          {section === "chat" && (
            <ChatPanel
              project={project}
              messages={messages}
              creative={creative}
              draft={draft}
              setDraft={setDraft}
              photos={photos}
              setPhotos={setPhotos}
              genImages={genImages}
              setGenImages={setGenImages}
              onSend={sendChat}
              onApprove={approve}
              busy={busy}
              bottomRef={bottomRef}
              onNeedProject={() => setPickerOpen(true)}
            />
          )}

          {section === "settings" && !settingsSub && (
            <SettingsHub
              project={project}
              defaults={defaults}
              onOpen={setSettingsSub}
              onNeedProject={() => setPickerOpen(true)}
            />
          )}

          {section === "settings" && settingsSub && project && (
            <ModelSettings
              kind={settingsSub}
              project={project}
              defaults={defaults}
              onBack={() => setSettingsSub(null)}
              onSave={saveProjectFields}
              busy={busy}
            />
          )}

          {section === "publications" && (
            <Placeholder
              title="Публикации"
              text="Здесь появится очередь утверждённых креативов и выгрузка в Avito Автозагрузку."
            />
          )}

          {section === "docs" && (
            <DocsPanel />
          )}
        </main>
      </div>

      {newOpen && (
        <div className="modal-scrim" onClick={() => setNewOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Новый проект</h2>
            <p className="muted">Свои модели, промпты и чат — без смешивания с другими.</p>
            <input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Название проекта"
              onKeyDown={(e) => e.key === "Enter" && createProject()}
            />
            <div className="modal-actions">
              <button onClick={() => setNewOpen(false)}>Отмена</button>
              <button className="primary" disabled={!newName.trim() || busy} onClick={createProject}>
                Создать
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ChatPanel({
  project,
  messages,
  creative,
  draft,
  setDraft,
  photos,
  setPhotos,
  genImages,
  setGenImages,
  onSend,
  onApprove,
  busy,
  bottomRef,
  onNeedProject,
}) {
  if (!project) {
    return (
      <EmptyState
        title="Нет активного проекта"
        text="Выберите проект справа сверху или создайте новый — чат и настройки привязаны только к нему."
        action="Выбрать проект"
        onAction={onNeedProject}
      />
    );
  }

  return (
    <section className="chat-panel">
      <div className="panel-head">
        <div>
          <div className="eyebrow">Чат проекта</div>
          <h1>{project.name}</h1>
        </div>
      </div>
      <div className="messages">
        {!messages.length && (
          <div className="empty-inline">
            Опишите товар или прикрепите фото — авитолог соберёт текст и креатив.
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`bubble ${m.role}`}>
            <div className="role">{m.role === "user" ? "Вы" : "Авитолог"}</div>
            <div className="body">{m.content}</div>
          </div>
        ))}
        {creative && (
          <div className="creative">
            <div className="creative-title">{creative.title || "Креатив"}</div>
            <pre>{creative.description}</pre>
            {!!creative.images?.length && (
              <div className="thumbs">
                {creative.images.map((img, i) => (
                  <img key={i} src={img.url} alt="" />
                ))}
              </div>
            )}
            <div className="row-actions">
              <button className="primary" disabled={creative.status === "approved" || busy} onClick={onApprove}>
                {creative.status === "approved" ? "Утверждено" : "Утвердить"}
              </button>
              <span className="muted">Правки — свободным текстом ниже</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="composer">
        {!!photos.length && (
          <div className="thumbs">
            {photos.map((p, i) => (
              <button key={i} className="thumb" onClick={() => setPhotos(photos.filter((_, j) => j !== i))}>
                <img src={p} alt="" />
              </button>
            ))}
          </div>
        )}
        <div className="composer-row">
          <label className="attach">
            +
            <input
              hidden
              type="file"
              accept="image/*"
              multiple
              onChange={async (e) => {
                const urls = await Promise.all(Array.from(e.target.files || []).slice(0, 4).map(fileToDataUrl));
                setPhotos((prev) => [...prev, ...urls].slice(0, 4));
              }}
            />
          </label>
          <textarea
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Задание или правки…"
          />
          <button className="primary send" disabled={busy} onClick={onSend}>
            Отправить
          </button>
        </div>
        <label className="check">
          <input type="checkbox" checked={genImages} onChange={(e) => setGenImages(e.target.checked)} />
          Генерировать изображение
        </label>
      </div>
    </section>
  );
}

function SettingsHub({ project, defaults, onOpen, onNeedProject }) {
  if (!project) {
    return (
      <EmptyState
        title="Настройки привязаны к проекту"
        text="Каждый проект видит только свои модели и промпты. Выберите проект, чтобы открыть настройки."
        action="Выбрать проект"
        onAction={onNeedProject}
      />
    );
  }

  const rows = [
    {
      id: "orch",
      title: "Оркестратор",
      hint: project.orchestrator_model || defaults?.default_orchestrator_model || "из Variables",
    },
    {
      id: "image",
      title: "Генерация изображений",
      hint: project.image_model || defaults?.default_image_model || "из Variables",
    },
    {
      id: "vision",
      title: "Vision",
      hint: project.vision_model || defaults?.default_vision_model || "из Variables",
    },
  ];

  return (
    <section className="stack-page">
      <div className="panel-head">
        <div>
          <div className="eyebrow">Только для «{project.name}»</div>
          <h1>Настройки</h1>
        </div>
      </div>
      <p className="lede">
        Модели по умолчанию берутся из Variables на Railway. Пустое поле = дефолт. Другие проекты эти значения не
        видят.
      </p>
      <div className="rows">
        {rows.map((r) => (
          <button key={r.id} className="row-btn" onClick={() => onOpen(r.id)}>
            <div>
              <strong>{r.title}</strong>
              <div className="mono">{r.hint}</div>
            </div>
            <span className="chev">›</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function ModelSettings({ kind, project, defaults, onBack, onSave, busy }) {
  const meta = {
    orch: {
      title: "Оркестратор",
      modelKey: "orchestrator_model",
      fallback: defaults?.default_orchestrator_model,
      fields: [
        { key: "orchestrator_prompt", label: "Системный промпт", rows: 6 },
        { key: "theme", label: "Тематика", rows: 2 },
        { key: "ideas", label: "Идеи", rows: 3 },
        { key: "constraints", label: "Ограничения", rows: 3 },
      ],
    },
    image: {
      title: "Генерация изображений",
      modelKey: "image_model",
      fallback: defaults?.default_image_model,
      fields: [{ key: "image_style_prompt", label: "Стиль / промпт для фото", rows: 5 }],
    },
    vision: {
      title: "Vision",
      modelKey: "vision_model",
      fallback: defaults?.default_vision_model,
      fields: [{ key: "vision_prompt", label: "Инструкция для разбора фото", rows: 5 }],
    },
  }[kind];

  const [form, setForm] = useState(() => {
    const base = { [meta.modelKey]: project[meta.modelKey] || "" };
    meta.fields.forEach((f) => {
      base[f.key] = project[f.key] || "";
    });
    return base;
  });

  useEffect(() => {
    const base = { [meta.modelKey]: project[meta.modelKey] || "" };
    meta.fields.forEach((f) => {
      base[f.key] = project[f.key] || "";
    });
    setForm(base);
  }, [project, kind]);

  return (
    <section className="stack-page">
      <button className="back" onClick={onBack}>
        ← Настройки
      </button>
      <div className="panel-head">
        <div>
          <div className="eyebrow">{project.name}</div>
          <h1>{meta.title}</h1>
        </div>
      </div>
      <div className="form-card">
        <label>
          Модель OpenRouter
          <input
            className="mono-input"
            value={form[meta.modelKey]}
            onChange={(e) => setForm({ ...form, [meta.modelKey]: e.target.value })}
            placeholder={meta.fallback || "slug модели"}
          />
          <span className="field-hint">По умолчанию: {meta.fallback || "—"}</span>
        </label>
        {meta.fields.map((f) => (
          <label key={f.key}>
            {f.label}
            <textarea
              rows={f.rows}
              value={form[f.key]}
              onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
            />
          </label>
        ))}
        <button className="primary" disabled={busy} onClick={() => onSave(form)}>
          Сохранить для проекта
        </button>
      </div>
    </section>
  );
}

function DocsPanel() {
  return (
    <section className="stack-page">
      <div className="panel-head">
        <div>
          <div className="eyebrow">Справка</div>
          <h1>Документация</h1>
        </div>
      </div>
      <div className="doc-card">
        <h3>Как работать</h3>
        <ol>
          <li>Создайте проект в переключателе справа сверху.</li>
          <li>В «Настройки» задайте модели и промпты только для этого проекта.</li>
          <li>В чате отправьте задание или фото → утвердите креатив.</li>
        </ol>
        <h3>Изоляция</h3>
        <p>Чаты, память, модели и промпты хранятся по `project_id` и не пересекаются.</p>
        <h3>Variables</h3>
        <p className="mono">
          ORCHESTRATOR_MODEL · VISION_MODEL · IMAGE_MODEL · OPENROUTER_API_KEY · PUBLIC_BASE_URL · TELEGRAM_BOT_TOKEN
        </p>
      </div>
    </section>
  );
}

function Placeholder({ title, text }) {
  return (
    <section className="stack-page">
      <div className="panel-head">
        <div>
          <div className="eyebrow">Скоро</div>
          <h1>{title}</h1>
        </div>
      </div>
      <p className="lede">{text}</p>
    </section>
  );
}

function EmptyState({ title, text, action, onAction }) {
  return (
    <div className="empty-state">
      <h2>{title}</h2>
      <p>{text}</p>
      {action && (
        <button className="primary" onClick={onAction}>
          {action}
        </button>
      )}
    </div>
  );
}
