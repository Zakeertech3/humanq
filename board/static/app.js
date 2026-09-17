const STORAGE_KEY = "humanq_admin_key";
const POLL_MS = 5000;
const FLASH_MS = 2000;
const TAG_TYPES = ["credential", "approval", "choice", "clarification"];

const gate = document.getElementById("gate");
const gateError = document.getElementById("gate-error");
const keyInput = document.getElementById("key");
const saveButton = document.getElementById("save");
const boardSection = document.getElementById("board");
const listEl = document.getElementById("list");
const emptyEl = document.getElementById("empty");
const countEl = document.getElementById("count");
const updatedEl = document.getElementById("updated");
const warningEl = document.getElementById("warning");
const signoutEl = document.getElementById("signout");
const flashEl = document.getElementById("flash");
const tabOpen = document.getElementById("tab-open");
const tabResolved = document.getElementById("tab-resolved");

let view = "open";
let items = [];
let expandedId = null;
let lastUpdated = null;
const drafts = new Map();
let timer = null;
let flashTimer = null;
let renderedIds = new Set();
let firstRenderDone = false;

function readKey() {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch (error) {
    return null;
  }
}

function writeKey(value) {
  try {
    window.localStorage.setItem(STORAGE_KEY, value);
  } catch (error) {
    return;
  }
}

function clearKey() {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    return;
  }
}

function plural(count, word) {
  return count === 1 ? `1 ${word}` : `${count} ${word}s`;
}

function blockedLabel(count) {
  return count === 1 ? "1 task blocked" : `${count} tasks blocked`;
}

function durationLabel(fromIso, toIso) {
  const from = new Date(fromIso).getTime();
  const to = toIso ? new Date(toIso).getTime() : Date.now();
  if (Number.isNaN(from) || Number.isNaN(to)) {
    return "";
  }
  const seconds = Math.max(0, Math.floor((to - from) / 1000));
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ${minutes % 60}m`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d ${hours % 24}h`;
}

function waitingLabel(item) {
  const span = durationLabel(item.created_at, null);
  if (span === "") {
    return "";
  }
  return `${span} waiting`;
}

function stamp(iso) {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) {
    return "";
  }
  return when.toLocaleTimeString();
}

function resolvedLine(item) {
  const span = durationLabel(item.created_at, item.resolved_at);
  return `waited ${span}, resolved at ${stamp(item.resolved_at)}`;
}

function emptyText() {
  return view === "open"
    ? "Nothing open. Every agent is unblocked."
    : "Nothing resolved yet.";
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined && text !== null) {
    node.textContent = String(text);
  }
  return node;
}

function showGate(message) {
  stopPolling();
  items = [];
  expandedId = null;
  drafts.clear();
  renderedIds = new Set();
  firstRenderDone = false;
  gate.hidden = false;
  boardSection.hidden = true;
  signoutEl.hidden = true;
  countEl.textContent = "";
  updatedEl.textContent = "";
  gateError.hidden = !message;
  gateError.textContent = message || "";
  keyInput.value = "";
  keyInput.focus();
}

function showBoard() {
  gate.hidden = true;
  gateError.hidden = true;
  boardSection.hidden = false;
  signoutEl.hidden = false;
}

function flashResolved() {
  flashEl.textContent = "Resolved";
  flashEl.hidden = false;
  flashEl.style.animation = "none";
  void flashEl.offsetWidth;
  flashEl.style.animation = "";
  window.clearTimeout(flashTimer);
  flashTimer = window.setTimeout(() => {
    flashEl.hidden = true;
  }, FLASH_MS);
}

async function api(path, options) {
  const key = readKey();
  const headers = { Authorization: `Bearer ${key}` };
  if (options && options.body) {
    headers["Content-Type"] = "application/json";
  }
  return fetch(path, { ...options, headers });
}

function renderHeader() {
  countEl.textContent = plural(items.length, view === "open" ? "open request" : "resolved request");
  updatedEl.textContent = lastUpdated ? `updated ${lastUpdated.toLocaleTimeString()}` : "";
}

