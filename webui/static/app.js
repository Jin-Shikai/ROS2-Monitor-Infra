const $ = (id) => document.getElementById(id);

let plugins = [];
let hosts = ["robot"];
let sources = [];
let converters = [];
let verdictServices = [];
let activeConverter = 0;
let activeVerdict = 0;
let lastLogId = 0;
let lastRobotLogId = 0;
let generated = false;
let eventSource = null;
let robotRunning = false;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  const text = await response.text();
  let data = {};
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (error) {
      const snippet = text.replace(/\s+/g, " ").slice(0, 120);
      throw new Error(`${path} returned non-JSON HTTP ${response.status}: ${snippet}`);
    }
  }
  if (!response.ok) {
    throw new Error(data.error || response.statusText);
  }
  return data;
}

function setStatus(text, running = false) {
  $("runState").textContent = text;
  $("runState").classList.toggle("running", running);
}

function showPage(name) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.page === name);
  });
  document.querySelectorAll(".page").forEach((page) => {
    page.classList.toggle("active", page.id === `page-${name}`);
  });
}

function uniqueSource(source) {
  return !sources.some(
    (item) => item.name === source.name && item.source_kind === source.source_kind,
  );
}

function sourceKey(source) {
  return `${source.source_kind}:${source.name}`;
}

function slug(value, fallback) {
  const cleaned = String(value || fallback)
    .replace(/[^a-zA-Z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return cleaned || fallback;
}

function currentConverter() {
  return converters[Math.min(activeConverter, Math.max(converters.length - 1, 0))];
}

function currentVerdict() {
  return verdictServices[Math.min(activeVerdict, Math.max(verdictServices.length - 1, 0))];
}

function ensureHost(value) {
  const cleaned = slug(value, "");
  if (!cleaned) return hosts[0];
  if (!hosts.includes(cleaned)) hosts.push(cleaned);
  return cleaned;
}

function hostOptions(selected) {
  return hosts
    .map((host) => `<option value="${escapeAttr(host)}" ${host === selected ? "selected" : ""}>${escapeAttr(host)}</option>`)
    .join("");
}

function removeHost(name) {
  if (hosts.length <= 1 || !hosts.includes(name)) return;
  hosts = hosts.filter((host) => host !== name);
  const fallback = hosts[0];
  sources.forEach((source) => {
    if (source.host === name) source.host = fallback;
  });
  converters.forEach((converter) => {
    if (converter.host === name) converter.host = fallback;
  });
  verdictServices.forEach((verdict) => {
    if (verdict.host === name) verdict.host = fallback;
  });
  renderGraphEditors();
}

function renderHosts() {
  const box = $("hostsList");
  box.className = "source-list";
  box.innerHTML = hosts
    .map((host) => `
      <div class="source-item">
        <strong>host</strong>
        <span>${escapeAttr(host)}</span>
        <button type="button" data-remove-host="${escapeAttr(host)}" ${hosts.length <= 1 ? "disabled" : ""}>Remove</button>
      </div>
    `)
    .join("");
  box.querySelectorAll("[data-remove-host]").forEach((button) => {
    button.addEventListener("click", () => removeHost(button.dataset.removeHost));
  });
}

function ensureGraphNodes() {
  if (!converters.length) {
    converters.push({
      id: "demo1-velocity-converter",
      class_path: "custom.speed_aggregate_filter:SpeedAggregateFilter",
      params: [],
      host: hosts[0],
      inputSourceKeys: [],
      verdictServiceIds: [],
    });
  }
  if (!verdictServices.length) {
    verdictServices.push({
      id: "demo1-speeding-check",
      class_path: "custom.threshold_verdict:ThresholdVerdict",
      params: [],
      host: hosts[0],
    });
  }
  activeConverter = Math.min(activeConverter, converters.length - 1);
  activeVerdict = Math.min(activeVerdict, verdictServices.length - 1);
}

function addSource(source) {
  const normalized = {
    source_kind: source.source_kind || "topic",
    name: (source.name || "").trim(),
    interface: (source.interface || "").trim(),
    host: ensureHost(source.host || hosts[0]),
  };
  if (!normalized.name || !normalized.interface || !uniqueSource(normalized)) return;
  sources.push(normalized);
  ensureGraphNodes();
  const converter = currentConverter();
  const key = sourceKey(normalized);
  if (converter && !converter.inputSourceKeys.includes(key)) {
    converter.inputSourceKeys.push(key);
  }
  renderSources();
  renderGraphEditors();
}

function removeSource(index) {
  const key = sourceKey(sources[index]);
  sources.splice(index, 1);
  converters.forEach((converter) => {
    converter.inputSourceKeys = converter.inputSourceKeys.filter((item) => item !== key);
  });
  renderSources();
  renderGraphEditors();
}

function renderSources() {
  const sourceBox = $("sourcesList");
  const inputBox = $("inputSourceList");
  const converter = currentConverter();
  if (!sources.length) {
    sourceBox.className = "source-list empty";
    sourceBox.textContent = "No monitored sources yet.";
    inputBox.className = "source-list empty";
    inputBox.textContent = "Add sources on the Discover page first.";
    return;
  }

  sourceBox.className = "source-list";
  sourceBox.innerHTML = sources
    .map((source, index) => `
      <div class="source-item">
        <strong>${source.source_kind}</strong>
        <span>${source.name}</span>
        <code>${source.interface}</code>
        <select data-source-host="${index}" title="Host">${hostOptions(source.host)}</select>
        <button type="button" data-remove-source="${index}">Remove</button>
      </div>
    `)
    .join("");

  inputBox.className = "source-list";
  inputBox.innerHTML = sources
    .map((source, index) => `
      <label class="source-item">
        <input type="checkbox" data-use-source="${index}" ${converter?.inputSourceKeys.includes(sourceKey(source)) ? "checked" : ""}>
        <strong>${source.source_kind}</strong>
        <span>${source.name}</span>
        <code>${source.interface}</code>
      </label>
    `)
    .join("");

  sourceBox.querySelectorAll("[data-remove-source]").forEach((button) => {
    button.addEventListener("click", () => removeSource(Number(button.dataset.removeSource)));
  });
  sourceBox.querySelectorAll("[data-source-host]").forEach((select) => {
    select.addEventListener("change", () => {
      sources[Number(select.dataset.sourceHost)].host = select.value;
    });
  });
  inputBox.querySelectorAll("[data-use-source]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const active = currentConverter();
      if (!active) return;
      const key = sourceKey(sources[Number(checkbox.dataset.useSource)]);
      if (checkbox.checked && !active.inputSourceKeys.includes(key)) {
        active.inputSourceKeys.push(key);
      }
      if (!checkbox.checked) {
        active.inputSourceKeys = active.inputSourceKeys.filter((item) => item !== key);
      }
      renderGraphEditors();
    });
  });
}

