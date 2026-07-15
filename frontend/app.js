const CATEGORIES = ["order_issue", "billing_and_payment", "product_inquiry", "technical_support"];
const PRIORITIES = ["low", "medium", "high"];
const TEAMS = ["fulfilment", "billing", "sales", "technical_support"];

// ---------- tiny helpers ----------

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "text") node.textContent = value;
    else if (key === "html") node.innerHTML = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) node.appendChild(child);
  return node;
}

function priorityBadge(priority) {
  return el("span", { class: `badge priority-${priority}`, text: priority.toUpperCase() });
}

function badge(text) {
  return el("span", { class: "badge", text });
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || `Request failed (${res.status})`);
  return data;
}

// ---------- tabs ----------

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");

    if (btn.dataset.tab === "teams") loadTeamQueue();
    if (btn.dataset.tab === "admin") loadAdminQueue();
    if (btn.dataset.tab === "metrics") loadMetrics();
  });
});

// ---------- submit ----------

const ticketInput = document.getElementById("ticket-input");
const submitBtn = document.getElementById("submit-btn");
const submitResult = document.getElementById("submit-result");

submitBtn.addEventListener("click", async () => {
  const text = ticketInput.value.trim();
  if (!text) return;

  submitBtn.disabled = true;
  submitBtn.textContent = "Routing...";
  submitResult.innerHTML = "";

  try {
    const ticket = await api("/route", { method: "POST", body: JSON.stringify({ text }) });
    submitResult.appendChild(renderResultCard(ticket));
    ticketInput.value = "";
  } catch (err) {
    submitResult.appendChild(
      el("div", { class: "ticket-card", html: `<p class="reasoning" style="color:#ff3b30">Rejected: ${err.message}</p>` })
    );
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Route Ticket";
  }
});

function renderResultCard(ticket) {
  const card = el("div", { class: "ticket-card" });
  card.appendChild(el("p", { class: "ticket-input-text", text: `"${ticket.input}"` }));
  const badges = el("div", { class: "badge-row" });
  badges.appendChild(badge(ticket.category));
  badges.appendChild(priorityBadge(ticket.priority));
  badges.appendChild(badge(`team: ${ticket.team}`));
  badges.appendChild(badge(`confidence: ${ticket.confidence}`));
  card.appendChild(badges);
  card.appendChild(el("p", { class: "reasoning", text: ticket.reasoning }));
  return card;
}

// ---------- team queues ----------

const teamSelect = document.getElementById("team-select");
const teamQueueList = document.getElementById("team-queue-list");

teamSelect.addEventListener("change", loadTeamQueue);

async function loadTeamQueue() {
  teamQueueList.innerHTML = `<p class="spinner-text">Loading...</p>`;
  const team = teamSelect.value;
  try {
    const data = await api(`/team-queue?team_name=${team}`);
    renderTeamQueue(data.team_queue);
  } catch (err) {
    teamQueueList.innerHTML = `<p class="empty-state">${err.message}</p>`;
  }
}

function renderTeamQueue(tickets) {
  teamQueueList.innerHTML = "";
  if (!tickets.length) {
    teamQueueList.appendChild(el("p", { class: "empty-state", text: "No tickets routed to this team right now." }));
    return;
  }
  tickets.forEach((ticket) => teamQueueList.appendChild(renderTeamTicketCard(ticket)));
}