function buildBody(item) {
  const body = element("div", "body");
  body.appendChild(element("p", "detail", item.detail));

  if (item.status === "resolved") {
    body.appendChild(element("div", "resolution", item.resolution || ""));
    if (item.resolved_at) {
      body.appendChild(element("p", "resolution-when", resolvedLine(item)));
    }
    return body;
  }

  const box = element("textarea");
  box.value = drafts.get(item.id) || "";
  box.placeholder = "Your decision";

  if (Array.isArray(item.options) && item.options.length > 0) {
    const options = element("div", "options");
    for (const option of item.options) {
      const optionButton = element("button", "option", option);
      optionButton.type = "button";
      optionButton.addEventListener("click", () => {
        box.value = option;
        drafts.set(item.id, option);
        resolveButton.disabled = false;
        box.focus();
      });
      options.appendChild(optionButton);
    }
    body.appendChild(options);
  }

  body.appendChild(box);

  const actions = element("div", "actions");
  const resolveButton = element("button", "primary", "Resolve");
  resolveButton.type = "button";
  resolveButton.disabled = box.value.trim().length === 0;
  actions.appendChild(resolveButton);
  body.appendChild(actions);

  const rowError = element("p", "row-error");
  rowError.hidden = true;
  body.appendChild(rowError);

  box.addEventListener("input", () => {
    drafts.set(item.id, box.value);
    resolveButton.disabled = box.value.trim().length === 0;
  });

  resolveButton.addEventListener("click", async () => {
    const text = box.value.trim();
    if (text.length === 0) {
      return;
    }
    resolveButton.disabled = true;
    rowError.hidden = true;
    try {
      const response = await api(`/requests/${item.id}/resolve`, {
        method: "POST",
        body: JSON.stringify({ resolution: text }),
      });
      if (response.status === 401) {
        handleUnauthorized();
        return;
      }
      if (!response.ok) {
        rowError.textContent = `Could not resolve (${response.status}).`;
        rowError.hidden = false;
        resolveButton.disabled = false;
        return;
      }
      drafts.delete(item.id);
      expandedId = null;
      flashResolved();
      await refresh();
    } catch (error) {
      rowError.textContent = "Could not reach the board.";
      rowError.hidden = false;
      resolveButton.disabled = false;
    }
  });

  return body;
}

function buildCard(item) {
  const card = element("div", "card");
  card.dataset.id = item.id;
  if (firstRenderDone && !renderedIds.has(item.id)) {
    card.classList.add("is-new");
  }
  if (expandedId === item.id) {
    card.classList.add("expanded");
  }

  const head = element("div", "card-head");
  head.appendChild(element("div", "score", item.score));

  const main = element("div", "card-main");
  main.appendChild(element("div", "title", item.title));

  const meta = element("div", "meta");
  const tag = element("span", "tag", item.request_type);
  if (TAG_TYPES.includes(item.request_type)) {
    tag.classList.add(`tag-${item.request_type}`);
  }
  meta.appendChild(tag);
  meta.appendChild(element("span", null, item.agent_name));
  meta.appendChild(element("span", null, blockedLabel(item.blocked_tasks)));
  if (!item.resolved_at) {
    meta.appendChild(element("span", null, waitingLabel(item)));
  }
  main.appendChild(meta);

  head.appendChild(main);
  card.appendChild(head);

  head.addEventListener("click", () => {
    expandedId = expandedId === item.id ? null : item.id;
    renderList(true);
  });

  if (expandedId === item.id) {
    card.appendChild(buildBody(item));
  }
  return card;
}

function renderList(force) {
  if (!force && expandedId !== null) {
    return;
  }
  listEl.replaceChildren();
  for (const item of items) {
    listEl.appendChild(buildCard(item));
  }
  renderedIds = new Set(items.map((item) => item.id));
  firstRenderDone = true;
  emptyEl.textContent = emptyText();
  emptyEl.hidden = items.length > 0;
}

function handleUnauthorized() {
  clearKey();
  showGate("That key was rejected. Enter it again.");
}

async function refresh() {
  if (!readKey()) {
    showGate();
    return;
  }
  try {
    const response = await api(`/requests?status=${view}`);
    if (response.status === 401) {
      handleUnauthorized();
      return;
    }
    if (!response.ok) {
      warningEl.textContent = `The board replied with ${response.status}.`;
      warningEl.hidden = false;
      return;
    }
    items = await response.json();
    lastUpdated = new Date();
    warningEl.hidden = true;
    renderHeader();
    renderList(false);
  } catch (error) {
    warningEl.textContent = "Cannot reach the board. Still trying.";
    warningEl.hidden = false;
  }
}

function startPolling() {
  stopPolling();
  timer = window.setInterval(refresh, POLL_MS);
}

function stopPolling() {
  if (timer !== null) {
    window.clearInterval(timer);
    timer = null;
  }
}

function setView(next) {
  if (view === next) {
    return;
  }
  view = next;
  expandedId = null;
  items = [];
  renderedIds = new Set();
  firstRenderDone = false;
  tabOpen.classList.toggle("active", view === "open");
  tabResolved.classList.toggle("active", view === "resolved");
  listEl.replaceChildren();
  emptyEl.hidden = true;
  refresh();
}

saveButton.addEventListener("click", () => {
  const value = keyInput.value.trim();
  if (value.length === 0) {
    gateError.textContent = "Enter a key.";
    gateError.hidden = false;
    return;
  }
  writeKey(value);
  showBoard();
  refresh();
  startPolling();
});

keyInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    saveButton.click();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && expandedId !== null) {
    expandedId = null;
    renderList(true);
  }
});

signoutEl.addEventListener("click", (event) => {
  event.preventDefault();
  clearKey();
  showGate();
});

tabOpen.addEventListener("click", () => setView("open"));
tabResolved.addEventListener("click", () => setView("resolved"));

if (readKey()) {
  showBoard();
  refresh();
  startPolling();
} else {
  showGate();
}