function paramRow(row, index, target) {
  const label = escapeAttr(row.label || row.key || "Parameter");
  const keyInput = row.schema
    ? `<input value="${escapeAttr(row.key || "")}" readonly spellcheck="false">`
    : `<input data-param-key="${target}:${index}" placeholder="key" value="${escapeAttr(row.key || "")}" spellcheck="false">`;
  const type = row.type || "auto";
  let valueInput = "";
  if (type === "bool") {
    valueInput = `
      <label class="inline-check">
        <input data-param-value="${target}:${index}" type="checkbox" ${String(row.value).toLowerCase() === "true" ? "checked" : ""}>
        enabled
      </label>`;
  } else if (type === "enum") {
    valueInput = `
      <select data-param-value="${target}:${index}">
        ${(row.options || []).map((option) => (
          `<option value="${escapeAttr(option)}" ${String(option) === String(row.value) ? "selected" : ""}>${escapeAttr(option)}</option>`
        )).join("")}
      </select>`;
  } else if (type === "json") {
    valueInput = `<textarea data-param-value="${target}:${index}" spellcheck="false">${escapeText(row.value ?? "")}</textarea>`;
  } else {
    const inputType = type === "number" || type === "int" ? "number" : "text";
    valueInput = `<input data-param-value="${target}:${index}" type="${inputType}" placeholder="value" value="${escapeAttr(row.value ?? "")}" spellcheck="false">`;
  }
  const typeCell = row.schema
    ? `<span class="param-type">${escapeAttr(type)}</span>`
    : `<select data-param-type="${target}:${index}">
        ${["auto", "string", "number", "int", "bool", "enum", "json"].map((item) => (
          `<option value="${item}" ${item === type ? "selected" : ""}>${item}</option>`
        )).join("")}
      </select>`;
  return `
    <div class="param-row ${type === "json" ? "json-param" : ""}">
      <label>${label}${row.required ? " *" : ""}${keyInput}</label>
      ${valueInput}
      ${typeCell}
      <button type="button" data-remove-param="${target}:${index}">Remove</button>
    </div>
  `;
}

