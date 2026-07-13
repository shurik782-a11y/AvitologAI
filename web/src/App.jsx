import { useEffect, useMemo, useRef, useState } from "react";
import { api, apiUpload, fileToDataUrl } from "./api.js";

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
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M21 12.5V8.2a5.2 5.2 0 0 0-10.4 0v9.1a3.4 3.4 0 1 0 6.8 0V9.1a1.6 1.6 0 1 0-3.2 0v7.5"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2m2 0v12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V7h12ZM10 11v6M14 11v6"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function App() {
  const [access, setAccess] = useState("loading");
  const [accessError, setAccessError] = useState("");
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
  const [deleteTarget, setDeleteTarget] = useState(null);
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

  useEffect(() => {
    let cancelled = false;
    api
      .authMe()
      .then(() => {
        if (!cancelled) setAccess("ok");
      })
      .catch((e) => {
        if (cancelled) return;
        if (e.status === 401 || e.status === 403) {
          setAccess("denied");
          setAccessError(e.message || "Нет доступа");
        } else {
          // сеть / health: всё равно пробуем UI (ADMIN_IDS может быть пуст на API)
          setAccess("ok");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
    if (access !== "ok") return;
    refreshProjects().catch((e) => setError(e.message));
    api.getSettings().then(setDefaults).catch((e) => setError(e.message));
    refreshBilling();
  }, [access]);

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

  async function confirmDeleteProject() {
    if (!deleteTarget) return;
    const doomed = deleteTarget;
    setBusy(true);
    try {
      await api.deleteProject(doomed.id);
      setDeleteTarget(null);
      setPickerOpen(false);
      const list = await refreshProjects();
      if (projectId === doomed.id) {
        setProjectId(null);
        setMessages([]);
        setCreative(null);
        setSection("chat");
        if (list.length) await selectProject(list[0].id);
      }
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

  if (access === "loading") {
    return (
      <div className="shell">
        <div className="empty-state">
          <h2>AvitologAI</h2>
          <p className="muted">Проверка доступа…</p>
        </div>
      </div>
    );
  }

  if (access === "denied") {
    return (
      <div className="shell">
        <EmptyState
          title="Нет доступа"
          text={
            accessError ||
            "Откройте приложение из Telegram-бота. Ваш ID должен быть в ADMIN_IDS на сервере."
          }
        />
      </div>
    );
  }

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
                <div key={p.id} className={`picker-row ${p.id === projectId ? "active" : ""}`}>
                  <button type="button" className="picker-item" onClick={() => selectProject(p.id)}>
                    {p.name}
                  </button>
                  <button
                    type="button"
                    className="picker-delete"
                    title="Удалить проект"
                    aria-label={`Удалить ${p.name}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      setPickerOpen(false);
                      setDeleteTarget(p);
                    }}
                  >
                    <TrashIcon />
                  </button>
                </div>
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

      {deleteTarget && (
        <div className="modal-scrim" onClick={() => !busy && setDeleteTarget(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Удалить проект?</h2>
            <p>
              Вы точно хотите удалить проект <strong>{deleteTarget.name}</strong>?
            </p>
            <p className="muted">Чат, настройки и публикации проекта будут удалены безвозвратно.</p>
            <div className="modal-actions">
              <button disabled={busy} onClick={() => setDeleteTarget(null)}>
                Нет
              </button>
              <button className="danger" disabled={busy} onClick={confirmDeleteProject}>
                Да
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ImageLightbox({ src, onClose }) {
  useEffect(() => {
    if (!src) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [src, onClose]);

  if (!src) return null;
  return (
    <div className="lightbox" role="dialog" aria-modal="true" onClick={onClose}>
      <button type="button" className="lightbox-close" onClick={onClose} aria-label="Закрыть">
        ×
      </button>
      <img src={src} alt="" className="lightbox-img" onClick={(e) => e.stopPropagation()} />
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
  const [lightbox, setLightbox] = useState(null);

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
          const wide = m.role === "assistant" && !isStatus;
          const imgs = Array.isArray(m.attachments)
            ? m.attachments.filter((a) => a?.url && !String(a.url).includes("…"))
            : [];
          return (
            <div
              key={m.id}
              className={`bubble ${m.role}${isStatus ? " status" : ""}${wide ? " wide" : ""}`}
            >
              <div className="role">{m.role === "user" ? "Вы" : isStatus ? "Статус" : "Авитолог"}</div>
              <div className="body">{m.content}</div>
              {!!imgs.length && (
                <div className="thumbs">
                  {imgs.map((img, i) => (
                    <button
                      key={i}
                      type="button"
                      className="thumb thumb-open"
                      onClick={() => setLightbox(img.url)}
                      title="Открыть фото"
                    >
                      <img src={img.url} alt="" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {creative && (
          <div className="creative">
            <div className="creative-title">{creative.title || "Креатив"}</div>
            <pre>{creative.description}</pre>
            {!!creative.images?.length && (
              <div className="thumbs creative-thumbs">
                {creative.images.map((img, i) => (
                  <button
                    key={i}
                    type="button"
                    className="thumb thumb-open"
                    onClick={() => setLightbox(img.url)}
                    title="Открыть фото"
                  >
                    <img src={img.url} alt="" />
                  </button>
                ))}
              </div>
            )}
            <div className="row-actions">
              <button className="primary" disabled={creative.status === "approved" || busy} onClick={onApprove}>
                {creative.status === "approved" ? "Утверждено" : "Утвердить"}
              </button>
              <span className="muted">Правки — свободным текстом · клик по фото — увеличить</span>
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
          <div className="composer-field">
            <label className="attach-inline" title="Прикрепить фото">
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
          </div>
          <button className="primary send" disabled={busy} onClick={onSend}>
            Отправить
          </button>
        </div>
      </div>
      <ImageLightbox src={lightbox} onClose={() => setLightbox(null)} />
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
        {
          key: "orchestrator_prompt",
          label: "Доп. промпт проекта (из знакомства)",
          rows: 6,
        },
        { key: "theme", label: "Тематика", rows: 2 },
        { key: "ideas", label: "Идеи", rows: 3 },
        { key: "constraints", label: "Ограничения", rows: 3 },
        { key: "listing_type", label: "Тип (product/service/used/b2b)", rows: 1 },
        { key: "ad_idea", label: "Идея объявления", rows: 3 },
        { key: "search_query", label: "Поисковый запрос (заголовок)", rows: 1 },
        { key: "conversion_offer", label: "Преимущество в заголовке", rows: 1 },
        { key: "advantages", label: "Преимущества продукта", rows: 3 },
        { key: "buyer_pains", label: "Боли покупателя", rows: 3 },
        { key: "why_here", label: "Почему купить здесь", rows: 2 },
        { key: "company_info", label: "О компании / продавце", rows: 3 },
        { key: "photo_count", label: "Число фото (1–5)", rows: 1 },
        { key: "allow_people", label: "Люди на фото (true/false)", rows: 1 },
        { key: "allow_text_overlays", label: "Текст на фото (true/false)", rows: 1 },
        { key: "competitor_insights", label: "Insights конкурентов", rows: 5 },
        { key: "visual_style_notes", label: "Стиль с референсов", rows: 3 },
      ],
    },
    image: {
      title: "Генерация изображений",
      modelKey: "image_model",
      fallback: defaults?.default_image_model,
      fields: [
        {
          key: "image_style_prompt",
          label: "Стиль фото проекта (из знакомства)",
          rows: 5,
        },
      ],
    },
    vision: {
      title: "Vision",
      modelKey: "vision_model",
      fallback: defaults?.default_vision_model,
      fields: [
        {
          key: "vision_prompt",
          label: "Доп. инструкция Vision (из знакомства)",
          rows: 5,
        },
      ],
    },
  }[kind];

  const [form, setForm] = useState({});
  const [compHint, setCompHint] = useState("");
  useEffect(() => {
    const base = { [meta.modelKey]: project[meta.modelKey] || "" };
    meta.fields.forEach((f) => {
      const v = project[f.key];
      if (typeof v === "boolean") base[f.key] = v ? "true" : "false";
      else base[f.key] = v ?? "";
    });
    setForm(base);
  }, [project, kind]);

  const handleSave = () => {
    const payload = { ...form };
    if (kind === "orch") {
      if (payload.photo_count !== undefined) {
        const n = parseInt(payload.photo_count, 10);
        payload.photo_count = Number.isFinite(n) ? n : 1;
      }
      if (payload.allow_people !== undefined) {
        payload.allow_people = String(payload.allow_people).toLowerCase() === "true";
      }
      if (payload.allow_text_overlays !== undefined) {
        payload.allow_text_overlays =
          String(payload.allow_text_overlays).toLowerCase() === "true";
      }
    }
    onSave(payload);
  };

  const handleCompetitorsFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCompHint("Импорт…");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await apiUpload(`/api/projects/${project.id}/competitors/import`, fd);
      setCompHint(res.message || "Готово");
      if (res.competitor_insights) {
        setForm((f) => ({ ...f, competitor_insights: res.competitor_insights }));
      }
    } catch (err) {
      setCompHint(String(err.message || err));
    }
    e.target.value = "";
  };

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
              value={form[f.key] ?? ""}
              onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
            />
          </label>
        ))}
        {kind === "orch" && (
          <label>
            Импорт таблицы конкурентов (CSV/XLSX)
            <input type="file" accept=".csv,.xlsx,.xls" onChange={handleCompetitorsFile} />
            {compHint && <span className="field-hint">{compHint}</span>}
          </label>
        )}
        <button className="primary" disabled={busy} onClick={handleSave}>
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

function formatPubDate(value) {
  if (!value) return "дата н/д";
  try {
    return new Date(value).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return String(value);
  }
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

  const selected = list.find((x) => x.creative_id === metricId) || null;

  return (
    <section className="stack-page">
      <div className="panel-head">
        <div>
          <div className="eyebrow">Avito</div>
          <h1>Метрики</h1>
        </div>
      </div>
      <p className="lede">Выберите публикацию. Данные с Авито — только по «Обновить» в модалке.</p>
      <div className="rows">
        {list.map((p) => (
          <button key={p.creative_id} className="row-btn" onClick={() => onOpen(p.creative_id)}>
            <div>
              <strong>{p.title || `#${p.creative_id}`}</strong>
              <div className="mono muted">
                {formatPubDate(p.published_at)} · item {p.avito_item_id || "не задан"}
                {p.has_snapshot ? " · есть снимок" : ""}
              </div>
            </div>
            <span className="chev">›</span>
          </button>
        ))}
        {!list.length && <div className="muted">Нет утверждённых публикаций.</div>}
      </div>

      {metricId && (
        <div className="modal-scrim" onClick={() => onOpen(null)}>
          <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
            <div className="panel-head" style={{ marginBottom: 0 }}>
              <div>
                <div className="eyebrow">Статистика Avito</div>
                <h2>{selected?.title || `Публикация #${metricId}`}</h2>
                <div className="mono muted">{formatPubDate(selected?.published_at)}</div>
              </div>
            </div>
            <label>
              Avito item ID
              <input
                value={itemId}
                onChange={(e) => setItemId(e.target.value)}
                placeholder="числовой ID объявления"
              />
            </label>
            <div className="row-actions">
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
              <button className="primary" disabled={busy} onClick={() => onRefresh()}>
                Обновить
              </button>
              <button type="button" onClick={() => onOpen(null)}>
                Закрыть
              </button>
            </div>
            <span className="muted">
              {snapshot?.fetched_at
                ? `Снимок: ${formatPubDate(snapshot.fetched_at)}`
                : snapshot?.message || "Ещё не обновляли"}
            </span>
            <pre className="stat-json">{JSON.stringify(snapshot?.payload || {}, null, 2)}</pre>
          </div>
        </div>
      )}
    </section>
  );
}

function InstructionsPanel({ project }) {
  const feedUrl = buildFeedUrl(project);
  const [copied, setCopied] = useState("");
  const [tab, setTab] = useState("header");

  async function copyFeed() {
    try {
      await copyText(feedUrl);
      setCopied("Скопировано");
      setTimeout(() => setCopied(""), 1600);
    } catch (e) {
      setCopied(e.message || "Нет URL");
    }
  }

  const tabs = [
    { id: "header", label: "Хеддер" },
    { id: "setup", label: "Настройка проекта" },
    { id: "publish", label: "Публикация" },
  ];

  return (
    <section className="stack-page">
      <div className="panel-head">
        <div>
          <div className="eyebrow">Usage</div>
          <h1>Инструкции</h1>
        </div>
      </div>

      <div className="instr-tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`instr-tab ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "header" && (
        <div className="doc-card">
          <h3>Хеддер</h3>
          <ol>
            <li>
              Справа сверху — <strong>выбор проекта</strong> и «+ Новый проект». После создания в чате
              придёт онбординг.
            </li>
            <li>
              <strong>Изоляция:</strong> чат, настройки, фид, публикации и метрики привязаны только к
              выбранному <code>project_id</code>. Данные чужих проектов не читаются и не пишутся.
            </li>
            <li>
              Между брендом AvitologAI и picker — <strong>баланс OpenRouter</strong> (остаток / spend за
              месяц). Ключ на клиент не отдаётся.
            </li>
          </ol>
        </div>
      )}

      {tab === "setup" && (
        <>
          <div className="doc-card">
            <h3>Настройка проекта</h3>
            <ol>
              <li>
                <strong>Онбординг в чате</strong> — опишите нишу; слоты (идея, заголовок, боли, число
                фото…) и доп. промпты заполнятся сами (правки в Настройках). Можно импортировать CSV/XLSX
                конкурентов. Базовая методика агентов встроена и в UI не показывается.
              </li>
              <li>
                <strong>Оркестратор</strong> — модель OpenRouter + смыслы объявления (идея, поисковый
                запрос, преимущество, боли) и доп. промпт проекта.
              </li>
              <li>
                При необходимости отдельно: <strong>Генерация изображений</strong> (стиль проекта) и{" "}
                <strong>Vision</strong> (доп. разбор фото).
              </li>
              <li>
                <strong>Avito / Фид</strong> — категория, адрес, телефон для XML. Client ID/Secret
                опциональны (API upload). User ID — для метрик. URL фида копируется без API.
              </li>
            </ol>
          </div>
          <div className="doc-card">
            <h3>Avito: откуда → куда</h3>
            <div className="instr-table">
              <div>
                <strong>Значение</strong>
                <span className="muted">Откуда</span>
                <span className="muted">Куда</span>
              </div>
              <div>
                <strong>Категория / Адрес / Телефон</strong>
                <span>Настройки проекта</span>
                <span>XML Category / Address / ContactPhone</span>
              </div>
              <div>
                <strong>Feed URL</strong>
                <span>Кнопка «Скопировать URL»</span>
                <span>Кабинет Автозагрузки Авито</span>
              </div>
              <div>
                <strong>Client ID / Secret</strong>
                <span>developers.avito.ru / API кабинета</span>
                <span>Настройки → автопубликация (опционально)</span>
              </div>
              <div>
                <strong>User ID</strong>
                <span>Профиль Авито</span>
                <span>Метрики объявлений</span>
              </div>
            </div>
            <div className="avito-copy-row">
              <button type="button" className="btn-copy-sm" onClick={copyFeed}>
                Скопировать URL фида
              </button>
              {copied && <span className="muted">{copied}</span>}
            </div>
            {feedUrl ? (
              <p className="mono muted" style={{ wordBreak: "break-all", margin: 0 }}>
                {feedUrl}
              </p>
            ) : (
              <p className="muted">Выберите проект — URL появится после токена фида.</p>
            )}
          </div>
        </>
      )}

      {tab === "publish" && (
        <div className="doc-card">
          <h3>Публикация</h3>
          <ol>
            <li>
              <strong>Тестовый прогон:</strong> начните сообщение с «тестовый прогон» — эмуляция Авито,
              реальный онбординг/креатив/обучение. Затем «сделай пост». «Утвердить» публикует
              имитацию (без кабинета Авито).
            </li>
            <li>
              В чате явно укажите товар, цену, тон, ограничения; «без картинки» — если фото не нужно.
              Можно прикрепить фото скрепкой.
            </li>
            <li>
              После черновика: <strong>Утвердить</strong> — креатив в XML-фид (публикация), или напишите
              правки свободным текстом.
            </li>
            <li>
              При правках оркестратор: «Фиксирую ошибку» → классифицирует (общая / только проект) →
              сохраняет → «Выполняю правки» → новый черновик. Снова Утвердить или правки.
            </li>
            <li>
              После утверждения строка появляется в <strong>Метрики</strong> (название + дата). Клик —
              модалка; статистика Авито только по кнопке <strong>Обновить</strong>.
            </li>
          </ol>
        </div>
      )}
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
