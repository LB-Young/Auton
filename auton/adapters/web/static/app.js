const state = {
  projectPath: window.localStorage.getItem("auton.projectPath") || "",
  sessions: [],
  currentSessionId: null,
  currentSessionDate: null,
  currentTitle: "",
  streaming: false,
  mode: "date",
};

// 问候语按 projectPath 缓存，切换项目后自动失效
let greetingCache = {};

const els = {
  projectPath: document.getElementById("projectPath"),
  applyProject: document.getElementById("applyProject"),
  clearProject: document.getElementById("clearProject"),
  modeLabel: document.getElementById("modeLabel"),
  sessionList: document.getElementById("sessionList"),
  chatHistory: document.getElementById("chatHistory"),
  chatTitle: document.getElementById("chatTitle"),
  chatMeta: document.getElementById("chatMeta"),
  composer: document.getElementById("composer"),
  messageInput: document.getElementById("messageInput"),
  sendButton: document.getElementById("sendButton"),
  statusDot: document.getElementById("statusDot"),
  composerHint: document.getElementById("composerHint"),
  newSession: document.getElementById("newSession"),
};

let pendingAssistantEl = null;

function setStatus(status) {
  els.statusDot.textContent = status === "streaming" ? "生成中" : "闲置";
  els.statusDot.classList.toggle("streaming", status === "streaming");
  els.statusDot.classList.toggle("idle", status !== "streaming");
}

function renderSessions() {
  els.modeLabel.textContent = state.mode === "project" ? "项目会话" : "日期模式";
  els.projectPath.value = state.projectPath;
  els.sessionList.innerHTML = "";
  if (!state.sessions.length) {
    const empty = document.createElement("div");
    empty.className = "session-empty";
    empty.textContent = "暂无会话记录";
    els.sessionList.appendChild(empty);
    return;
  }
  state.sessions.forEach((session) => {
    const item = document.createElement("div");
    item.className = "session-item";
    if (session.session_id === state.currentSessionId) {
      item.classList.add("active");
    }
    item.addEventListener("click", () => selectSession(session));

    const title = document.createElement("div");
    title.className = "session-item-title";
    title.textContent = session.label || session.session_id;

    const meta = document.createElement("div");
    meta.className = "session-item-meta";
    meta.textContent = session.started_at || session.date || "";

    item.appendChild(title);
    item.appendChild(meta);
    els.sessionList.appendChild(item);
  });
}

async function loadSidebar() {
  const url = new URL("/api/sidebar", window.location.origin);
  if (state.projectPath) {
    url.searchParams.set("project_path", state.projectPath);
  }
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error("无法加载会话列表");
  }
  const data = await res.json();
  state.sessions = data.sessions || [];
  state.mode = data.mode || "date";
  renderSessions();
}

async function selectSession(session) {
  state.currentSessionId = session.session_id;
  state.currentSessionDate = session.date || null;
  state.currentTitle = session.label || "对话";
  renderSessions();
  await loadConversation();
}

function _greetingCacheKey() {
  return state.projectPath || "__date__";
}

async function loadGreeting() {
  const cacheKey = _greetingCacheKey();
  const cached = greetingCache[cacheKey];
  if (cached) {
    _appendGreetingBubble(cached);
    return;
  }

  // 先展示加载占位，再用真实问候替换
  const bubble = _appendGreetingBubble("…");
  try {
    const url = new URL("/api/greeting", window.location.origin);
    if (state.projectPath) {
      url.searchParams.set("project_path", state.projectPath);
    }
    const res = await fetch(url);
    const text = res.ok
      ? ((await res.json()).greeting || "你好！我是 Auton，有什么可以帮你的吗？")
      : "你好！我是 Auton，有什么可以帮你的吗？";
    greetingCache[cacheKey] = text;
    bubble.textContent = text;
  } catch {
    bubble.textContent = "你好！我是 Auton，有什么可以帮你的吗？";
  }
}

function _appendGreetingBubble(text) {
  const bubble = document.createElement("div");
  bubble.className = "message assistant greeting";
  bubble.textContent = text;
  els.chatHistory.appendChild(bubble);
  scrollToBottom();
  return bubble;
}

async function loadConversation() {
  if (!state.currentSessionId) {
    els.chatHistory.innerHTML = "";
    els.chatTitle.textContent = "新会话";
    els.chatMeta.textContent = state.mode === "project" ? "项目模式" : "日期模式";
    await loadGreeting();
    return;
  }
  const url = new URL(`/api/sessions/${state.currentSessionId}`, window.location.origin);
  if (state.projectPath) {
    url.searchParams.set("project_path", state.projectPath);
  }
  if (state.currentSessionDate) {
    url.searchParams.set("session_date", state.currentSessionDate);
  }
  const res = await fetch(url);
  if (!res.ok) {
    els.chatHistory.innerHTML = `<div class="session-empty">无法加载会话</div>`;
    return;
  }
  const data = await res.json();
  state.currentSessionDate = data.session_date || state.currentSessionDate;
  const messages = data.messages || [];
  els.chatHistory.innerHTML = "";
  messages.forEach((msg) => appendMessage(msg.role, msg.content));
  els.chatTitle.textContent = state.currentTitle || "对话";
  els.chatMeta.textContent = `Session: ${state.currentSessionId}`;
  scrollToBottom();
}

function appendMessage(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `message ${role}`;
  bubble.textContent = text;
  els.chatHistory.appendChild(bubble);
  scrollToBottom();
  return bubble;
}

function ensureAssistantBubble() {
  if (!pendingAssistantEl) {
    pendingAssistantEl = appendMessage("assistant", "");
  }
  return pendingAssistantEl;
}