function escapeAttr(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeText(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderParams() {
  $("converterParams").innerHTML = (currentConverter()?.params || [])
    .map((row, index) => paramRow(row, index, "converter"))
    .join("");
  $("verdictParams").innerHTML = (currentVerdict()?.params || [])
    .map((row, index) => paramRow(row, index, "verdict"))
    .join("");

  document.querySelectorAll("[data-param-key]").forEach((input) => {
    input.addEventListener("input", () => setParam(input.dataset.paramKey, "key", input.value));
  });
  document.querySelectorAll("[data-param-value]").forEach((input) => {
    const eventName = input.type === "checkbox" ? "change" : "input";
    input.addEventListener(eventName, () => {
      const value = input.type === "checkbox" ? String(input.checked) : input.value;
      setParam(input.dataset.paramValue, "value", value);
    });
  });
  document.querySelectorAll("[data-param-type]").forEach((select) => {
    select.addEventListener("change", () => setParam(select.dataset.paramType, "type", select.value));
  });
  document.querySelectorAll("[data-remove-param]").forEach((button) => {
    button.addEventListener("click", () => removeParam(button.dataset.removeParam));
  });
}

function paramArray(target) {
  if (target === "converter") return currentConverter()?.params || [];
  return currentVerdict()?.params || [];
}

function setParam(address, field, value) {
  const [target, rawIndex] = address.split(":");
  const rows = paramArray(target);
  if (rows[Number(rawIndex)]) rows[Number(rawIndex)][field] = value;
}

function removeParam(address) {
  const [target, rawIndex] = address.split(":");
  paramArray(target).splice(Number(rawIndex), 1);
  renderParams();
}

function renderGraphEditors() {
  ensureGraphNodes();
  $("converterSelect").innerHTML = converters
    .map((converter, index) => (
      `<option value="${index}" ${index === activeConverter ? "selected" : ""}>${escapeAttr(converter.id)}</option>`
    ))
    .join("");
  $("verdictSelect").innerHTML = verdictServices
    .map((verdict, index) => (
      `<option value="${index}" ${index === activeVerdict ? "selected" : ""}>${escapeAttr(verdict.id)}</option>`
    ))
    .join("");

  const converter = currentConverter();
  const verdict = currentVerdict();
  $("converterId").value = converter?.id || "";
  $("converterClass").value = converter?.class_path || "";
  $("converterHost").innerHTML = hostOptions(converter?.host || hosts[0]);
  $("verdictId").value = verdict?.id || "";
  $("verdictClass").value = verdict?.class_path || "";
  $("verdictHost").innerHTML = hostOptions(verdict?.host || hosts[0]);
  renderHosts();

  const linksBox = $("converterVerdictLinks");
  if (!verdictServices.length) {
    linksBox.className = "source-list empty";
    linksBox.textContent = "Add a verdict service first.";
  } else {
    linksBox.className = "source-list";
    linksBox.innerHTML = verdictServices
      .map((item) => `
        <label class="source-item">
          <input type="checkbox" data-use-verdict="${escapeAttr(item.id)}" ${converter?.verdictServiceIds.includes(item.id) ? "checked" : ""}>
          <strong>verdict</strong>
          <span>${escapeAttr(item.id)}</span>
          <code>${escapeAttr(item.class_path)}</code>
        </label>
      `)
      .join("");
    linksBox.querySelectorAll("[data-use-verdict]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        const active = currentConverter();
        if (!active) return;
        const id = checkbox.dataset.useVerdict;
        if (checkbox.checked && !active.verdictServiceIds.includes(id)) {
          active.verdictServiceIds.push(id);
        }
        if (!checkbox.checked) {
          active.verdictServiceIds = active.verdictServiceIds.filter((item) => item !== id);
        }
      });
    });
  }
  renderSources();
  renderParams();
}