function renderTeamTicketCard(ticket) {
  const card = el("div", { class: "ticket-card" });
  card.appendChild(el("p", { class: "ticket-input-text", text: `"${ticket.input}"` }));

  const badges = el("div", { class: "badge-row" });
  badges.appendChild(badge(ticket.category));
  badges.appendChild(priorityBadge(ticket.priority));
  badges.appendChild(badge(`confidence: ${ticket.confidence}`));
  card.appendChild(badges);

  card.appendChild(el("p", { class: "reasoning", text: ticket.reasoning }));

  const actions = el("div", { class: "ticket-actions" });

  const confidenceInput = el("input", { type: "number", min: "0", max: "100", placeholder: "90", style: "width:70px" });
  const boostBtn = el("button", { class: "secondary-btn", text: "Boost confidence" });
  boostBtn.addEventListener("click", async () => {
    const confidence = confidenceInput.value ? Number(confidenceInput.value) : null;
    await api("/boost_confidence", {
      method: "POST",
      body: JSON.stringify({ ticket_id: ticket.id, confidence }),
    });
    loadTeamQueue();
  });

  const flagBtn = el("button", { class: "secondary-btn", text: "Flag to admin" });
  flagBtn.addEventListener("click", async () => {
    await api(`/flagged/${ticket.id}`, { method: "POST" });
    loadTeamQueue();
  });

  const clearBtn = el("button", { class: "link-btn", text: "Clear" });
  clearBtn.addEventListener("click", async () => {
    await api(`/clear/${ticket.id}`, { method: "POST" });
    loadTeamQueue();
  });

  actions.appendChild(confidenceInput);
  actions.appendChild(boostBtn);
  actions.appendChild(flagBtn);
  actions.appendChild(clearBtn);
  card.appendChild(actions);

  return card;
}

// ---------- admin queue ----------

const adminQueueList = document.getElementById("admin-queue-list");

async function loadAdminQueue() {
  adminQueueList.innerHTML = `<p class="spinner-text">Loading...</p>`;
  try {
    const data = await api("/admin-queue");
    renderAdminQueue(data.admin_queue);
  } catch (err) {
    adminQueueList.innerHTML = `<p class="empty-state">${err.message}</p>`;
  }
}

function renderAdminQueue(tickets) {
  adminQueueList.innerHTML = "";
  if (!tickets.length) {
    adminQueueList.appendChild(el("p", { class: "empty-state", text: "No flagged tickets right now." }));
    return;
  }
  tickets.forEach((ticket) => adminQueueList.appendChild(renderAdminTicketCard(ticket)));
}

function selectOf(options, current) {
  const select = el("select");
  options.forEach((opt) => {
    const option = el("option", { value: opt, text: opt });
    if (opt === current) option.setAttribute("selected", "selected");
    select.appendChild(option);
  });
  return select;
}

function renderAdminTicketCard(ticket) {
  const card = el("div", { class: "ticket-card" });
  card.appendChild(el("p", { class: "ticket-input-text", text: `"${ticket.input}"` }));

  const badges = el("div", { class: "badge-row" });
  badges.appendChild(badge(`currently: ${ticket.category}`));
  badges.appendChild(priorityBadge(ticket.priority));
  badges.appendChild(badge(`team: ${ticket.team}`));
  card.appendChild(badges);

  card.appendChild(el("p", { class: "reasoning", text: ticket.reasoning }));

  const form = el("div", { class: "correct-form" });
  const categorySelect = selectOf(CATEGORIES, ticket.category);
  const prioritySelect = selectOf(PRIORITIES, ticket.priority);
  const teamSelectEl = selectOf(TEAMS, ticket.team);
  const reasoningInput = el("textarea", { rows: "2", placeholder: "Corrected reasoning..." });
  const submitCorrectionBtn = el("button", { class: "primary-btn", text: "Submit correction" });

  submitCorrectionBtn.addEventListener("click", async () => {
    const reasoning = reasoningInput.value.trim();
    if (!reasoning) {
      reasoningInput.focus();
      return;
    }
    submitCorrectionBtn.disabled = true;
    submitCorrectionBtn.textContent = "Saving...";
    try {
      await api("/route_to_admin", {
        method: "POST",
        body: JSON.stringify({
          ticket_id: ticket.id,
          input_text: ticket.input,
          category: categorySelect.value,
          priority: prioritySelect.value,
          team: teamSelectEl.value,
          reasoning,
        }),
      });
      loadAdminQueue();
    } finally {
      submitCorrectionBtn.disabled = false;
      submitCorrectionBtn.textContent = "Submit correction";
    }
  });

  form.appendChild(categorySelect);
  form.appendChild(prioritySelect);
  form.appendChild(teamSelectEl);
  form.appendChild(reasoningInput);
  form.appendChild(submitCorrectionBtn);
  card.appendChild(form);

  return card;
}