function updateAssistantText(delta) {
  const el = ensureAssistantBubble();
  el.textContent += delta;
  scrollToBottom();
}

function finalizeAssistantText(text) {
  if (pendingAssistantEl) {
    pendingAssistantEl.textContent = text;
    pendingAssistantEl = null;
  } else {
    appendMessage("assistant", text);
  }
  scrollToBottom();
}

function showSystemInfo(text) {
  const bubble = document.createElement("div");
  bubble.className = "message assistant";
  bubble.textContent = text;
  bubble.style.opacity = 0.8;
  bubble.style.fontSize = "13px";
  els.chatHistory.appendChild(bubble);
  scrollToBottom();
}

function showToolOutput(name, output, error = false) {
  const bubble = document.createElement("div");
  bubble.className = `message assistant tool${error ? " error" : ""}`;
  const preview = output.length > 30 ? `${output.slice(0, 30)}…` : output;
  bubble.textContent = `[${name}] ${preview}`;
  els.chatHistory.appendChild(bubble);
  scrollToBottom();
}

async function streamChat(message) {
  state.streaming = true;
  setStatus("streaming");
  pendingAssistantEl = null;
  const payload = {
    message,
    session_id: state.currentSessionId,
    project_path: state.projectPath || null,
    session_date: state.currentSessionDate || null,
  };

  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok || !res.body) {
    showSystemInfo("请求失败，无法连接到服务端。");
    state.streaming = false;
    setStatus("idle");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (!line) continue;
      handleStreamEvent(JSON.parse(line));
    }
  }
  state.streaming = false;
  setStatus("idle");
}

function handleStreamEvent(event) {
  switch (event.type) {
    case "session":
      state.currentSessionId = event.session_id;
      state.currentSessionDate = event.session_date || state.currentSessionDate;
      els.chatMeta.textContent = `Session: ${state.currentSessionId}`;
      break;
    case "delta":
      updateAssistantText(event.text || "");
      break;
    case "message":
      finalizeAssistantText(event.text || "");
      break;
    case "tool_call":
      showToolOutput(event.name || "tool", "调用中…");
      break;
    case "tool_result":
      showToolOutput(event.name || "tool", event.output || "");
      break;
    case "tool_error":
      showToolOutput(event.name || "tool", event.error || "工具错误", true);
      break;
    case "command":
      showSystemInfo(event.content || "");
      break;
    case "error":
      showSystemInfo(event.message || "发生错误");
      break;
    case "result":
      // no-op for now
      break;
    case "complete":
      state.streaming = false;
      setStatus("idle");
      pendingAssistantEl = null;
      loadSidebar().catch(() => {});
      break;
    default:
      break;
  }
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    els.chatHistory.scrollTop = els.chatHistory.scrollHeight;
  });
}

function bindEvents() {
  els.applyProject.addEventListener("click", async () => {
    state.projectPath = els.projectPath.value.trim();
    window.localStorage.setItem("auton.projectPath", state.projectPath);
    state.currentSessionId = null;
    state.currentSessionDate = null;
    state.currentTitle = "";
    delete greetingCache[_greetingCacheKey()];
    await loadSidebar();
    await loadConversation();
  });

  els.clearProject.addEventListener("click", async () => {
    delete greetingCache[_greetingCacheKey()];
    state.projectPath = "";
    els.projectPath.value = "";
    window.localStorage.removeItem("auton.projectPath");
    state.currentSessionId = null;
    state.currentSessionDate = null;
    await loadSidebar();
    await loadConversation();
  });

  els.newSession.addEventListener("click", async () => {
    state.currentSessionId = null;
    state.currentSessionDate = null;
    state.currentTitle = "新会话";
    els.chatHistory.innerHTML = "";
    els.chatTitle.textContent = "新会话";
    els.chatMeta.textContent = state.mode === "project" ? "项目模式" : "日期模式";
    await loadGreeting();
  });

  els.composer.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.streaming) return;
    const text = els.messageInput.value.trim();
    if (!text) return;
    appendMessage("user", text);
    els.messageInput.value = "";
    setTimeout(() => { els.messageInput.value = ""; }, 0);
    await streamChat(text);
  });

  let isComposing = false;
  let compositionEndTime = 0;
  let enterWasIME = false;

  els.messageInput.addEventListener("compositionstart", () => {
    isComposing = true;
  });
  els.messageInput.addEventListener("compositionend", () => {
    isComposing = false;
    compositionEndTime = Date.now();
  });

  // keydown 只做两件事：阻止换行插入、记录本次 Enter 是否属于 IME
  els.messageInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    // 记录判断结果供 keyup 使用，不在这里触发提交
    // Chrome 序列：keydown(isComposing=true) → compositionend → keyup
    // Safari 序列：compositionend → keydown(isComposing=false) → keyup
    // 两种情况都可以通过此处的三重检查覆盖
    enterWasIME = event.isComposing || isComposing || (Date.now() - compositionEndTime < 300);
  });

  // keyup 时所有 IME 事件已经结束，此时做提交判断最安全
  els.messageInput.addEventListener("keyup", (event) => {
    if (event.key !== "Enter" || event.shiftKey) return;

    // Chrome：compositionend 在 keydown 之后、keyup 之前触发
    // 所以到 keyup 时 compositionEndTime 已经更新，timestamp 检查能覆盖这种情况
    const blocked = enterWasIME
      || event.isComposing
      || isComposing
      || (Date.now() - compositionEndTime < 300);

    enterWasIME = false;
    if (blocked) return;

    els.composer.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
}

async function bootstrap() {
  bindEvents();
  await loadSidebar();
  await loadConversation();
}

bootstrap().catch((err) => {
  console.error(err);
  showSystemInfo("初始化失败，请检查服务端日志。");
});