function applyTemplate(templateId, options = {}) {
  const plugin = plugins.find((item) => item.id === templateId);
  if (!plugin) return;
  const applySources = options.applySources !== false;
  hosts = (plugin.hosts || ["robot"]).slice();
  const placement = plugin.placement || {};
  const converterId = plugin.converter_manifest || (templateId === "blank" ? "custom-converter" : templateId);
  const verdictId = plugin.verdict_manifest || (templateId === "blank" ? "custom-verdict" : `${templateId}-verdict`);
  converters = [{
    id: slug(converterId, "converter_1"),
    class_path: plugin.converter || "",
    params: structuredClone(plugin.converter_params || []),
    host: ensureHost(placement.converter || hosts[0]),
    inputSourceKeys: [],
    verdictServiceIds: [slug(verdictId, "verdict_1")],
  }];
  verdictServices = [{
    id: slug(verdictId, "verdict_1"),
    class_path: plugin.verdict || "",
    params: structuredClone(plugin.verdict_params || []),
    host: ensureHost(placement.verdict || hosts[0]),
  }];
  activeConverter = 0;
  activeVerdict = 0;
  if (applySources && plugin.sources?.length) {
    sources = [];
    plugin.sources.forEach((source) => addSource(source));
  } else {
    renderSources();
  }
  renderGraphEditors();
}

function renderGraphGroup(title, rows) {
  if (!rows.length) return "";
  return `
    <div class="graph-group">
      <h3>${title}</h3>
      ${rows.map((row) => `
        <div class="graph-item">
          <span>${row.name}</span>
          <code>${row.interface}</code>
          <button type="button" data-add-graph='${escapeAttr(JSON.stringify(row))}'>+ Add</button>
        </div>
      `).join("")}
    </div>
  `;
}

function renderGraph(data) {
  const box = $("graphResults");
  const topics = data.topics || [];
  const services = data.services || [];
  const actions = data.actions || [];
  if (!topics.length && !services.length && !actions.length) {
    box.innerHTML = `<div class="empty">No graph resources found.</div>`;
    return;
  }
  box.innerHTML = [
    renderGraphGroup("Topics", topics),
    renderGraphGroup("Services", services),
    renderGraphGroup("Actions", actions),
  ].join("");
  box.querySelectorAll("[data-add-graph]").forEach((button) => {
    button.addEventListener("click", () => addSource(JSON.parse(button.dataset.addGraph)));
  });
}

function renderDiscoveryFailure(data) {
  const attempts = (data.attempts || [])
    .map((row) => `<div><strong>${row.method}</strong>: ${row.error}</div>`)
    .join("");
  $("graphResults").innerHTML = `
    <div class="notice">
      Discovery failed. You can still add sources manually, or run the UI from a sourced ROS 2 environment.
      ${attempts}
    </div>
  `;
}

function currentPayload() {
  return {
    hosts: hosts.slice(),
    broker: {
      host: $("brokerHost").value.trim() || "127.0.0.1",
      port: Number($("brokerPort").value) || 1883,
    },
    sources: sources.map(({ source_kind, name, interface: iface, host }) => (
      { source_kind, name, interface: iface, host }
    )),
    converters: converters.map((converter) => ({
      id: converter.id,
      class_path: converter.class_path,
      host: converter.host,
      input_source_keys: converter.inputSourceKeys,
      verdict_service_ids: converter.verdictServiceIds,
      params: converter.params,
    })),
    verdict_services: verdictServices.map((verdict) => ({
      id: verdict.id,
      class_path: verdict.class_path,
      host: verdict.host,
      params: verdict.params,
    })),
  };
}

