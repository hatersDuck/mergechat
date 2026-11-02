(() => {
  "use strict";

  const TOKEN_KEY = "mergechat.api.token";
  const ACCOUNT_KEY = "mergechat.account";
  const LABELER_KEY = "mergechat.labeler";

  const state = {
    accounts: [],
    accountId: localStorage.getItem(ACCOUNT_KEY) || "",
    chats: [],
    chatsLoadedAccountId: null,
    messages: [],
    messagesOffset: 0,
    messagesLimit: 100,
    messagesUnlabeled: false,
    token: localStorage.getItem(TOKEN_KEY) || "",
    labeler: localStorage.getItem(LABELER_KEY) || "local",
    view: "overview",
    modalAccount: null,
    modalMessage: null,
    statusTimers: new Map(),
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const numberFormatter = new Intl.NumberFormat();
  const dateFormatter = new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (char) => {
      switch (char) {
        case "&": return "&amp;";
        case "<": return "&lt;";
        case ">": return "&gt;";
        case '"': return "&quot;";
        default: return "&#39;";
      }
    });
  }

  function fmtDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : dateFormatter.format(date);
  }

  function fmtNumber(value) {
    if (value == null || Number.isNaN(Number(value))) return "—";
    return numberFormatter.format(Number(value));
  }

  function pct(value) {
    if (value == null || Number.isNaN(Number(value))) return "—";
    return `${(Number(value) * 100).toFixed(1)}%`;
  }

  function truncate(value, limit = 180) {
    const text = String(value == null ? "" : value);
    return text.length > limit ? `${text.slice(0, limit)}...` : text;
  }

  function shortId(value) {
    if (!value) return "—";
    const text = String(value);
    return text.length > 12 ? `${text.slice(0, 8)}...` : text;
  }

  function safeUrl(value) {
    if (!value) return null;
    try {
      const url = new URL(String(value), window.location.href);
      if (["http:", "https:", "max:"].includes(url.protocol)) return String(value);
    } catch (_error) {
      return null;
    }
    return null;
  }

  function statusPill(status) {
    const clean = String(status || "unknown").replace(/[^a-zA-Z0-9_-]/g, "");
    return `<span class="pill pill-${esc(clean)}">${esc(status || "unknown")}</span>`;
  }

  function toneClass(value, target) {
    if (value == null) return "";
    if (target != null) return Number(value) >= target ? "good" : "warn";
    return "";
  }

  async function api(path, options = {}) {
    const opts = { ...options };
    const headers = new Headers(opts.headers || {});
    if (opts.body && !(opts.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (state.token) headers.set("Authorization", `Bearer ${state.token}`);

    let response;
    try {
      response = await fetch(path, { ...opts, headers });
    } catch (error) {
      throw new Error(`API request failed: ${error.message}`);
    }

    if (response.status === 401) {
      openTokenDialog();
    }
    if (response.status === 204) return null;

    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (_error) {
        data = text;
      }
    }

    if (!response.ok) {
      let message = `HTTP ${response.status} ${response.statusText}`;
      if (data && typeof data === "object" && data.detail != null) {
        message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      } else if (typeof data === "string" && data.trim()) {
        message = data;
      }
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function toast(message, type = "info") {
    const container = $("#toasts");
    const node = document.createElement("div");
    node.className = `toast${type === "error" ? " is-error" : type === "ok" ? " is-ok" : ""}`;
    node.textContent = message;
    container.appendChild(node);
    window.setTimeout(() => node.remove(), 6500);
  }

  function setBusy(button, busy, label) {
    if (!button) return;
    if (busy) {
      if (!button.dataset.originalLabel) button.dataset.originalLabel = button.textContent;
      button.disabled = true;
      button.textContent = label || "Working...";
    } else {
      button.disabled = false;
      if (button.dataset.originalLabel) {
        button.textContent = button.dataset.originalLabel;
        delete button.dataset.originalLabel;
      }
    }
  }

  async function action(button, work, successMessage) {
    setBusy(button, true);
    try {
      const result = await work();
      if (successMessage) toast(successMessage, "ok");
      return result;
    } catch (error) {
      toast(error.message || String(error), "error");
      return undefined;
    } finally {
      setBusy(button, false);
    }
  }

  function openModal(title, bodyHtml) {
    $("#modal-title").textContent = title;
    $("#modal-body").innerHTML = bodyHtml;
    const dialog = $("#modal");
    if (!dialog.open) dialog.showModal();
  }

  function closeModal() {
    const dialog = $("#modal");
    if (dialog.open) dialog.close();
  }

  function stopStatusPolling(accountId) {
    const timer = state.statusTimers.get(accountId);
    if (timer) {
      window.clearInterval(timer);
      state.statusTimers.delete(accountId);
    }
  }

  function stopAllStatusPolling() {
    Array.from(state.statusTimers.keys()).forEach(stopStatusPolling);
  }

  /* ------------------------------------------------------------------ */
  /* Accounts                                                           */
  /* ------------------------------------------------------------------ */

  async function loadAccounts(options = {}) {
    const quiet = Boolean(options.quiet);
    try {
      state.accounts = await api("/accounts");
      if (state.accountId && !state.accounts.some((item) => item.id === state.accountId)) {
        state.accountId = "";
        localStorage.removeItem(ACCOUNT_KEY);
      }
      renderAccountOptions();
      renderAccounts();
      renderOverviewAccounts();
      return state.accounts;
    } catch (error) {
      if (!quiet) toast(error.message || String(error), "error");
      if (quiet) throw error;
      return undefined;
    }
  }

  function renderAccountOptions() {
    const select = $("#global-account");
    const current = state.accountId;
    const options = ['<option value="">All accounts</option>'];
    for (const account of state.accounts) {
      options.push(
        `<option value="${esc(account.id)}">${esc(account.display_name)} · ${esc(account.status)}</option>`
      );
    }
    select.innerHTML = options.join("");
    select.value = current;
  }

  function accountCard(account) {
    const selected = account.id === state.accountId;
    const error = account.last_error
      ? `<p class="account-error">${esc(account.last_error)}</p>`
      : "";
    return `
      <article class="account-card${selected ? " is-selected" : ""}" data-id="${esc(account.id)}">
        <div class="account-head">
          <div>
            <div class="account-name">${esc(account.display_name)}</div>
            <div class="account-meta">
              ${statusPill(account.status)}
              <span class="pill pill-muted">${esc(account.platform)}</span>
              ${account.has_session
                ? '<span class="pill pill-ok">session stored</span>'
                : '<span class="pill pill-muted">no session</span>'}
            </div>
          </div>
          <button class="btn btn-sm${selected ? "" : " btn-ghost"}" data-action="use"
                  data-account="${esc(account.id)}" type="button">${selected ? "Selected" : "Use"}</button>
        </div>
        <div class="account-grid">
          <div><span>Account ID</span><strong class="mono">${esc(shortId(account.id))}</strong></div>
          <div><span>Reconnects</span><strong>${fmtNumber(account.reconnect_count)}</strong></div>
          <div><span>Last health check</span><strong>${fmtDate(account.last_health_check)}</strong></div>
          <div><span>Last message</span><strong>${fmtDate(account.last_message_at)}</strong></div>
          <div><span>Created</span><strong>${fmtDate(account.created_at)}</strong></div>
          <div><span>Session</span><strong>${account.has_session ? "encrypted copy present" : "not stored"}</strong></div>
        </div>
        ${error}
        <div class="account-actions">
          <button class="btn btn-primary btn-sm" data-action="connect" data-account="${esc(account.id)}" type="button">Connect</button>
          <button class="btn btn-sm" data-action="status" data-account="${esc(account.id)}" type="button">Status</button>
          <button class="btn btn-sm" data-action="health" data-account="${esc(account.id)}" type="button">Health</button>
          <button class="btn btn-sm" data-action="start-listener" data-account="${esc(account.id)}" type="button">Start listener</button>
          <button class="btn btn-sm" data-action="stop-listener" data-account="${esc(account.id)}" type="button">Stop listener</button>
          <button class="btn btn-sm" data-action="disconnect" data-account="${esc(account.id)}" type="button">Disconnect</button>
          <button class="btn btn-sm btn-danger" data-action="revoke-session" data-account="${esc(account.id)}" type="button">Revoke session</button>
          <button class="btn btn-sm btn-danger" data-action="delete-account" data-account="${esc(account.id)}" type="button">Delete</button>
        </div>
      </article>
    `;
  }

  function renderAccounts() {
    const container = $("#accounts-list");
    if (!container) return;
    if (!state.accounts.length) {
      container.innerHTML = '<div class="empty">No accounts yet. Create one above, then connect it to Max.</div>';
      return;
    }
    container.innerHTML = state.accounts.map(accountCard).join("");
  }

  function renderOverviewAccounts() {
    const container = $("#overview-accounts");
    if (!container) return;
    if (!state.accounts.length) {
      container.innerHTML = '<div class="empty">No accounts yet. Open Accounts to create one.</div>';
      return;
    }
    container.innerHTML = `<div class="summary-list">${state.accounts
      .map((account) => `
        <button class="summary-row" data-goto="accounts" type="button">
          <span class="summary-main">
            <strong>${esc(account.display_name)}</strong>
            <small>${esc(account.platform)} · ${account.has_session ? "session stored" : "no session"}</small>
          </span>
          <span class="summary-side">${statusPill(account.status)}</span>
        </button>
      `)
      .join("")}</div>`;
  }

  function selectAccount(accountId) {
    state.accountId = accountId;
    state.messagesOffset = 0;
    state.chatsLoadedAccountId = null;
    if (accountId) localStorage.setItem(ACCOUNT_KEY, accountId);
    else localStorage.removeItem(ACCOUNT_KEY);
    renderAccountOptions();
    renderAccounts();
    updateChatSaveState();
    if (state.view === "messages") {
      loadMessages();
    } else if (state.view === "chats") {
      loadChats();
    } else if (state.view === "classification") {
      loadClassificationView();
    } else if (state.view === "overview") {
      loadOverview();
    }
  }

  function statusPanelHtml(accountId, status) {
    const link = status.qr_link && !status.connected ? safeUrl(status.qr_link) : null;
    const rawLink = status.qr_link && !status.connected ? String(status.qr_link) : null;
    let qrBlock = "";
    if (rawLink) {
      qrBlock = `
        <div class="qr-link-box">${esc(rawLink)}</div>
        <div class="qr-actions">
          ${link ? `<a class="btn btn-primary btn-sm" href="${esc(link)}" target="_blank" rel="noopener">Open QR link</a>` : ""}
          <button class="btn btn-sm" type="button" data-copy="${esc(rawLink)}">Copy link</button>
        </div>
        <p class="muted">Open this link in the Max app and confirm the login. This panel refreshes automatically.</p>
      `;
    } else if (!status.connected) {
      qrBlock = '<p class="muted">No QR link yet. Max may still be preparing the session, or the stored session is being restored. Use Refresh status to poll again.</p>';
    }

    const error = status.error
      ? `<div class="notice is-error">${esc(status.error)}</div>`
      : "";

    return `
      <div class="classification-top" style="margin-bottom:12px">
        ${status.connected ? '<span class="pill pill-connected">connected</span>' : statusPill(status.status)}
        <span class="muted">last update ${fmtDate(new Date().toISOString())}</span>
      </div>
      <div class="status-summary">
        <div><span>Account</span><strong class="mono">${esc(accountId)}</strong></div>
        <div><span>Status</span><strong>${esc(status.status)}</strong></div>
        <div><span>Connected</span><strong>${status.connected ? "yes" : "no"}</strong></div>
        <div><span>Reconnects</span><strong>${fmtNumber(status.reconnect_count)}</strong></div>
        <div><span>Last message</span><strong>${fmtDate(status.last_message_at)}</strong></div>
        <div><span>Health</span><strong>${status.connected ? "ok" : "not connected"}</strong></div>
      </div>
      ${qrBlock}
      ${error}
      <div class="qr-actions">
        <button class="btn btn-sm" type="button" data-action="poll-status" data-account="${esc(accountId)}">Refresh status</button>
      </div>
    `;
  }

  function openStatusModal(accountId, status) {
    stopAllStatusPolling();
    state.modalAccount = accountId;
    state.modalMessage = null;
    openModal("Account status", `<div id="status-live">${statusPanelHtml(accountId, status)}</div>`);
    if (!status.connected) startStatusPolling(accountId);
  }

  function openQrModal(accountId, qrLink, status) {
    const payload = {
      status: status || "pending_auth",
      connected: false,
      qr_link: qrLink || null,
      reconnect_count: 0,
      last_message_at: null,
      error: null,
    };
    openStatusModal(accountId, payload);
  }

  async function pollStatusOnce(accountId) {
    const status = await api(`/accounts/${accountId}/status`);
    const live = $("#status-live");
    if (state.modalAccount === accountId && live) {
      live.innerHTML = statusPanelHtml(accountId, status);
    }
    if (status.connected) {
      stopStatusPolling(accountId);
      await loadAccounts({ quiet: true });
      if (state.modalAccount === accountId) {
        state.modalAccount = null;
        closeModal();
      }
      toast("Max account connected.", "ok");
    } else if (status.status === "error") {
      stopStatusPolling(accountId);
    }
    return status;
  }

  function startStatusPolling(accountId) {
    stopStatusPolling(accountId);
    let attempts = 0;
    let failures = 0;
    const timer = window.setInterval(async () => {
      attempts += 1;
      if (state.modalAccount !== accountId) {
        stopStatusPolling(accountId);
        return;
      }
      try {
        await pollStatusOnce(accountId);
        failures = 0;
      } catch (error) {
        failures += 1;
        if (failures >= 3) {
          stopStatusPolling(accountId);
          toast(error.message || String(error), "error");
        }
      }
      if (attempts >= 150) stopStatusPolling(accountId);
    }, 2000);
    state.statusTimers.set(accountId, timer);
  }

  async function connectAccount(accountId, button, listener) {
    setBusy(button, true, listener ? "Starting..." : "Connecting...");
    try {
      const path = listener
        ? `/accounts/${accountId}/listener/start`
        : `/accounts/${accountId}/connect`;
      const result = await api(path, { method: "POST" });
      await loadAccounts({ quiet: true });
      if (result.connected) {
        toast(listener ? "Listener started." : "Account connected.", "ok");
        return;
      }
      openQrModal(accountId, result.qr_link, result.status);
    } catch (error) {
      toast(error.message || String(error), "error");
    } finally {
      setBusy(button, false);
    }
  }

  async function handleAccountAction(button) {
    const accountId = button.dataset.account;
    const actionName = button.dataset.action;

    if (actionName === "use") {
      selectAccount(accountId);
      return;
    }
    if (actionName === "connect") {
      await connectAccount(accountId, button, false);
      return;
    }
    if (actionName === "start-listener") {
      await connectAccount(accountId, button, true);
      return;
    }
    if (actionName === "status") {
      setBusy(button, true);
      try {
        const status = await api(`/accounts/${accountId}/status`);
        openStatusModal(accountId, status);
      } catch (error) {
        toast(error.message || String(error), "error");
      } finally {
        setBusy(button, false);
      }
      return;
    }
    if (actionName === "health") {
      setBusy(button, true);
      try {
        const health = await api(`/accounts/${accountId}/health`);
        state.modalAccount = null;
        state.modalMessage = null;
        openModal("Account health", `
          <div class="status-summary">
            <div><span>Account</span><strong class="mono">${esc(accountId)}</strong></div>
            <div><span>Status</span><strong>${esc(health.status)}</strong></div>
            <div><span>Connected</span><strong>${health.connected ? "yes" : "no"}</strong></div>
            <div><span>Reconnects</span><strong>${fmtNumber(health.reconnect_count)}</strong></div>
            <div><span>Last event</span><strong>${fmtDate(health.last_event_at)}</strong></div>
            <div><span>Error</span><strong>${esc(health.error || "none")}</strong></div>
          </div>
        `);
      } catch (error) {
        toast(error.message || String(error), "error");
      } finally {
        setBusy(button, false);
      }
      return;
    }
    if (actionName === "stop-listener") {
      await action(button, async () => {
        await api(`/accounts/${accountId}/listener/stop`, { method: "POST" });
        await loadAccounts({ quiet: true });
      }, "Listener stopped.");
      return;
    }
    if (actionName === "disconnect") {
      await action(button, async () => {
        await api(`/accounts/${accountId}/disconnect`, { method: "POST" });
        await loadAccounts({ quiet: true });
      }, "Account disconnected.");
      return;
    }
    if (actionName === "revoke-session") {
      if (!window.confirm("Revoke the encrypted Max session for this account?")) return;
      await action(button, async () => {
        await api(`/accounts/${accountId}/session`, { method: "DELETE" });
        await loadAccounts({ quiet: true });
      }, "Session revoked.");
      return;
    }
    if (actionName === "delete-account") {
      if (!window.confirm("Delete this account and all stored data? This cannot be undone.")) return;
      await action(button, async () => {
        await api(`/accounts/${accountId}`, { method: "DELETE" });
        if (state.accountId === accountId) selectAccount("");
        await loadAccounts({ quiet: true });
      }, "Account deleted.");
      if (state.view === "chats" || state.view === "messages") {
        if (state.view === "chats") loadChats();
        else loadMessages();
      }
    }
  }

  /* ------------------------------------------------------------------ */
  /* Chats                                                              */
  /* ------------------------------------------------------------------ */

  function currentAccount() {
    return state.accounts.find((account) => account.id === state.accountId) || null;
  }

  async function loadChats() {
    const container = $("#chats-list");
    const label = $("#chats-account-label");
    if (!state.accountId) {
      state.chatsLoadedAccountId = null;
      updateChatSaveState();
      if (label) label.textContent = "Choose a specific account in the top bar to manage chats.";
      if (container) container.innerHTML = '<div class="empty">No account selected.</div>';
      $("#chats-selected-count").textContent = "0 selected";
      return;
    }
    const accountId = state.accountId;
    state.chatsLoadedAccountId = null;
    updateChatSaveState();
    const account = currentAccount();
    if (label) {
      label.textContent = account
        ? `Monitoring chats for ${account.display_name} (${account.status}).`
        : `Monitoring chats for account ${shortId(accountId)}.`;
    }
    try {
      const chats = await api(`/accounts/${accountId}/chats`);
      if (state.accountId !== accountId) return;
      state.chats = chats;
      state.chatsLoadedAccountId = accountId;
      renderChats();
    } catch (error) {
      if (state.accountId !== accountId) return;
      state.chats = [];
      state.chatsLoadedAccountId = null;
      updateChatSaveState();
      if (container) container.innerHTML = `<div class="notice is-error">${esc(error.message)}</div>`;
      $("#chats-selected-count").textContent = "0 selected";
    }
  }

  function chatRow(chat) {
    const title = chat.title || `Chat ${shortId(chat.external_chat_id)}`;
    const search = `${title} ${chat.external_chat_id}`.toLowerCase();
    return `
      <label class="chat-row" data-search="${esc(search)}">
        <input type="checkbox" name="chat-select" value="${esc(chat.external_chat_id)}"${chat.selected ? " checked" : ""}>
        <span class="chat-main">
          <span class="chat-title">${esc(title)}</span>
          <span class="chat-sub">${esc(chat.external_chat_id)} · ${esc(chat.chat_type)} · ${fmtNumber(chat.participants_count)} participants</span>
          <span class="chat-badges">
            ${chat.selected ? '<span class="pill pill-connected">selected</span>' : '<span class="pill pill-muted">not selected</span>'}
            ${chat.messages_count ? `<span class="pill pill-muted">${fmtNumber(chat.messages_count)} messages</span>` : ""}
          </span>
        </span>
      </label>
    `;
  }

  function renderChats() {
    const container = $("#chats-list");
    if (!container) return;
    if (!state.accountId) {
      container.innerHTML = '<div class="empty">Choose a specific account in the top bar.</div>';
      $("#chats-selected-count").textContent = "0 selected";
      updateChatSaveState();
      return;
    }
    if (!state.chats.length) {
      container.innerHTML = '<div class="empty">No chats stored. Press Refresh from Max after connecting the account.</div>';
      $("#chats-selected-count").textContent = "0 selected";
      updateChatSaveState();
      return;
    }
    container.innerHTML = state.chats.map(chatRow).join("");
    applyChatFilter();
    updateChatCount();
    updateChatSaveState();
  }

  function applyChatFilter() {
    const query = ($("#chat-search").value || "").trim().toLowerCase();
    $$(".chat-row", $("#chats-list")).forEach((row) => {
      row.classList.toggle("chat-search-hidden", Boolean(query) && !row.dataset.search.includes(query));
    });
  }

  function updateChatCount() {
    const selected = $$('input[name="chat-select"]:checked', $("#chats-list")).length;
    $("#chats-selected-count").textContent = `${selected} selected`;
  }

  function updateChatSaveState() {
    const button = $("#chats-save");
    if (!button) return;
    button.disabled = !(
      state.accountId
      && state.chatsLoadedAccountId === state.accountId
      && state.chats.length > 0
    );
  }

  async function saveChatSelection(button) {
    const accountId = state.accountId;
    if (!accountId) {
      toast("Choose an account first.", "error");
      return;
    }
    if (state.chatsLoadedAccountId !== accountId || !state.chats.length) {
      toast("Wait for this account's chats to finish loading first.", "error");
      return;
    }
    const ids = $$('input[name="chat-select"]:checked', $("#chats-list")).map((input) => input.value);
    await action(button, async () => {
      const result = await api(`/accounts/${accountId}/chats/selection`, {
        method: "POST",
        body: JSON.stringify({ chat_ids: ids }),
      });
      if (state.accountId !== accountId) return;
      state.chats = result.chats;
      renderChats();
    }, `Saved ${ids.length} selected chat(s).`);
  }

  /* ------------------------------------------------------------------ */
  /* Messages                                                           */
  /* ------------------------------------------------------------------ */

  async function loadMessages() {
    const container = $("#messages-table");
    if (!container) return;
    const params = new URLSearchParams();
    if (state.accountId) params.set("account_id", state.accountId);
    if (state.messagesUnlabeled) params.set("unlabeled", "true");
    params.set("limit", String(state.messagesLimit));
    params.set("offset", String(state.messagesOffset));
    try {
      state.messages = await api(`/messages?${params.toString()}`);
      renderMessages();
    } catch (error) {
      container.innerHTML = `<div class="notice is-error">${esc(error.message)}</div>`;
      $("#messages-count").textContent = "";
    }
  }

  function renderMessages() {
    const container = $("#messages-table");
    if (!container) return;
    $("#messages-count").textContent = `${state.messages.length} message(s) loaded`
      + (state.accountId ? " for the selected account" : " across all accounts");
    $("#msg-page").textContent = `Page ${Math.floor(state.messagesOffset / state.messagesLimit) + 1}`;
    $("#msg-prev").disabled = state.messagesOffset === 0;
    $("#msg-next").disabled = state.messages.length < state.messagesLimit;

    if (!state.messages.length) {
      container.innerHTML = '<div class="empty">No messages found for these filters.</div>';
      return;
    }

    const rows = state.messages.map((message) => {
      const text = message.text ? truncate(message.text, 240) : "No text (attachment-only message)";
      const attachments = Array.isArray(message.attachments) ? message.attachments.length : 0;
      return `
        <tr>
          <td class="nowrap">${fmtDate(message.timestamp)}</td>
          <td>${esc(message.author_name || message.author_external_id || "—")}</td>
          <td class="mono">${esc(message.external_chat_id)}</td>
          <td class="msg-text${message.text ? "" : " is-empty"}">${esc(text)}${attachments ? ` <span class="chip">${attachments} attachment(s)</span>` : ""}</td>
          <td>${statusPill(message.processing_status)}</td>
          <td class="actions-cell">
            <button class="btn btn-sm" data-action="open-message" data-message="${esc(message.id)}" type="button">Open</button>
          </td>
        </tr>
      `;
    }).join("");

    container.innerHTML = `
      <table class="table">
        <thead>
          <tr>
            <th>Received</th>
            <th>Author</th>
            <th>Chat</th>
            <th>Text</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  function classificationHtml(classification, loadError) {
    if (loadError) {
      return `<div class="notice is-error">Could not load classification: ${esc(loadError)}</div>`;
    }
    if (!classification) {
      return '<div class="empty">No classification stored for this message yet.</div>';
    }
    const attributes = classification.attributes || {};
    const usage = classification.usage || {};
    const keywords = Array.isArray(classification.keywords) ? classification.keywords : [];
    const confidence = classification.confidence == null ? 0 : Math.max(0, Math.min(1, Number(classification.confidence)));
    const extractionNotes = attributes.extraction_notes;
    const orderLabel = classification.is_order === true
      ? '<span class="pill pill-order">order</span>'
      : classification.is_order === false
        ? '<span class="pill pill-not_order">not order</span>'
        : '<span class="pill pill-muted">unknown</span>';

    const attributeRows = Object.entries(attributes)
      .filter(([key]) => key !== "extraction_notes")
      .slice(0, 16)
      .map(([key, value]) => {
        const display = typeof value === "object" && value !== null ? JSON.stringify(value) : value;
        return `<div><span>${esc(key)}</span><strong>${esc(display == null ? "—" : display)}</strong></div>`;
      })
      .join("");

    return `
      <div class="classification-card">
        <div class="classification-top">
          ${statusPill(classification.status)}
          ${orderLabel}
          <span class="muted">confidence ${classification.confidence == null ? "—" : pct(classification.confidence)}</span>
        </div>
        <div class="confidence-track"><div class="confidence-fill" style="width:${(confidence * 100).toFixed(1)}%"></div></div>
        <div class="kv-grid">
          <div><span>Model</span><strong>${esc(classification.model || "—")}</strong></div>
          <div><span>Prompt</span><strong>${esc(classification.prompt_version)}</strong></div>
          <div><span>Latency</span><strong>${classification.latency_ms == null ? "—" : `${Number(classification.latency_ms).toFixed(0)} ms`}</strong></div>
          <div><span>Created</span><strong>${fmtDate(classification.created_at)}</strong></div>
          <div><span>Provider</span><strong>${esc(classification.provider)}</strong></div>
          <div><span>Confidence</span><strong>${classification.confidence == null ? "—" : Number(classification.confidence).toFixed(4)}</strong></div>
        </div>
        ${keywords.length ? `<div class="chips">${keywords.map((word) => `<span class="chip">${esc(word)}</span>`).join("")}</div>` : ""}
        ${attributeRows ? `<div class="kv-grid">${attributeRows}</div>` : ""}
        ${extractionNotes ? `<p class="muted">${esc(extractionNotes)}</p>` : ""}
        ${classification.error ? `<div class="notice is-error">${esc(classification.error)}</div>` : ""}
        <details>
          <summary>Attributes JSON</summary>
          <pre class="json">${esc(JSON.stringify(attributes, null, 2))}</pre>
        </details>
        <details>
          <summary>Answers JSON</summary>
          <pre class="json">${esc(JSON.stringify(classification.answers || {}, null, 2))}</pre>
        </details>
        <details>
          <summary>Usage JSON</summary>
          <pre class="json">${esc(JSON.stringify(usage, null, 2))}</pre>
        </details>
      </div>
    `;
  }

  function labelHistoryHtml(labels) {
    if (!labels.length) return '<div class="empty">No manual labels yet.</div>';
    return `<div class="label-history">${labels.map((label) => `
      <div class="label-history-row">
        <span>${statusPill(label.label)} <small>by ${esc(label.labeler)}</small></span>
        <small>${fmtDate(label.created_at)}</small>
      </div>
      ${label.comment ? `<div class="label-history-row"><span>${esc(label.comment)}</span></div>` : ""}
    `).join("")}</div>`;
  }

  function messageDetailHtml(message, labels, classification, loadError) {
    const currentLabel = labels.find((label) => label.labeler === state.labeler) || null;
    const attachments = Array.isArray(message.attachments) ? message.attachments : [];
    const checked = (value) => currentLabel && currentLabel.label === value ? " checked" : "";
    const comment = currentLabel && currentLabel.comment ? currentLabel.comment : "";
    return `
      <div class="detail-meta">
        <div><span>Message ID</span><strong class="mono">${esc(message.id)}</strong></div>
        <div><span>External ID</span><strong class="mono">${esc(message.external_message_id)}</strong></div>
        <div><span>Chat</span><strong class="mono">${esc(message.external_chat_id)}</strong></div>
        <div><span>Author</span><strong>${esc(message.author_name || message.author_external_id || "—")}</strong></div>
        <div><span>Sent</span><strong>${fmtDate(message.timestamp)}</strong></div>
        <div><span>Received</span><strong>${fmtDate(message.received_at)}</strong></div>
        <div><span>Status</span><strong>${statusPill(message.processing_status)}</strong></div>
        <div><span>Attachments</span><strong>${attachments.length}</strong></div>
      </div>
      <pre class="message-text${message.text ? "" : " is-empty"}">${message.text ? esc(message.text) : "No text (attachment-only message)."}</pre>
      ${message.processing_error ? `<div class="notice is-error">${esc(message.processing_error)}</div>` : ""}

      <div class="section-title">
        <h4>Classification</h4>
        <button class="btn btn-sm" id="classify-btn" data-action="classify" data-message="${esc(message.id)}" type="button">Classify now</button>
      </div>
      ${classificationHtml(classification, loadError)}

      <div class="section-title"><h4>Manual label</h4></div>
      <form id="label-form" class="form" data-message="${esc(message.id)}">
        <div class="segmented">
          <label><input type="radio" name="label" value="order"${checked("order")}> Order</label>
          <label><input type="radio" name="label" value="not_order"${checked("not_order")}> Not an order</label>
          <label><input type="radio" name="label" value="uncertain"${checked("uncertain")}> Uncertain</label>
        </div>
        <div class="kv-grid">
          <label class="field">
            <span>Labeler</span>
            <input id="labeler-input" name="labeler" type="text" maxlength="128" value="${esc(state.labeler)}">
          </label>
          <label class="field">
            <span>Comment</span>
            <input name="comment" type="text" maxlength="1000" placeholder="optional" value="${esc(comment)}">
          </label>
        </div>
        <div class="form-foot">
          <button class="btn btn-primary" type="submit">Save label</button>
          <span class="muted">Saving replaces your previous label for this message.</span>
        </div>
      </form>

      <div class="section-title"><h4>Label history</h4></div>
      ${labelHistoryHtml(labels)}

      ${attachments.length ? `
        <div class="section-title"><h4>Attachments</h4></div>
        <pre class="json">${esc(JSON.stringify(attachments, null, 2))}</pre>
      ` : ""}
    `;
  }

  async function openMessage(messageId) {
    stopAllStatusPolling();
    state.modalAccount = null;
    state.modalMessage = messageId;
    openModal(`Message ${shortId(messageId)}`, '<div class="empty">Loading message...</div>');
    try {
      const [message, labels] = await Promise.all([
        api(`/messages/${messageId}`),
        api(`/messages/${messageId}/label`),
      ]);
      let classification = null;
      let classificationError = null;
      try {
        classification = await api(`/messages/${messageId}/classification`);
      } catch (error) {
        if (error.status !== 404) classificationError = error.message;
      }
      if (state.modalMessage !== messageId) return;
      $("#modal-body").innerHTML = messageDetailHtml(message, labels, classification, classificationError);
    } catch (error) {
      if (state.modalMessage !== messageId) return;
      $("#modal-body").innerHTML = `<div class="notice is-error">${esc(error.message)}</div>`;
    }
  }

  async function classifyMessage(messageId, button) {
    setBusy(button, true, "Classifying...");
    try {
      const record = await api(`/messages/${messageId}/classify`, { method: "POST" });
      toast(
        `Classified: ${record.is_order ? "order" : "not order"} at ${pct(record.confidence)} confidence.`,
        "ok"
      );
      await openMessage(messageId);
      if (state.view === "messages") await loadMessages();
      else if (state.view === "overview") await loadOverview();
      else if (state.view === "classification") await loadClassificationView();
    } catch (error) {
      toast(error.message || String(error), "error");
    } finally {
      setBusy(button, false);
    }
  }

  async function submitLabel(form) {
    const messageId = form.dataset.message;
    const data = new FormData(form);
    const label = data.get("label");
    if (!label) {
      toast("Choose a label first.", "error");
      return;
    }
    const labeler = String(data.get("labeler") || "").trim() || "local";
    const comment = String(data.get("comment") || "").trim() || null;
    state.labeler = labeler;
    localStorage.setItem(LABELER_KEY, labeler);
    const button = form.querySelector('button[type="submit"]');
    setBusy(button, true, "Saving...");
    try {
      await api(`/messages/${messageId}/label`, {
        method: "POST",
        body: JSON.stringify({ label, labeler, comment }),
      });
      toast("Label saved.", "ok");
      await openMessage(messageId);
      if (state.view === "messages") await loadMessages();
      else if (state.view === "overview") await loadOverview();
      else if (state.view === "classification") await loadClassificationView();
    } catch (error) {
      toast(error.message || String(error), "error");
    } finally {
      setBusy(button, false);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Classification, metrics and export                                 */
  /* ------------------------------------------------------------------ */

  function metricCard(label, value, hint, tone = "") {
    return `
      <div class="metric">
        <div class="metric-label">${esc(label)}</div>
        <div class="metric-value${tone ? ` ${tone}` : ""}">${esc(value)}</div>
        ${hint ? `<div class="metric-hint">${esc(hint)}</div>` : ""}
      </div>
    `;
  }

  function metricsHtml(metrics) {
    const quality = metrics.quality || {};
    return [
      metricCard("Messages", fmtNumber(metrics.messages), "stored and not deleted"),
      metricCard("Classified", fmtNumber(metrics.classified_messages), "JEV completed"),
      metricCard("Pending / failed", fmtNumber(metrics.pending_messages), "available for a run"),
      metricCard("Manual labels", fmtNumber(metrics.manual_labels), "review coverage"),
      metricCard("Order predictions", fmtNumber(metrics.order_predictions), "is_order = true"),
      metricCard(
        "Avg JEV latency",
        metrics.average_jev_latency_ms == null ? "—" : `${Number(metrics.average_jev_latency_ms).toFixed(0)} ms`,
        "per request"
      ),
      metricCard("Precision", pct(quality.precision), "target 90%", toneClass(quality.precision, 0.9)),
      metricCard("Recall", pct(quality.recall), "target 80%", toneClass(quality.recall, 0.8)),
    ].join("");
  }

  function qualityHtml(quality) {
    if (!quality || !quality.labelled_messages) {
      return '<div class="empty">No comparable labels yet. Label order and not-order messages to compute precision and recall.</div>';
    }
    const precision = quality.precision;
    const recall = quality.recall;
    const bar = (value, target) => {
      if (value == null) return "";
      const width = Math.max(0, Math.min(1, Number(value))) * 100;
      return `<div class="quality-track"><div class="quality-fill${Number(value) < target ? " is-below" : ""}" style="width:${width.toFixed(1)}%"></div></div>`;
    };
    return `
      <div class="quality-row">
        <div class="quality-head"><span>Precision <span class="quality-target">(target 90%)</span></span><strong>${pct(precision)}</strong></div>
        ${bar(precision, 0.9)}
      </div>
      <div class="quality-row">
        <div class="quality-head"><span>Recall <span class="quality-target">(target 80%)</span></span><strong>${pct(recall)}</strong></div>
        ${bar(recall, 0.8)}
      </div>
      <div class="confusion">
        <div><span>TP</span><strong>${fmtNumber(quality.true_positives)}</strong></div>
        <div><span>FP</span><strong>${fmtNumber(quality.false_positives)}</strong></div>
        <div><span>FN</span><strong>${fmtNumber(quality.false_negatives)}</strong></div>
        <div><span>TN</span><strong>${fmtNumber(quality.true_negatives)}</strong></div>
      </div>
      <p class="muted">${fmtNumber(quality.labelled_messages)} labelled message(s) compared against the latest prediction. Uncertain labels are excluded.</p>
    `;
  }

  async function fetchMetrics() {
    const params = new URLSearchParams();
    if (state.accountId) params.set("account_id", state.accountId);
    return api(`/classifications/metrics${params.size ? `?${params.toString()}` : ""}`);
  }

  async function loadOverview() {
    try {
      const [metrics, messages] = await Promise.all([
        fetchMetrics(),
        api(`/messages?limit=8${state.accountId ? `&account_id=${encodeURIComponent(state.accountId)}` : ""}`),
      ]);
      $("#overview-metrics").innerHTML = metricsHtml(metrics);
      renderOverviewMessages(messages);
      renderOverviewAccounts();
    } catch (error) {
      $("#overview-metrics").innerHTML = `<div class="notice is-error">${esc(error.message)}</div>`;
    }
  }

  function renderOverviewMessages(messages) {
    const container = $("#overview-messages");
    if (!container) return;
    if (!messages.length) {
      container.innerHTML = '<div class="empty">No stored messages yet.</div>';
      return;
    }
    container.innerHTML = `<div class="recent-list">${messages.map((message) => `
      <button class="recent-row" data-action="open-message" data-message="${esc(message.id)}" type="button">
        <span class="recent-main">
          <span class="recent-text">${esc(message.text ? truncate(message.text, 150) : "No text (attachment-only message)")}</span>
          <span class="recent-sub">${esc(message.author_name || message.author_external_id || "unknown")} · ${fmtDate(message.timestamp)}</span>
        </span>
        ${statusPill(message.processing_status)}
      </button>
    `).join("")}</div>`;
  }

  async function loadClassificationView() {
    try {
      const metrics = await fetchMetrics();
      $("#classification-metrics").innerHTML = metricsHtml(metrics);
      $("#quality-panel").innerHTML = qualityHtml(metrics.quality || {});
    } catch (error) {
      $("#classification-metrics").innerHTML = `<div class="notice is-error">${esc(error.message)}</div>`;
    }
  }

  async function runClassification(button) {
    const limit = Number($("#run-limit").value || 50);
    const box = $("#run-result");
    setBusy(button, true, "Running...");
    try {
      const payload = { limit };
      if (state.accountId) payload.account_id = state.accountId;
      const result = await api("/classifications/run", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      box.hidden = false;
      box.className = result.failed ? "notice" : "notice is-ok";
      box.textContent = `Run ${result.run_id || "—"}: ${result.processed} processed, ${result.failed} failed.`;
      toast(`Classification finished: ${result.processed} processed, ${result.failed} failed.`, result.failed ? "error" : "ok");
      await loadClassificationView();
    } catch (error) {
      box.hidden = false;
      box.className = "notice is-error";
      box.textContent = error.message || String(error);
      toast(error.message || String(error), "error");
    } finally {
      setBusy(button, false);
    }
  }

  async function fetchExportRows() {
    const limit = Number($("#export-limit").value || 500);
    const params = new URLSearchParams({ limit: String(limit) });
    if (state.accountId) params.set("account_id", state.accountId);
    return api(`/classifications/export?${params.toString()}`);
  }

  async function previewExport(button) {
    const resultBox = $("#export-result");
    const table = $("#export-table");
    setBusy(button, true, "Loading...");
    try {
      const rows = await fetchExportRows();
      resultBox.hidden = false;
      resultBox.className = "notice";
      resultBox.textContent = `${rows.length} export row(s) loaded. Each row contains the message and one classification record.`;
      if (!rows.length) {
        table.innerHTML = '<div class="empty">No classification rows found.</div>';
        return;
      }
      table.innerHTML = `
        <table class="table">
          <thead>
            <tr>
              <th>Classified</th>
              <th>Message</th>
              <th>Prediction</th>
              <th>Confidence</th>
              <th>Model</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map((row) => `
              <tr>
                <td class="nowrap">${fmtDate(row.classification.created_at)}</td>
                <td class="msg-text">${esc(row.message.text ? truncate(row.message.text, 220) : "No text")}</td>
                <td>${row.classification.is_order === true
                  ? '<span class="pill pill-order">order</span>'
                  : row.classification.is_order === false
                    ? '<span class="pill pill-not_order">not order</span>'
                    : statusPill(row.classification.status)}</td>
                <td>${pct(row.classification.confidence)}</td>
                <td class="mono">${esc(row.classification.model || "—")}</td>
                <td class="nowrap">${row.classification.latency_ms == null ? "—" : `${Number(row.classification.latency_ms).toFixed(0)} ms`}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;
    } catch (error) {
      resultBox.hidden = false;
      resultBox.className = "notice is-error";
      resultBox.textContent = error.message || String(error);
      toast(error.message || String(error), "error");
    } finally {
      setBusy(button, false);
    }
  }

  async function downloadExport(button) {
    setBusy(button, true, "Preparing...");
    try {
      const rows = await fetchExportRows();
      const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      const body = rows.map((row) => JSON.stringify(row)).join("\n");
      const blob = new Blob([body ? `${body}\n` : ""], { type: "application/x-ndjson" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `mergechat-export-${stamp}.jsonl`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 2000);
      toast(`Downloaded ${rows.length} row(s).`, "ok");
    } catch (error) {
      toast(error.message || String(error), "error");
    } finally {
      setBusy(button, false);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Labels import                                                      */
  /* ------------------------------------------------------------------ */

  const EXAMPLE_LABELS = {
    labels: [
      {
        message_id: "<message uuid>",
        label: "order",
        labeler: "me",
        comment: "optional note",
      },
    ],
  };

  async function importLabels(form) {
    const resultBox = $("#labels-result");
    const raw = $("#labels-json").value.trim();
    if (!raw) {
      toast("Paste a JSON payload first.", "error");
      return;
    }
    let payload;
    try {
      payload = JSON.parse(raw);
    } catch (error) {
      toast(`Invalid JSON: ${error.message}`, "error");
      return;
    }
    if (!payload || !Array.isArray(payload.labels)) {
      toast('Payload must contain a "labels" array.', "error");
      return;
    }
    const button = form.querySelector('button[type="submit"]');
    setBusy(button, true, "Importing...");
    try {
      const result = await api("/labels/import", {
        method: "POST",
        body: JSON.stringify({ labels: payload.labels }),
      });
      resultBox.hidden = false;
      resultBox.className = result.skipped ? "notice" : "notice is-ok";
      resultBox.textContent = `Imported ${result.imported} label(s), skipped ${result.skipped}.`;
      toast(`Imported ${result.imported} label(s).`, "ok");
      if (state.view === "overview") await loadOverview();
    } catch (error) {
      resultBox.hidden = false;
      resultBox.className = "notice is-error";
      resultBox.textContent = error.message || String(error);
      toast(error.message || String(error), "error");
    } finally {
      setBusy(button, false);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Token, health and navigation                                       */
  /* ------------------------------------------------------------------ */

  function openTokenDialog() {
    const dialog = $("#token-dialog");
    $("#token-input").value = state.token;
    if (!dialog.open) dialog.showModal();
  }

  async function afterTokenChange() {
    checkHealth();
    try {
      await loadAccounts({ quiet: true });
    } catch (error) {
      toast(error.message || String(error), "error");
    }
    refreshCurrentView();
  }

  async function saveToken() {
    const value = $("#token-input").value.trim();
    state.token = value;
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
    $("#token-dialog").close();
    toast(value ? "API token saved." : "API token cleared.", "ok");
    await afterTokenChange();
  }

  async function clearToken() {
    state.token = "";
    localStorage.removeItem(TOKEN_KEY);
    $("#token-input").value = "";
    $("#token-dialog").close();
    toast("API token cleared.", "ok");
    await afterTokenChange();
  }

  async function checkHealth() {
    const pill = $("#api-health");
    try {
      await api("/healthz");
      pill.className = "pill pill-ok";
      pill.textContent = "API: online";
    } catch (_error) {
      pill.className = "pill pill-error";
      pill.textContent = "API: offline";
    }
  }

  function navigate(view) {
    if (!["overview", "accounts", "chats", "messages", "classification", "labels"].includes(view)) {
      view = "overview";
    }
    closeModal();
    stopAllStatusPolling();
    state.modalAccount = null;
    state.modalMessage = null;
    state.view = view;
    $$(".view").forEach((section) => {
      section.hidden = section.dataset.view !== view;
    });
    $$(".nav-item").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.nav === view);
    });

    if (view === "overview") loadOverview();
    else if (view === "accounts") {
      renderAccounts();
      loadAccounts({ quiet: true }).catch((error) => toast(error.message, "error"));
    } else if (view === "chats") loadChats();
    else if (view === "messages") loadMessages();
    else if (view === "classification") loadClassificationView();
  }

  function refreshCurrentView() {
    if (state.view === "overview") loadOverview();
    else if (state.view === "accounts") loadAccounts().catch(() => {});
    else if (state.view === "chats") loadChats();
    else if (state.view === "messages") loadMessages();
    else if (state.view === "classification") loadClassificationView();
  }

  function bindEvents() {
    $$(".nav-item").forEach((button) => {
      button.addEventListener("click", () => navigate(button.dataset.nav));
    });

    $("#global-account").addEventListener("change", (event) => {
      selectAccount(event.target.value);
    });

    document.addEventListener("click", (event) => {
      const goto = event.target.closest("[data-goto]");
      if (goto) navigate(goto.dataset.goto);
    });

    $("#account-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = $("#account-name");
      const name = input.value.trim();
      if (!name) return;
      const button = event.submitter || $("#account-form button[type='submit']");
      await action(button, async () => {
        const account = await api("/accounts", {
          method: "POST",
          body: JSON.stringify({ display_name: name, platform: "max" }),
        });
        input.value = "";
        await loadAccounts({ quiet: true });
        selectAccount(account.id);
      }, "Account created.");
    });

    $("#accounts-refresh").addEventListener("click", async (event) => {
      await action(event.currentTarget, () => loadAccounts({ quiet: true }), "Accounts refreshed.");
    });

    $("#accounts-list").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (button) {
        handleAccountAction(button).catch((error) => toast(error.message || String(error), "error"));
      }
    });

    $("#chats-refresh").addEventListener("click", async (event) => {
      if (!state.accountId) {
        toast("Choose a specific account first.", "error");
        return;
      }
      await action(event.currentTarget, async () => {
        state.chats = await api(`/accounts/${state.accountId}/chats`);
        renderChats();
      }, "Chats refreshed.");
    });

    $("#chats-save").addEventListener("click", (event) => saveChatSelection(event.currentTarget));

    $("#chat-search").addEventListener("input", applyChatFilter);
    $("#chat-select-all").addEventListener("click", () => {
      $$(".chat-row:not(.chat-search-hidden) input[name='chat-select']", $("#chats-list"))
        .forEach((input) => { input.checked = true; });
      updateChatCount();
    });
    $("#chat-select-none").addEventListener("click", () => {
      $$(".chat-row input[name='chat-select']", $("#chats-list"))
        .forEach((input) => { input.checked = false; });
      updateChatCount();
    });
    $("#chats-list").addEventListener("change", updateChatCount);

    $("#messages-refresh").addEventListener("click", (event) => {
      action(event.currentTarget, loadMessages);
    });
    $("#msg-unlabeled").addEventListener("change", (event) => {
      state.messagesUnlabeled = event.target.checked;
      state.messagesOffset = 0;
      loadMessages();
    });
    $("#msg-limit").addEventListener("change", (event) => {
      state.messagesLimit = Number(event.target.value);
      state.messagesOffset = 0;
      loadMessages();
    });
    $("#msg-prev").addEventListener("click", () => {
      state.messagesOffset = Math.max(0, state.messagesOffset - state.messagesLimit);
      loadMessages();
    });
    $("#msg-next").addEventListener("click", () => {
      state.messagesOffset += state.messagesLimit;
      loadMessages();
    });
    $("#messages-table").addEventListener("click", (event) => {
      const button = event.target.closest('[data-action="open-message"]');
      if (button) openMessage(button.dataset.message);
    });

    $("#overview-refresh").addEventListener("click", (event) => {
      action(event.currentTarget, loadOverview);
    });
    $("#overview-messages").addEventListener("click", (event) => {
      const button = event.target.closest('[data-action="open-message"]');
      if (button) openMessage(button.dataset.message);
    });
    $("#metrics-refresh").addEventListener("click", (event) => {
      action(event.currentTarget, loadClassificationView);
    });

    $("#run-form").addEventListener("submit", (event) => {
      event.preventDefault();
      runClassification(event.submitter || $("#run-form button[type='submit']"));
    });

    $("#export-preview").addEventListener("click", (event) => previewExport(event.currentTarget));
    $("#export-download").addEventListener("click", (event) => downloadExport(event.currentTarget));

    $("#labels-form").addEventListener("submit", (event) => {
      event.preventDefault();
      importLabels(event.currentTarget);
    });
    $("#labels-example").addEventListener("click", () => {
      $("#labels-json").value = JSON.stringify(EXAMPLE_LABELS, null, 2);
    });

    $("#token-btn").addEventListener("click", openTokenDialog);
    $("#token-save").addEventListener("click", saveToken);
    $("#token-clear").addEventListener("click", clearToken);

    $("#modal-close").addEventListener("click", closeModal);
    $("#modal").addEventListener("close", () => {
      state.modalAccount = null;
      state.modalMessage = null;
      stopAllStatusPolling();
    });

    $("#modal").addEventListener("click", (event) => {
      const copyButton = event.target.closest("[data-copy]");
      if (copyButton) {
        const value = copyButton.dataset.copy || "";
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(value)
            .then(() => toast("Copied to clipboard.", "ok"))
            .catch(() => toast("Clipboard is unavailable.", "error"));
        }
        return;
      }
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      if (button.dataset.action === "open-message") {
        openMessage(button.dataset.message);
      } else if (button.dataset.action === "poll-status") {
        setBusy(button, true, "Refreshing...");
        pollStatusOnce(button.dataset.account)
          .catch((error) => toast(error.message || String(error), "error"))
          .finally(() => setBusy(button, false));
      } else if (button.dataset.action === "classify") {
        classifyMessage(button.dataset.message, button);
      }
    });

    $("#modal").addEventListener("submit", (event) => {
      if (event.target.id !== "label-form") return;
      event.preventDefault();
      submitLabel(event.target);
    });
  }

  async function init() {
    bindEvents();
    await checkHealth();
    try {
      await loadAccounts({ quiet: true });
    } catch (error) {
      toast(error.message || String(error), "error");
    }
    const hashView = window.location.hash.replace("#", "");
    navigate(["overview", "accounts", "chats", "messages", "classification", "labels"].includes(hashView)
      ? hashView
      : "overview");
    window.setInterval(checkHealth, 30000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
