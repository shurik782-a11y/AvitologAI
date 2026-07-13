import { useEffect, useMemo, useRef, useState } from "react";
import { api, fileToDataUrl } from "./api.js";

const NAV = [
  { id: "settings", label: "Настройки" },
  { id: "publications", label: "Публикации" },
  { id: "metrics", label: "Метрики" },
  { id: "instructions", label: "Инструкции" },
];

function buildFeedUrl(project) {
  if (!project?.id) return "";
  const token = String(project.avito_feed_token || "").trim();
  const raw = String(project.feed_url || "").trim();
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const local = token
    ? `${origin}/api/projects/${project.id}/avito-feed.xml?token=${encodeURIComponent(token)}`
    : "";
  if (raw.startsWith("http://") || raw.startsWith("https://")) return raw;
  if (local) return local;
  if (raw.startsWith("/") && origin) return `${origin}${raw}`;
  return raw || "";
}

function isAvitoConfigured(project) {
  if (!project) return false;
  return Boolean(
    String(project.avito_category || "").trim() &&
      String(project.avito_address || "").trim() &&
      String(project.avito_contact_phone || "").trim() &&
      (project.avito_feed_token || project.feed_url || project.id)
  );
}

async function copyText(text) {
  if (!text) throw new Error("URL ещё не готов — нажмите «Сохранить Avito»");
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const el = document.createElement("textarea");
    el.value = text;
    el.setAttribute("readonly", "");
    el.style.position = "fixed";
    el.style.left = "-9999px";
    document.body.appendChild(el);
    el.select();
    document.execCommand("copy");
    document.body.removeChild(el);
  }
}

function PaperclipIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M21 12.5V8.2a5.2 5.2 0 0 0-10.4 0v9.1a3.4 3.4 0 1 0 6.8 0V9.1a1.6 1.6 0 1 0-3.2 0v7.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function App() {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(null);
  const [section, setSection] = useState("chat");
  const [settingsSub, setSettingsSub] = useState(null);
  const [defaults, setDefaults] = useState(null);
  const [billing, setBilling] = useState(null);
  const [messages, setMessages] = useState([]);
  const [creative, setCreative] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [photos, setPhotos] = useState([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [newOpen, setNewOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [pubs, setPubs] = useState([]);
  const [runs, setRuns] = useState([]);
  const [metricList, setMetricList] = useState([]);
  const [metricId, setMetricId] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
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

  async function refreshBilling() {
    try {
      setBilling(await api.billing());
    } catch {
      setBilling({ available: false, label: "баланс н/д" });
    }
  }

  useEffect(() => {
    refreshProjects().catch((e) => setError(e.message));
    api.getSettings().then(setDefaults).catch((e) => setError(e.message));
    refreshBilling();
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
    setMetricId(null);
    setSnapshot(null);
    setError("");
    setBusy(true);
    try {
      setMessages(await api.getMessages(id));
      setCreative(null);
      await refreshProjects();
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
    if (!projectId) return null;
    setBusy(true);
    try {
      const updated = await api.updateProject(projectId, patch);
      setProjects((list) => list.map((p) => (p.id === updated.id ? updated : p)));
      setError("");
      return updated;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function sendChat() {
    if (!projectId || (!draft.trim() && photos.length === 0)) return;
    setBusy(true);
    setError("");
    const poll = setInterval(async () => {
      try {
        setMessages(await api.getMessages(projectId));
      } catch {
        /* ignore poll errors while waiting */
      }
    }, 700);
    try {
      const res = await api.chat(projectId, {
        content: draft.trim(),
        images: photos,
        revise_of_creative_id: creative?.id || null,
      });
      setMessages(await api.getMessages(projectId));
      setCreative(res.creative);
      setDraft("");
      setPhotos([]);
      if (res.onboarding_done) await refreshProjects();
    } catch (e) {
      setError(e.message);
      try {
        setMessages(await api.getMessages(projectId));
      } catch {
        /* keep previous */
      }
    } finally {
      clearInterval(poll);
      setBusy(false);
    }
  }

  async function approve() {
    if (!projectId || !creative) return;
    setBusy(true);
    const poll = setInterval(async () => {
      try {
        setMessages(await api.getMessages(projectId));
      } catch {
        /* ignore */
      }
    }, 700);
    try {
      const res = await api.approve(projectId, creative.id);
      setCreative(res.creative);
      setMessages(await api.getMessages(projectId));
    } catch (e) {
      setError(e.message);
    } finally {
      clearInterval(poll);
      setBusy(false);
    }
  }

  async function loadPublications() {
    if (!projectId) return;
    setBusy(true);
    try {
      setPubs(await api.publications(projectId));
      setRuns(await api.publishRuns(projectId));
      setSection("publications");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function loadMetrics() {
    if (!projectId) return;
    setBusy(true);
    try {
      setMetricList(await api.metricPublications(projectId));
      setSection("metrics");
      setMetricId(null);
      setSnapshot(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function openMetric(cid) {
    setMetricId(cid);
    if (!cid) {
      setSnapshot(null);
      return;
    }
    setBusy(true);
    try {
      setSnapshot(await api.metricSnapshot(projectId, cid));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function refreshMetric() {
    if (!projectId || !metricId) return;
    setBusy(true);
    try {
      setSnapshot(await api.metricRefresh(projectId, metricId));
      setMetricList(await api.metricPublications(projectId));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function go(sectionId) {
    if (["settings", "chat", "publications", "metrics"].includes(sectionId) && !projectId) {
      setError("Сначала выберите проект справа сверху");
      setPickerOpen(true);
      return;
    }
    setSettingsSub(null);
    setNavOpen(false);
    setError("");
    if (sectionId === "publications") return loadPublications();
    if (sectionId === "metrics") return loadMetrics();
    setSection(sectionId);
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
          <div className="balance" title={billing?.error || ""}>
            {billing?.label || "баланс…"}
          </div>
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
                className={
                  section === item.id || (item.id === "settings" && settingsSub)
                    ? "side-link active"
                    : "side-link"
                }
                onClick={() => go(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <div className="side-foot">{busy ? <span className="pulse">Синхронизация…</span> : <span>Проект изолирован</span>}</div>
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
              onSaveAvito={saveProjectFields}
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

          {section === "publications" && project && (
            <PublicationsPanel
              project={project}
              pubs={pubs}
              runs={runs}
              busy={busy}
              onPublish={async () => {
                setBusy(true);
                try {
                  await api.triggerPublish(projectId);
                  setPubs(await api.publications(projectId));
                  setRuns(await api.publishRuns(projectId));
                } catch (e) {
                  setError(e.message);
                } finally {
                  setBusy(false);
                }
              }}
            />
          )}

          {section === "metrics" && project && (
            <MetricsPanel
              projectId={projectId}
              list={metricList}
              metricId={metricId}
              snapshot={snapshot}
              onOpen={openMetric}
              onRefresh={refreshMetric}
              busy={busy}
              onError={setError}
              onListReload={async () => setMetricList(await api.metricPublications(projectId))}
            />
          )}

          {section === "instructions" && <InstructionsPanel project={project} />}
        </main>
      </div>

      {newOpen && (
        <div className="modal-scrim" onClick={() => setNewOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Новый проект</h2>
            <p className="muted">После создания авитолог попросит настройку в чате.</p>
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
        text="Выберите проект справа сверху или создайте новый."
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
        {!messages.length && <div className="empty-inline">Опишите товар или прикрепите фото.</div>}
        {messages.map((m) => {
          const isStatus = !!m.meta?.status;
          return (
            <div key={m.id} className={`bubble ${m.role}${isStatus ? " status" : ""}`}>
              <div className="role">{m.role === "user" ? "Вы" : isStatus ? "Статус" : "Авитолог"}</div>
              <div className="body">{m.content}</div>
            </div>
          );
        })}
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
          <label className="attach" title="Прикрепить фото">
            <PaperclipIcon />
            <input
              hidden
              type="file"
              accept="image/*"
              multiple
              onChange={async (e) => {
                const urls = await Promise.all(
                  Array.from(e.target.files || [])
                    .slice(0, 4)
                    .map(fileToDataUrl)
                );
                setPhotos((prev) => [...prev, ...urls].slice(0, 4));
              }}
            />
          </label>
          <textarea
            rows={1}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Задание или правки…"
          />
          <button className="primary send" disabled={busy} onClick={onSend}>
            Отправить
          </button>
        </div>
      </div>
    </section>
  );
}

function SettingsHub({ project, defaults, onOpen, onNeedProject, onSaveAvito }) {
  const [avito, setAvito] = useState({
    avito_category: "",
    avito_address: "",
    avito_contact_phone: "",
    avito_client_id: "",
    avito_client_secret: "",
    avito_user_id: "",
  });
  const [avitoOpen, setAvitoOpen] = useState(true);
  const [copyHint, setCopyHint] = useState("");

  useEffect(() => {
    if (!project) return;
    setAvito({
      avito_category: project.avito_category || "",
      avito_address: project.avito_address || "",
      avito_contact_phone: project.avito_contact_phone || "",
      avito_client_id: project.avito_client_id || "",
      avito_client_secret: "",
      avito_user_id: project.avito_user_id || "",
    });
    setAvitoOpen(!isAvitoConfigured(project));
  }, [project]);

  if (!project) {
    return (
      <EmptyState
        title="Настройки привязаны к проекту"
        text="Выберите проект, чтобы открыть настройки."
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

  const feedUrl = buildFeedUrl(project);
  const configured = isAvitoConfigured(project);
  const apiReady = Boolean(project.avito_client_id && project.avito_client_secret_set);

  async function handleSaveAvito() {
    const updated = await onSaveAvito(avito);
    const ready = Boolean(
      String(avito.avito_category || "").trim() &&
        String(avito.avito_address || "").trim() &&
        String(avito.avito_contact_phone || "").trim()
    );
    if (ready) setAvitoOpen(false);
    return updated;
  }

  async function handleCopyUrl() {
    try {
      let url = buildFeedUrl(project);
      if (!url) {
        const updated = await onSaveAvito(avito);
        url = buildFeedUrl(updated || project);
      }
      await copyText(url);
      setCopyHint("Скопировано");
      setTimeout(() => setCopyHint(""), 1600);
    } catch (e) {
      setCopyHint(e.message || "Не удалось скопировать");
    }
  }

  return (
    <section className="stack-page">
      <div className="panel-head">
        <div>
          <div className="eyebrow">Только для «{project.name}»</div>
          <h1>Настройки</h1>
        </div>
      </div>
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

      <div className={`form-card avito-block ${configured && !avitoOpen ? "collapsed" : ""}`}>
        <button
          type="button"
          className="avito-toggle"
          onClick={() => setAvitoOpen((v) => !v)}
          aria-expanded={avitoOpen}
        >
          <div>
            <strong>Avito / Фид</strong>
            <div className="muted mono">
              {configured
                ? apiReady
                  ? "настроено · автопубликация API"
                  : "настроено · фид по URL"
                : "заполните поля для связки"}
            </div>
          </div>
          <span className="chev">{avitoOpen ? "▾" : "›"}</span>
        </button>

        {avitoOpen && (
          <div className="avito-fields">
            <label>
              Категория
              <input
                value={avito.avito_category}
                onChange={(e) => setAvito({ ...avito, avito_category: e.target.value })}
                placeholder="как в Автозагрузке Авито, напр. Товары для компьютера"
              />
              <span className="field-hint">Куда: XML-фид → поле Category. Откуда: ваша рубрика на Авито.</span>
            </label>
            <label>
              Адрес
              <input
                value={avito.avito_address}
                onChange={(e) => setAvito({ ...avito, avito_address: e.target.value })}
              />
              <span className="field-hint">Куда: XML → Address. Откуда: город/адрес объявлений.</span>
            </label>
            <label>
              Телефон
              <input
                value={avito.avito_contact_phone}
                onChange={(e) => setAvito({ ...avito, avito_contact_phone: e.target.value })}
              />
              <span className="field-hint">Куда: XML → ContactPhone.</span>
            </label>
            <label>
              Client ID
              <input
                value={avito.avito_client_id}
                onChange={(e) => setAvito({ ...avito, avito_client_id: e.target.value })}
              />
              <span className="field-hint">
                Откуда: Авито → Для профессионалов → API / developers.avito.ru. Нужен для автопубликации.
              </span>
            </label>
            <label>
              Client Secret {project.avito_client_secret_set ? "(задан)" : ""}
              <input
                type="password"
                value={avito.avito_client_secret}
                onChange={(e) => setAvito({ ...avito, avito_client_secret: e.target.value })}
                placeholder="оставьте пустым чтобы не менять"
              />
              <span className="field-hint">Пара к Client ID. Хранится только в этом проекте.</span>
            </label>
            <label>
              User ID
              <input
                value={avito.avito_user_id}
                onChange={(e) => setAvito({ ...avito, avito_user_id: e.target.value })}
              />
              <span className="field-hint">ID пользователя Авито — для метрик объявлений.</span>
            </label>
            <button
              className="primary"
              onClick={async () => {
                await handleSaveAvito();
              }}
            >
              Сохранить Avito
            </button>
          </div>
        )}

        <div className="avito-copy-row">
          <button type="button" className="btn-copy-sm" onClick={handleCopyUrl}>
            Скопировать URL
          </button>
          {copyHint && <span className="muted">{copyHint}</span>}
        </div>
        {feedUrl ? (
          <p className="mono muted" style={{ wordBreak: "break-all", margin: 0, fontSize: "0.78rem" }}>
            {feedUrl}
          </p>
        ) : (
          <p className="muted" style={{ margin: 0, fontSize: "0.85rem" }}>
            URL появится после сохранения (Client ID не нужен).
          </p>
        )}
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

  const [form, setForm] = useState({});
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
            value={form[meta.modelKey] || ""}
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
              value={form[f.key] || ""}
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

function PublicationsPanel({ project, pubs, runs, onPublish, busy }) {
  const feedUrl = buildFeedUrl(project);
  const [copyHint, setCopyHint] = useState("");

  async function handleCopy() {
    try {
      await copyText(feedUrl);
      setCopyHint("Скопировано");
      setTimeout(() => setCopyHint(""), 1600);
    } catch (e) {
      setCopyHint(e.message || "Нет URL");
    }
  }

  return (
    <section className="stack-page">
      <div className="panel-head">
        <div>
          <div className="eyebrow">{project.name}</div>
          <h1>Публикации</h1>
        </div>
      </div>
      <div className="form-card">
        <p className="muted">XML-фид Автозагрузки. После утверждения креатив попадает в фид.</p>
        <div className="avito-copy-row">
          <button type="button" className="btn-copy-sm" disabled={!feedUrl} onClick={handleCopy}>
            Скопировать URL
          </button>
          {copyHint && <span className="muted">{copyHint}</span>}
        </div>
        <button className="primary" disabled={busy} onClick={onPublish}>
          Обновить фид / запустить подгрузку
        </button>
      </div>
      <div className="rows">
        {pubs.map((p) => (
          <div key={p.id} className="card">
            <strong>{p.title}</strong>
            <div className="muted mono">
              {p.avito_ad_id || "—"} · {p.publish_status || p.status}
            </div>
          </div>
        ))}
        {!pubs.length && <div className="muted">Пока нет утверждённых креативов.</div>}
      </div>
      {!!runs.length && (
        <div className="form-card">
          <h3>Последние запуски</h3>
          {runs.map((r) => (
            <div key={r.id} className="muted mono">
              #{r.id} {r.status} {r.error || ""}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function MetricsPanel({
  projectId,
  list,
  metricId,
  snapshot,
  onOpen,
  onRefresh,
  busy,
  onError,
  onListReload,
}) {
  const [itemId, setItemId] = useState("");
  useEffect(() => {
    const row = list.find((x) => x.creative_id === metricId);
    setItemId(row?.avito_item_id || "");
  }, [metricId, list]);

  if (metricId) {
    return (
      <section className="stack-page">
        <button className="back" onClick={() => onOpen(null)}>
          ← К списку
        </button>
        <div className="panel-head">
          <div>
            <div className="eyebrow">Статистика Avito</div>
            <h1>Публикация #{metricId}</h1>
          </div>
        </div>
        <div className="form-card">
          <label>
            Avito item ID
            <input value={itemId} onChange={(e) => setItemId(e.target.value)} placeholder="числовой ID объявления" />
          </label>
          <button
            className="primary"
            disabled={busy || !itemId.trim()}
            onClick={async () => {
              try {
                await api.patchCreative(projectId, metricId, { avito_item_id: itemId.trim() });
                await onListReload();
                await onRefresh();
              } catch (e) {
                onError(e.message);
              }
            }}
          >
            Сохранить ID и обновить
          </button>
        </div>
        <div className="row-actions">
          <button className="primary" disabled={busy} onClick={() => onRefresh()}>
            Обновить
          </button>
          <span className="muted">
            {snapshot?.fetched_at
              ? `Снимок: ${new Date(snapshot.fetched_at).toLocaleString()}`
              : snapshot?.message || "Ещё не обновляли"}
          </span>
        </div>
        <pre className="stat-json">{JSON.stringify(snapshot?.payload || {}, null, 2)}</pre>
      </section>
    );
  }

  return (
    <section className="stack-page">
      <div className="panel-head">
        <div>
          <div className="eyebrow">Avito</div>
          <h1>Метрики</h1>
        </div>
      </div>
      <p className="lede">Выберите публикацию. Данные с Авито — только по «Обновить».</p>
      <div className="rows">
        {list.map((p) => (
          <button key={p.creative_id} className="row-btn" onClick={() => onOpen(p.creative_id)}>
            <div>
              <strong>{p.title || `#${p.creative_id}`}</strong>
              <div className="mono muted">
                item {p.avito_item_id || "не задан"} · {p.has_snapshot ? "есть снимок" : "нет снимка"}
              </div>
            </div>
            <span className="chev">›</span>
          </button>
        ))}
        {!list.length && <div className="muted">Нет утверждённых публикаций.</div>}
      </div>
    </section>
  );
}

function InstructionsPanel({ project }) {
  const feedUrl = buildFeedUrl(project);
  const [copied, setCopied] = useState("");

  async function copyFeed() {
    try {
      await copyText(feedUrl);
      setCopied("Скопировано");
      setTimeout(() => setCopied(""), 1600);
    } catch (e) {
      setCopied(e.message || "Нет URL");
    }
  }

  return (
    <section className="stack-page">
      <div className="panel-head">
        <div>
          <div className="eyebrow">Связка Avito ↔ WebApp</div>
          <h1>Инструкции</h1>
        </div>
      </div>

      <div className="doc-card">
        <h3>Как ИИ публикует объявления</h3>
        <p className="muted">
          После «Утвердить» креатив попадает в XML-фид проекта. Авито забирает фид по URL (кабинет
          Автозагрузки) или WebApp дергает Autoload API (если заданы Client ID/Secret). Без фида или
          без ключей «сама публикация на Авито» не сработает.
        </p>
      </div>

      <div className="doc-card">
        <h3>1. Настройте WebApp (этот проект)</h3>
        <ol>
          <li>
            Откройте <strong>Настройки → Avito / Фид</strong> для выбранного проекта.
          </li>
          <li>
            Заполните поля объявления (они уходят в XML):
            <ul>
              <li>
                <strong>Категория</strong> — ваша рубрика Авито → в фид как <code>Category</code>
              </li>
              <li>
                <strong>Адрес</strong> — город/адрес → <code>Address</code>
              </li>
              <li>
                <strong>Телефон</strong> — контакт → <code>ContactPhone</code>
              </li>
            </ul>
          </li>
          <li>
            Для <strong>автопубликации через API</strong> (кнопка утвердить / «Обновить фид») добавьте:
            <ul>
              <li>
                <strong>Client ID</strong> и <strong>Client Secret</strong> — из кабинета Авито:
                «Для профессионалов» → API или{" "}
                <a href="https://developers.avito.ru/" target="_blank" rel="noreferrer">
                  developers.avito.ru
                </a>{" "}
                → приложение. Вставляются только в Настройки этого проекта.
              </li>
              <li>
                <strong>User ID</strong> — числовой ID аккаунта Авито (нужен для раздела Метрики).
              </li>
            </ul>
          </li>
          <li>
            Нажмите <strong>Сохранить Avito</strong>. После заполнения блок свернётся; URL фида
            копируется кнопкой под ним.
          </li>
        </ol>
        <div className="avito-copy-row">
          <button type="button" className="btn-copy-sm" disabled={!feedUrl} onClick={copyFeed}>
            Скопировать URL фида
          </button>
          {copied && <span className="muted">{copied}</span>}
        </div>
        {feedUrl ? (
          <p className="mono muted" style={{ wordBreak: "break-all", margin: 0 }}>
            {feedUrl}
          </p>
        ) : (
          <p className="muted">Выберите проект и сохраните Avito / Фид — URL появится здесь.</p>
        )}
      </div>

      <div className="doc-card">
        <h3>2. Куда вставить URL на Авито</h3>
        <ol>
          <li>
            Скопируйте URL кнопкой выше (формат:{" "}
            <code>/api/projects/&#123;id&#125;/avito-feed.xml?token=…</code>).
          </li>
          <li>
            Token берётся из проекта автоматически (<code>avito_feed_token</code>), база — публичный
            HTTPS адрес приложения (<code>PUBLIC_BASE_URL</code> / текущий домен).
          </li>
          <li>
            В кабинете Авито откройте <strong>Автозагрузку</strong> → добавьте/укажите фид → вставьте
            этот URL как адрес файла объявлений.
          </li>
          <li>
            Проверьте XML:{" "}
            <a href="https://autoload.avito.ru/format/xmlcheck/" target="_blank" rel="noreferrer">
              валидатор Автозагрузки
            </a>
            .
          </li>
          <li>
            Если Client ID/Secret заданы — при утверждении WebApp сам может дернуть upload API; URL
            в кабинете всё равно полезен как запасной канал.
          </li>
        </ol>
      </div>

      <div className="doc-card">
        <h3>3. Таблица: откуда → куда</h3>
        <div className="instr-table">
          <div>
            <strong>Значение</strong>
            <span className="muted">Откуда берётся</span>
            <span className="muted">Куда вставляется</span>
          </div>
          <div>
            <strong>Категория / Адрес / Телефон</strong>
            <span>Вы вручную в Настройках</span>
            <span>XML-фид (Category, Address, ContactPhone)</span>
          </div>
          <div>
            <strong>Заголовок, описание, фото, цена</strong>
            <span>Чат → креатив ИИ → Утвердить</span>
            <span>XML (Title, Description, Images, Price)</span>
          </div>
          <div>
            <strong>Feed URL + token</strong>
            <span>Генерируется проектом (кнопка «Скопировать URL»)</span>
            <span>Кабинет Автозагрузки Авито → URL фида</span>
          </div>
          <div>
            <strong>Client ID / Secret</strong>
            <span>Авито API / developers.avito.ru</span>
            <span>Настройки проекта → автопубликация upload</span>
          </div>
          <div>
            <strong>User ID</strong>
            <span>Профиль Авито / API</span>
            <span>Настройки → Метрики по объявлениям</span>
          </div>
          <div>
            <strong>avito_item_id</strong>
            <span>После выгрузки — ID объявления на Авито</span>
            <span>Метрики → поле item ID → «Обновить»</span>
          </div>
        </div>
      </div>

      <div className="doc-card">
        <h3>4. Рабочий цикл</h3>
        <ol>
          <li>Чат: задание → черновик → правки при необходимости.</li>
          <li>
            <strong>Утвердить</strong> → креатив в фиде; при ключах API — попытка подгрузки.
          </li>
          <li>
            Раздел <strong>Публикации</strong> — статус и ручной «Обновить фид / запустить подгрузку».
          </li>
          <li>
            <strong>Метрики</strong> — данные Авито только по кнопке «Обновить».
          </li>
        </ol>
      </div>
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