function renderVerdicts(rows) {
  $("verdictCount").textContent = rows.length ? `${rows.length} recent` : "";
  if (!rows.length) {
    $("verdicts").className = "verdicts empty";
    $("verdicts").textContent = "No verdict JSONL records found yet.";
    return;
  }
  $("verdicts").className = "verdicts";
  $("verdicts").innerHTML = rows
    .map((row) => {
      const failed = row.result === false;
      const label = `Result: ${String(row.result)}`;
      const details = row.details ? JSON.stringify(row.details) : "";
      return `
        <div class="verdict ${failed ? "failed" : "passed"}">
          <strong>${label}: ${row.property_id}</strong>
          <span>${details}</span>
          <span>${row._file || ""}</span>
        </div>`;
    })
    .join("");
}

function renderGenerated(data) {
  if (!data) return;
  generated = true;
  $("generatedMeta").textContent = `Wrote ${data.configs.length} config(s), ${data.compose_path}`;
  $("requestOut").textContent = JSON.stringify(data.request, null, 2);
  $("yamlOut").textContent = data.configs
    .map((cfg) => `# ${cfg.filename}\n# ${cfg.run_command}\n${cfg.yaml}`)
    .join("\n---\n");
}

function applyRunState(data) {
  generated = data.generated || generated;
  if (data.running) {
    setStatus(`Running: ${data.target_id}`, true);
  } else if (data.exit_code !== undefined) {
    setStatus(`Exited: ${data.exit_code}`, false);
  } else {
    setStatus(generated ? "Generated" : "Idle", false);
  }
}

function applyRobotState(data) {
  robotRunning = Boolean(data.running);
  if (data.running) {
    $("robotStatus").textContent = `Running: ${data.container_name}`;
  } else {
    $("robotStatus").textContent = data.message || "Robot container is stopped.";
  }
}

async function refreshRobotState() {
  try {
    const data = await api("/api/robots/current");
    applyRobotState(data);
  } catch (error) {
    $("robotStatus").textContent = error.message;
  }
}

function renderRobotLogText(lines) {
  $("robotLogs").textContent = lines.length
    ? lines.join("\n")
    : robotRunning
      ? "Robot is running, waiting for log output..."
      : "Robot logs will appear here.";
  $("robotLogs").scrollTop = $("robotLogs").scrollHeight;
  $("robotLogStatus").textContent = lines.length ? `${lines.length} lines` : "";
}

async function refreshRobotLogs() {
  try {
    const data = await api("/api/robots/logs?limit=120");
    renderRobotLogText(data.logs);
  } catch (error) {
    $("robotLogStatus").textContent = error.message;
  }
}

function appendRobotLogRows(rows) {
  if (!rows.length) {
    renderRobotLogText([]);
    return;
  }
  const freshRows = rows.filter((row) => Number(row.id) > lastRobotLogId);
  if (!freshRows.length) return;
  const text = freshRows.map((row) => row.line).join("\n");
  const logs = $("robotLogs");
  logs.textContent = logs.textContent.startsWith("Robot logs will")
    || logs.textContent.includes("waiting for log output")
    ? text
    : `${logs.textContent}\n${text}`;
  logs.scrollTop = logs.scrollHeight;
  lastRobotLogId = Number(freshRows[freshRows.length - 1].id);
  $("robotLogStatus").textContent = `${lastRobotLogId} lines via SSE`;
}

function appendLogRows(rows) {
  if (!rows.length) return;
  const freshRows = rows.filter((row) => Number(row.id) > lastLogId);
  if (!freshRows.length) return;
  const text = freshRows.map((row) => row.line).join("\n");
  const logs = $("logs");
  logs.textContent = logs.textContent.startsWith("Logs will") ? text : `${logs.textContent}\n${text}`;
  logs.scrollTop = logs.scrollHeight;
  lastLogId = Number(freshRows[freshRows.length - 1].id);
  $("logStatus").textContent = `${lastLogId} lines via SSE`;
}

function parseEventData(event) {
  try {
    return JSON.parse(event.data);
  } catch (error) {
    $("logStatus").textContent = `Live stream parse error: ${error.message}`;
    return null;
  }
}

