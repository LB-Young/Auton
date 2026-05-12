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
/** 同一 cacheKey 上并发/重复 init 时复用，避免叠多条「…」问候 */
let _greetingInFlight = null;

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
  if (els.sendButton) {
    els.sendButton.disabled = status === "streaming";
  }
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
    for (const el of els.chatHistory.querySelectorAll(".message.assistant.greeting")) {
      el.remove();
    }
    _appendGreetingBubble(cached);
    return;
  }
  if (_greetingInFlight && _greetingInFlight._key === cacheKey) {
    return _greetingInFlight;
  }
  const p = (async () => {
    for (const el of els.chatHistory.querySelectorAll(".message.assistant.greeting")) {
      el.remove();
    }
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
      if (document.body.contains(bubble)) {
        bubble.textContent = text;
      }
    } catch {
      if (document.body.contains(bubble)) {
        bubble.textContent = "你好！我是 Auton，有什么可以帮你的吗？";
      }
    }
  })();
  p._key = cacheKey;
  _greetingInFlight = p;
  try {
    await p;
  } finally {
    if (_greetingInFlight === p) {
      _greetingInFlight = null;
    }
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

function _lastContentAssistantBubble() {
  const items = els.chatHistory.querySelectorAll(".message.assistant");
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const el = items[i];
    if (el.classList.contains("greeting") || el.classList.contains("tool")) continue;
    return el;
  }
  return null;
}

// 只处理**末尾若干行**内、与上一行完全相同的**短行**（模型常重复结语文案）
function _collapseTailStutter(text, tailLineCap = 30) {
  const s = (text || "").replace(/\r\n/g, "\n");
  const lines = s.split("\n");
  if (lines.length < 2) {
    return text;
  }
  const k = Math.min(tailLineCap, lines.length);
  const head = lines.slice(0, -k);
  const tail = lines.slice(-k);
  const out = [];
  for (const line of tail) {
    if (
      out.length
      && line === out[out.length - 1]
      && line.trim().length < 200
    ) {
      continue;
    }
    out.push(line);
  }
  return [...head, ...out].join("\n");
}

function finalizeAssistantText(text) {
  const norm = (s) => (s || "").trim();
  const t = _collapseTailStutter(norm(text));
  if (pendingAssistantEl) {
    pendingAssistantEl.textContent = t;
    pendingAssistantEl = null;
  } else {
    const prev = _lastContentAssistantBubble();
    if (prev && norm(prev.textContent) === t && t.length > 0) {
      return;
    }
    appendMessage("assistant", t);
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

  try {
    const res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok || !res.body) {
      showSystemInfo("请求失败，无法连接到服务端。");
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
        try {
          handleStreamEvent(JSON.parse(line));
        } catch (err) {
          console.error("stream line parse", err, line);
          showSystemInfo("流式数据解析失败，请重试或查看控制台。");
        }
      }
    }
  } catch (err) {
    console.error(err);
    showSystemInfo("网络或流式连接中断，请重试。");
  } finally {
    state.streaming = false;
    setStatus("idle");
  }
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
  if (window.__autonWebEventsBound) {
    return;
  }
  window.__autonWebEventsBound = true;
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
    // 在任意 await 之前占用 streaming，避免快速连发 Enter 造成重复请求与重复整段展示
    state.streaming = true;
    setStatus("streaming");
    appendMessage("user", text);
    els.messageInput.value = "";
    setTimeout(() => { els.messageInput.value = ""; }, 0);
    try {
      await streamChat(text);
    } catch (e) {
      console.error(e);
    }
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
