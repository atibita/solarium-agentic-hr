/**
 * static/js/chat.js
 * --------------------
 * Client-side logic for the Solarium HR Assistant chat UI. Vanilla JS, no
 * build step or framework required (keeps the app trivially deployable on
 * a free-tier static+Flask host). Talks to the Flask backend via
 * POST /chat, GET /health, GET /api/demo-tasks, GET /api/sample-employees.
 *
 * Security note: all model/user text is rendered through `escapeHtml()`
 * before any markdown-lite formatting is applied, and formatting only ever
 * *adds* a small, fixed allow-list of tags (<strong>, <em>, <code>, <ul>,
 * <li>, <br>, <p>, <pre>) — never raw HTML from the server or the user.
 */

const chatScroll = document.getElementById("chatScroll");
const composerForm = document.getElementById("composerForm");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const employeeSelect = document.getElementById("employeeSelect");
const demoTaskList = document.getElementById("demoTaskList");
const healthDot = document.getElementById("healthDot");
const healthLabel = document.getElementById("healthLabel");
const tracePanel = document.getElementById("tracePanel");
const traceContent = document.getElementById("traceContent");
const traceToggleBtn = document.getElementById("traceToggleBtn");
const traceCloseBtn = document.getElementById("traceCloseBtn");
const sidebar = document.getElementById("sidebar");
const sidebarOpen = document.getElementById("sidebarOpen");
const sidebarClose = document.getElementById("sidebarClose");
const sidebarScrim = document.getElementById("sidebarScrim");

let lastPendingAction = null;

// ---------------------------------------------------------------------
// Small, safe markdown-lite renderer (escape first, then allow-list markup)
// ---------------------------------------------------------------------
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderMarkdownLite(raw) {
  let html = escapeHtml(raw);

  // fenced code blocks ```...```
  html = html.replace(/```([\s\S]*?)```/g, (_, code) => `<pre>${code.trim()}</pre>`);
  // inline code `...`
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  // bold **...**
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // bullet lines "- item"
  html = html.replace(/(^|\n)-\s+(.*)/g, "$1<li>$2</li>");
  html = html.replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>");
  // paragraphs: split on blank lines
  html = html
    .split(/\n{2,}/)
    .map((block) => (block.startsWith("<ul>") || block.startsWith("<pre>") ? block : `<p>${block.replace(/\n/g, "<br>")}</p>`))
    .join("");

  return html;
}

// ---------------------------------------------------------------------
// Message rendering
// ---------------------------------------------------------------------
function addMessage({ role, html, citations = [], workflow = null, pendingAction = null }) {
  const wrap = document.createElement("div");
  wrap.className = `msg msg-${role}`;

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar";
  avatar.textContent = role === "user" ? "You".charAt(0) : "S";
  avatar.setAttribute("aria-hidden", "true");

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.innerHTML = html;

  if (workflow) {
    const meta = document.createElement("div");
    meta.className = "msg-meta";
    const badge = document.createElement("span");
    badge.className = "badge workflow";
    badge.textContent = workflow.replaceAll("_", " ");
    meta.appendChild(badge);
    bubble.appendChild(meta);
  }

  if (citations && citations.length) {
    const citeWrap = document.createElement("div");
    citeWrap.className = "citations";
    citations.forEach((c) => {
      const chip = document.createElement("div");
      chip.className = "citation-chip";
      chip.innerHTML = `<strong>${escapeHtml(c.doc_id)}</strong> — ${escapeHtml(c.section)}: ${escapeHtml(c.snippet)}`;
      citeWrap.appendChild(chip);
    });
    bubble.appendChild(citeWrap);
  }

  if (pendingAction) {
    const pa = document.createElement("div");
    pa.className = "pending-action";
    pa.innerHTML = `<span>This action hasn't happened yet — confirm to proceed.</span>`;
    const btn = document.createElement("button");
    btn.className = "btn-confirm";
    btn.textContent = "Confirm";
    btn.onclick = () => confirmPendingAction(pendingAction);
    pa.appendChild(btn);
    bubble.appendChild(pa);
  }

  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  chatScroll.appendChild(wrap);
  chatScroll.scrollTop = chatScroll.scrollHeight;
  return wrap;
}

function addLoadingMessage() {
  const wrap = document.createElement("div");
  wrap.className = "msg msg-agent msg-loading";
  wrap.innerHTML = `
    <div class="msg-avatar" aria-hidden="true">S</div>
    <div class="msg-bubble"><span class="dot"></span><span class="dot"></span><span class="dot"></span></div>
  `;
  chatScroll.appendChild(wrap);
  chatScroll.scrollTop = chatScroll.scrollHeight;
  return wrap;
}

// ---------------------------------------------------------------------
// Trace panel rendering
// ---------------------------------------------------------------------
function renderTrace(trace) {
  if (!trace || !trace.length) {
    traceContent.innerHTML = `<p class="trace-empty">No tool calls were needed for that answer.</p>`;
    return;
  }
  traceContent.innerHTML = "";
  trace.forEach((step, i) => {
    const el = document.createElement("div");
    const cls = step.tool_ok === true ? "ok" : step.tool_ok === false ? "fail" : "neutral";
    el.className = `trace-step ${cls}`;
    let toolBlock = "";
    if (step.tool_name) {
      toolBlock = `<div class="trace-step-tool">${escapeHtml(step.tool_name)}(${escapeHtml(
        JSON.stringify(step.tool_arguments || {})
      )})${step.latency_ms != null ? ` — ${step.latency_ms}ms` : ""}</div>`;
    }
    el.innerHTML = `
      <div class="trace-step-head">
        <span class="trace-step-index">${i + 1}</span>
        <span class="trace-step-name">${escapeHtml(step.step.replaceAll("_", " "))}</span>
      </div>
      <div class="trace-step-detail">${escapeHtml(step.detail)}</div>
      ${toolBlock}
    `;
    traceContent.appendChild(el);
  });
}