function connectEventStream() {
  if (!window.EventSource) {
    $("logStatus").textContent = "This browser does not support Server-Sent Events.";
    return;
  }
  if (eventSource) return;
  eventSource = new EventSource("/api/events");
  eventSource.addEventListener("open", () => {
    const current = lastLogId ? `${lastLogId} lines` : "connected";
    $("logStatus").textContent = `${current} via SSE`;
  });
  eventSource.addEventListener("error", () => {
    $("logStatus").textContent = "SSE stream reconnecting.";
  });
  eventSource.addEventListener("run_state", (event) => {
    const data = parseEventData(event);
    if (data) applyRunState(data);
  });
  eventSource.addEventListener("robot_state", (event) => {
    const data = parseEventData(event);
    if (data) applyRobotState(data);
  });
  eventSource.addEventListener("robot_logs", (event) => {
    const data = parseEventData(event);
    if (data) appendRobotLogRows(data.logs || []);
  });
  eventSource.addEventListener("robot_log", (event) => {
    const data = parseEventData(event);
    if (data) appendRobotLogRows([data]);
  });
  eventSource.addEventListener("logs", (event) => {
    const data = parseEventData(event);
    if (data) appendLogRows(data.logs || []);
  });
  eventSource.addEventListener("log", (event) => {
    const data = parseEventData(event);
    if (data) appendLogRows([data]);
  });
  eventSource.addEventListener("verdicts", (event) => {
    const data = parseEventData(event);
    if (data) renderVerdicts(data.verdicts || []);
  });
  eventSource.addEventListener("generated", (event) => {
    const data = parseEventData(event);
    if (data) renderGenerated(data);
  });
}

async function init() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => showPage(tab.dataset.page));
  });

  const health = await api("/api/health");
  $("health").textContent = `Control plane ready at ${health.root}`;

  plugins = (await api("/api/plugins")).plugins;
  $("template").innerHTML = plugins
    .map((plugin) => `<option value="${plugin.id}">${plugin.name}</option>`)
    .join("");
  $("template").addEventListener("change", () => applyTemplate($("template").value));
  applyTemplate("cmd_vel_threshold", { applySources: false });
  $("template").value = "cmd_vel_threshold";
  connectEventStream();
}

$("startRobot").addEventListener("click", async () => {
  $("robotStatus").textContent = "Starting robot container...";
  $("robotLogs").textContent = "Building image and starting container...";
  lastRobotLogId = 0;
  try {
    const data = await api("/api/robots/start", {
      method: "POST",
      body: JSON.stringify({
        dockerfile: $("robotDockerfile").value,
        command: $("robotCommand").value,
      }),
    });
    applyRobotState(data);
  } catch (error) {
    $("robotStatus").textContent = error.message;
  }
});

$("stopRobot").addEventListener("click", async () => {
  try {
    const data = await api("/api/robots/stop", { method: "POST", body: "{}" });
    lastRobotLogId = 0;
    applyRobotState(data);
    renderRobotLogText([]);
  } catch (error) {
    $("robotStatus").textContent = error.message;
  }
});

$("refreshRobot").addEventListener("click", async () => {
  await refreshRobotState();
  await refreshRobotLogs();
});

$("scanGraph").addEventListener("click", async () => {
  $("scanStatus").textContent = "Scanning ROS graph...";
  $("graphResults").innerHTML = "";
  try {
    const data = await api("/api/discovery/graph");
    if (!data.available) {
      $("scanStatus").textContent = data.error || "Discovery failed.";
      renderDiscoveryFailure(data);
      return;
    }
    $("scanStatus").textContent = `Scan complete via ${data.method}.`;
    renderGraph(data);
  } catch (error) {
    $("scanStatus").textContent = error.message;
  }
});

$("addManualSource").addEventListener("click", () => {
  addSource({
    source_kind: $("manualKind").value,
    name: $("manualName").value,
    interface: $("manualInterface").value,
  });
});

$("converterSelect").addEventListener("change", () => {
  activeConverter = Number($("converterSelect").value);
  renderGraphEditors();
});

$("verdictSelect").addEventListener("change", () => {
  activeVerdict = Number($("verdictSelect").value);
  renderGraphEditors();
});

$("converterId").addEventListener("input", () => {
  const converter = currentConverter();
  if (!converter) return;
  const oldId = converter.id;
  converter.id = slug($("converterId").value, oldId);
  renderGraphEditors();
});

$("converterClass").addEventListener("input", () => {
  const converter = currentConverter();
  if (converter) converter.class_path = $("converterClass").value.trim();
});