// ---------- metrics ----------

const evalSummary = document.getElementById("eval-summary");
const evalDetails = document.getElementById("eval-details");
const evalRunBtn = document.getElementById("eval-run-btn");
const benchmarkRunBtn = document.getElementById("benchmark-run-btn");
const benchmarkResult = document.getElementById("benchmark-result");
const logSummary = document.getElementById("log-summary");

function renderEvalStats(data) {
  evalSummary.innerHTML = "";
  evalSummary.appendChild(statTile(`${data.passed}/${data.total}`, "passed"));
  evalSummary.appendChild(statTile(`${Math.round((data.passed / data.total) * 100) || 0}%`, "accuracy"));

  evalDetails.innerHTML = "";
  const failures = data.results.filter((r) => !r.passed);
  if (!failures.length) {
    evalDetails.appendChild(el("p", { class: "empty-state", text: "All cases passed." }));
    return;
  }
  failures.forEach((f) => {
    const detail = f.note || `expected ${JSON.stringify(f.expected)}, got ${JSON.stringify(f.actual)}`;
    evalDetails.appendChild(el("div", { class: "eval-failure", text: `"${f.text.slice(0, 70)}" -> ${detail}` }));
  });
}

function statTile(value, label) {
  const tile = el("div", { class: "stat-tile" });
  tile.appendChild(el("div", { class: "stat-value", text: value }));
  tile.appendChild(el("div", { class: "stat-label", text: label }));
  return tile;
}

async function loadMetrics() {
  try {
    const data = await api("/eval/baseline");
    renderEvalStats(data);
  } catch (err) {
    evalSummary.innerHTML = `<p class="empty-state">${err.message}</p>`;
  }

  try {
    const log = await api("/log");
    renderLogSummary(log.log);
  } catch (err) {
    logSummary.innerHTML = `<p class="empty-state">${err.message}</p>`;
  }
}

function renderLogSummary(tickets) {
  logSummary.innerHTML = "";
  const byStatus = {};
  tickets.forEach((t) => { byStatus[t.status] = (byStatus[t.status] || 0) + 1; });
  logSummary.appendChild(statTile(tickets.length, "total tickets"));
  logSummary.appendChild(statTile(byStatus["routed"] || 0, "routed"));
  logSummary.appendChild(statTile(byStatus["flagged_to_admin"] || 0, "flagged"));
  logSummary.appendChild(statTile(byStatus["below_threshold"] || 0, "below threshold"));
}

evalRunBtn.addEventListener("click", async () => {
  evalRunBtn.disabled = true;
  evalRunBtn.textContent = "Running 20 live calls...";
  try {
    const data = await api("/eval/run", { method: "POST" });
    renderEvalStats(data);
  } finally {
    evalRunBtn.disabled = false;
    evalRunBtn.textContent = "Re-run eval now (~20 live calls)";
  }
});

benchmarkRunBtn.addEventListener("click", async () => {
  benchmarkRunBtn.disabled = true;
  benchmarkRunBtn.textContent = "Running...";
  benchmarkResult.innerHTML = "";
  try {
    const data = await api("/benchmark/run", { method: "POST" });
    benchmarkResult.appendChild(statTile(`${data.average_seconds.toFixed(2)}s`, "average per ticket"));
  } finally {
    benchmarkRunBtn.disabled = false;
    benchmarkRunBtn.textContent = "Run benchmark (5 tickets)";
  }
});

// initial load
loadTeamQueue();