// ---------------------------------------------------------------------
// Networking
// ---------------------------------------------------------------------
async function sendChat(body) {
  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errPayload = await res.json().catch(() => ({}));
    throw new Error(errPayload.error || `Request failed (${res.status})`);
  }
  return res.json();
}

async function handleSubmitMessage(message) {
  const employeeId = employeeSelect.value || null;
  addMessage({ role: "user", html: renderMarkdownLite(message) });
  const loadingEl = addLoadingMessage();

  try {
    const data = await sendChat({ message, employee_id: employeeId });
    loadingEl.remove();
    lastPendingAction = data.pending_action || null;
    addMessage({
      role: "agent",
      html: renderMarkdownLite(data.answer),
      citations: data.citations,
      workflow: data.workflow,
      pendingAction: data.pending_action,
    });
    renderTrace(data.trace);
  } catch (err) {
    loadingEl.remove();
    const el = addMessage({ role: "agent", html: `<p>Sorry — ${escapeHtml(err.message)}</p>` });
    el.querySelector(".msg-bubble").classList.add("error-bubble");
  }
}

async function confirmPendingAction(pendingAction) {
  const loadingEl = addLoadingMessage();
  try {
    const data = await sendChat({ message: "", confirm: true, pending_action: pendingAction });
    loadingEl.remove();
    addMessage({
      role: "agent",
      html: renderMarkdownLite(data.answer),
      citations: data.citations,
      workflow: data.workflow,
    });
    renderTrace(data.trace);
  } catch (err) {
    loadingEl.remove();
    addMessage({ role: "agent", html: `<p>Sorry — ${escapeHtml(err.message)}</p>` });
  }
}

// ---------------------------------------------------------------------
// Init: health, sample employees, demo tasks
// ---------------------------------------------------------------------
async function initHealth() {
  try {
    const res = await fetch("/health");
    const data = await res.json();
    const connected = data.mcp && data.mcp.connected;
    healthDot.classList.add(connected ? "ok" : "bad");
    healthLabel.textContent = connected
      ? `Online · ${data.mcp.tool_count} MCP tools (${data.mcp.transport})`
      : "MCP tools unavailable";
  } catch {
    healthDot.classList.add("bad");
    healthLabel.textContent = "Unable to reach server";
  }
}

async function initSampleEmployees() {
  try {
    const res = await fetch("/api/sample-employees");
    const employees = await res.json();
    employees.forEach((e) => {
      const opt = document.createElement("option");
      opt.value = e.employee_id;
      opt.textContent = `${e.name} — ${e.title} (${e.employee_id})`;
      employeeSelect.appendChild(opt);
    });
  } catch {
    /* non-critical UX convenience; fail silently */
  }
}

async function initDemoTasks() {
  try {
    const res = await fetch("/api/demo-tasks");
    const data = await res.json();
    data.tasks.forEach((task) => {
      const btn = document.createElement("button");
      btn.className = "demo-task-btn";
      btn.innerHTML = `<span class="task-title">${escapeHtml(task.title)}</span><span class="task-sub">${escapeHtml(
        task.message
      )}</span>`;
      btn.onclick = () => {
        if (task.employee_id) {
          employeeSelect.value = task.employee_id;
        }
        handleSubmitMessage(task.message);
        if (window.innerWidth <= 880) closeSidebar();
      };
      demoTaskList.appendChild(btn);
    });
  } catch {
    demoTaskList.innerHTML = `<p class="trace-empty">Demo tasks unavailable.</p>`;
  }
}

// ---------------------------------------------------------------------
// UI wiring
// ---------------------------------------------------------------------
composerForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;
  messageInput.value = "";
  messageInput.style.height = "auto";
  handleSubmitMessage(message);
});

messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    composerForm.requestSubmit();
  }
});

messageInput.addEventListener("input", () => {
  messageInput.style.height = "auto";
  messageInput.style.height = `${Math.min(messageInput.scrollHeight, 140)}px`;
});

traceToggleBtn.addEventListener("click", () => {
  const willOpen = !tracePanel.classList.contains("open");
  tracePanel.classList.toggle("open", willOpen);
  traceToggleBtn.setAttribute("aria-pressed", String(willOpen));
});
traceCloseBtn.addEventListener("click", () => {
  tracePanel.classList.remove("open");
  traceToggleBtn.setAttribute("aria-pressed", "false");
});

function openSidebar() {
  sidebar.classList.add("open");
  sidebarScrim.classList.add("open");
}
function closeSidebar() {
  sidebar.classList.remove("open");
  sidebarScrim.classList.remove("open");
}
sidebarOpen.addEventListener("click", openSidebar);
sidebarClose.addEventListener("click", closeSidebar);
sidebarScrim.addEventListener("click", closeSidebar);

// ---------------------------------------------------------------------
initHealth();
initSampleEmployees();
initDemoTasks();