$("verdictId").addEventListener("input", () => {
  const verdict = currentVerdict();
  if (!verdict) return;
  const oldId = verdict.id;
  verdict.id = slug($("verdictId").value, oldId);
  converters.forEach((converter) => {
    converter.verdictServiceIds = converter.verdictServiceIds.map((id) => (
      id === oldId ? verdict.id : id
    ));
  });
  renderGraphEditors();
});

$("verdictClass").addEventListener("input", () => {
  const verdict = currentVerdict();
  if (verdict) verdict.class_path = $("verdictClass").value.trim();
});

$("addConverter").addEventListener("click", () => {
  ensureGraphNodes();
  const id = `converter_${converters.length + 1}`;
  converters.push({
    id,
    class_path: currentConverter()?.class_path || "",
    params: [],
    host: currentConverter()?.host || hosts[0],
    inputSourceKeys: sources.map(sourceKey),
    verdictServiceIds: verdictServices.length ? [verdictServices[0].id] : [],
  });
  activeConverter = converters.length - 1;
  renderGraphEditors();
});

$("removeConverter").addEventListener("click", () => {
  if (converters.length <= 1) return;
  converters.splice(activeConverter, 1);
  activeConverter = Math.max(0, activeConverter - 1);
  renderGraphEditors();
});

$("addVerdict").addEventListener("click", () => {
  ensureGraphNodes();
  const id = `verdict_${verdictServices.length + 1}`;
  verdictServices.push({
    id,
    class_path: currentVerdict()?.class_path || "",
    params: [],
    host: currentVerdict()?.host || hosts[0],
  });
  activeVerdict = verdictServices.length - 1;
  renderGraphEditors();
});

$("addHost").addEventListener("click", () => {
  const name = $("newHostName").value.trim();
  if (!name) return;
  ensureHost(name);
  $("newHostName").value = "";
  renderGraphEditors();
});

$("converterHost").addEventListener("change", () => {
  const converter = currentConverter();
  if (converter) converter.host = $("converterHost").value;
});

$("verdictHost").addEventListener("change", () => {
  const verdict = currentVerdict();
  if (verdict) verdict.host = $("verdictHost").value;
});

$("removeVerdict").addEventListener("click", () => {
  if (verdictServices.length <= 1) return;
  const removed = verdictServices[activeVerdict].id;
  verdictServices.splice(activeVerdict, 1);
  converters.forEach((converter) => {
    converter.verdictServiceIds = converter.verdictServiceIds.filter((id) => id !== removed);
  });
  activeVerdict = Math.max(0, activeVerdict - 1);
  renderGraphEditors();
});

$("addConverterParam").addEventListener("click", () => {
  ensureGraphNodes();
  currentConverter().params.push({ key: "", value: "", type: "auto" });
  renderParams();
});

$("addVerdictParam").addEventListener("click", () => {
  ensureGraphNodes();
  currentVerdict().params.push({ key: "", value: "", type: "auto" });
  renderParams();
});

$("startRun").addEventListener("click", async () => {
  $("logs").textContent = "Generating runtime files and starting monitor...";
  $("requestOut").textContent = "Generating...";
  $("yamlOut").textContent = "Generating...";
  lastLogId = 0;
  try {
    const data = await api("/api/runs/start", {
      method: "POST",
      body: JSON.stringify(currentPayload()),
    });
    renderGenerated(data.generated_files);
    applyRunState(data);
  } catch (error) {
    $("logs").textContent = error.message;
    $("requestOut").textContent = error.message;
    $("yamlOut").textContent = error.message;
  }
});

$("stopRun").addEventListener("click", async () => {
  try {
    const data = await api("/api/runs/stop", { method: "POST", body: "{}" });
    applyRunState(data);
  } catch (error) {
    $("logs").textContent += `\n${error.message}`;
  }
});

$("clearVerdicts").addEventListener("click", async () => {
  try {
    const data = await api("/api/verdicts/clear", { method: "POST", body: "{}" });
    $("verdictCount").textContent = data.cleared_files ? `cleared ${data.cleared_files} files` : "";
    renderVerdicts([]);
  } catch (error) {
    $("verdictCount").textContent = error.message;
  }
});

init().catch((error) => {
  $("health").textContent = error.message;
});
