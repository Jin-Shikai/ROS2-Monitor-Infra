const $ = (id) => document.getElementById(id);

let plugins = [];
let manifests = [];
let hosts = [];
let sources = [];
let monitors = [];
let converters = [];
let verdictServices = [];
let selectedNode = null;
let selectedNodeKeys = new Set();
let selectedLink = null;
let lastLogId = 0;
let lastRobotLogId = 0;
let generated = false;
let eventSource = null;
let robotRunning = false;
let runActive = false;
let robotDockerfile = "Dockerfile";
let robotCommand = "source /opt/ros/kilted/setup.bash && python3 /demo/common/topic_robot.py cmd-velocity-cycle --ros-args -r __node:=showcase_robot";
let editorTargetPath = "";
let brokerHost = "127.0.0.1";
let brokerPort = 1883;
let zoom = 1;
let marquee = null;
let runLogRows = [];
let robotLogRows = [];
let runningNodeKeys = new Set();

const NODE_WIDTH = 210;
const NODE_HEIGHT = 72;
const HOST_PADDING = 18;
const HOST_HEADER = 36;
const HOST_GAP_X = 88;
const HOST_GAP_Y = 62;
const RUNTIME_GAP_X = 42;
const RUNTIME_GAP_Y = 22;

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
      const snippet = text.replace(/\s+/g, " ").slice(0, 160);
      throw new Error(`${path} returned non-JSON HTTP ${response.status}: ${snippet}`);
    }
  }
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function escapeAttr(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeText(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function slug(value, fallback) {
  const cleaned = String(value || fallback)
    .replace(/[^a-zA-Z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return cleaned || fallback;
}

function sourceKey(source) {
  return `${source.source_kind}:${source.name}`;
}

function sourceId(source) {
  return `source:${sourceKey(source)}`;
}

function monitorKey(monitor) {
  return `monitor:${monitor.id}`;
}

function ensureHost(value, fallback = "robot") {
  const host = slug(value, fallback);
  if (!hosts.includes(host)) hosts.push(host);
  return host;
}

function hostOptions(selected) {
  return hosts
    .map((host) => `<option value="${escapeAttr(host)}" ${host === selected ? "selected" : ""}>${escapeAttr(host)}</option>`)
    .join("");
}

function setStatus(text, running = false) {
  $("scanStatus").textContent = text || (running ? "Running." : "Idle.");
  renderTopology();
}

function classPathToFile(classPath) {
  const moduleName = String(classPath || "").split(":")[0].trim();
  if (!moduleName) return "";
  return `${moduleName.replaceAll(".", "/")}.py`;
}

function serviceNameForHost(host) {
  return `generated_${slug(host, "host")}`;
}

function selectedKeys() {
  if (selectedNodeKeys.size) return sortNodeKeys([...selectedNodeKeys]);
  const key = nodeKeyFromSelection(selectedNode);
  return key ? [key] : [];
}

function sortNodeKeys(keys) {
  const layout = topologyLayout();
  const ordered = [...layout.hostBoxes.map((box) => ({ key: box.key })), ...layout.nodes];
  const order = Object.fromEntries(ordered.map((node, index) => [node.key, index]));
  return keys.slice().sort((a, b) => (order[a] ?? 9999) - (order[b] ?? 9999));
}

function primarySelectedKey() {
  return selectedKeys()[0] || "";
}

function hostForNodeKey(key) {
  if (key.startsWith("host:")) return key.replace(/^host:/, "");
  if (key.startsWith("source:")) {
    return sources.find((source) => sourceId(source) === key)?.host || "";
  }
  if (key.startsWith("monitor:")) {
    const id = key.replace(/^monitor:/, "");
    return monitors.find((monitor) => monitor.id === id)?.host || "";
  }
  if (key.startsWith("converter:")) {
    const id = key.replace(/^converter:/, "");
    return converters.find((converter) => converter.id === id)?.host || "";
  }
  if (key.startsWith("verdict:")) {
    const id = key.replace(/^verdict:/, "");
    return verdictServices.find((verdict) => verdict.id === id)?.host || "";
  }
  return "";
}

function servicesForKeys(keys) {
  const services = new Set();
  keys.forEach((key) => {
    const host = hostForNodeKey(key);
    if (host) services.add(serviceNameForHost(host));
  });
  return [...services];
}

function labelForNodeKey(key) {
  if (key.startsWith("host:")) return key.replace(/^host:/, "");
  if (key.startsWith("source:")) return sources.find((source) => sourceId(source) === key)?.name || key;
  if (key.startsWith("monitor:")) return key.replace(/^monitor:/, "");
  if (key.startsWith("converter:")) return key.replace(/^converter:/, "");
  if (key.startsWith("verdict:")) return key.replace(/^verdict:/, "");
  return key || "Selection";
}

function logTermsForKey(key) {
  const terms = [labelForNodeKey(key), hostForNodeKey(key), serviceNameForHost(hostForNodeKey(key))].filter(Boolean);
  if (key.startsWith("host:")) terms.push("node_runner", "monitor_node");
  if (key.startsWith("source:")) terms.push("robot", "docker", "ros");
  if (key.startsWith("monitor:")) terms.push("monitor_node", "monitor");
  if (key.startsWith("converter:")) {
    const id = key.replace(/^converter:/, "");
    const converter = converters.find((item) => item.id === id);
    terms.push(id, converter?.class_path || "", converter?.host || "");
  }
  if (key.startsWith("verdict:")) {
    const id = key.replace(/^verdict:/, "");
    const verdict = verdictServices.find((item) => item.id === id);
    terms.push(id, verdict?.class_path || "", verdict?.host || "", "verdict");
  }
  return terms.map((term) => String(term).toLowerCase()).filter(Boolean);
}

function currentPayload() {
  return {
    hosts: hosts.slice(),
    broker: {
      host: brokerHost,
      port: Number(brokerPort) || 1883,
    },
    sources: sources.map(({ source_kind, name, interface: iface, host }) => ({
      source_kind,
      name,
      interface: iface,
      host,
    })),
    monitors: monitors.map((monitor) => ({
      id: monitor.id,
      host: monitor.host,
      source_keys: monitor.sourceKeys,
    })),
    converters: converters.map((converter) => ({
      id: converter.id,
      class_path: converter.class_path,
      host: converter.host,
      input_source_keys: converter.inputSourceKeys,
      input_converter_ids: converter.inputConverterIds || [],
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

function selectedConverter() {
  if (selectedNode?.kind !== "converter") return converters[0] || null;
  return converters.find((item) => item.id === selectedNode.id) || converters[0] || null;
}

function selectedVerdict() {
  if (selectedNode?.kind !== "verdict") return verdictServices[0] || null;
  return verdictServices.find((item) => item.id === selectedNode.id) || verdictServices[0] || null;
}

function selectedHost() {
  if (selectedNode?.kind !== "host") return "";
  return selectedNode.id;
}

function uniqueRuntimeId(base, existingIds) {
  let id = slug(base, "runtime");
  let index = 2;
  while (existingIds.includes(id)) {
    id = `${slug(base, "runtime")}_${index}`;
    index += 1;
  }
  return id;
}

function addHost(seed = {}) {
  const base = seed.id || `host${hosts.length + 1}`;
  const host = uniqueRuntimeId(base, hosts);
  hosts.push(host);
  selectedNode = { kind: "host", id: host };
  selectedNodeKeys = new Set([`host:${host}`]);
  renderAll();
}

function addRobot(seed = {}) {
  const targetHost = seed.host || selectedHost();
  if (!targetHost) {
    $("scanStatus").textContent = "Create and select a host before adding a robot.";
    return;
  }
  const host = ensureHost(targetHost);
  const source = {
    source_kind: seed.source_kind || "topic",
    name: seed.name || `/${host}/odom`,
    interface: seed.interface || "nav_msgs/msg/Odometry",
    host,
  };
  if (!sources.some((item) => sourceKey(item) === sourceKey(source))) {
    sources.push(source);
  }
  selectedNode = { kind: "robot", id: sourceId(source) };
  selectedNodeKeys = new Set([sourceId(source)]);
  renderAll();
}

function addMonitor(seed = {}) {
  const targetHost = seed.host || selectedHost();
  if (!targetHost) {
    $("scanStatus").textContent = "Select a host before adding a monitor.";
    return;
  }
  const host = ensureHost(targetHost);
  const id = uniqueRuntimeId(seed.id || `monitor_${host}`, monitors.map((monitor) => monitor.id));
  const sameHostKeys = sources.filter((source) => source.host === host).map(sourceKey);
  const monitor = {
    id,
    host,
    sourceKeys: seed.sourceKeys ? seed.sourceKeys.slice() : sameHostKeys,
  };
  monitors.push(monitor);
  selectedNode = { kind: "monitor", id: monitor.id };
  selectedNodeKeys = new Set([monitorKey(monitor)]);
  $("scanStatus").textContent = monitor.sourceKeys.length
    ? `Monitor ${id} subscribes to ${monitor.sourceKeys.length} source(s) on ${host}. Use Connect to target to subscribe robots on other hosts.`
    : `Monitor ${id} added with no subscriptions. Select robot blocks, click this monitor, then Connect to target.`;
  renderAll();
}

function addConverter(seed = {}) {
  const targetHost = seed.host || selectedHost();
  if (!targetHost) {
    $("scanStatus").textContent = "Select a host before adding a converter.";
    return;
  }
  const index = converters.length + 1;
  const converter = {
    id: uniqueRuntimeId(seed.id || `converter_${index}`, converters.map((item) => item.id)),
    class_path: seed.class_path || "custom.rule_based:RuleBasedConverter",
    params: structuredClone(seed.params || []),
    host: ensureHost(targetHost),
    inputSourceKeys: seed.inputSourceKeys ? seed.inputSourceKeys.slice() : [],
    inputConverterIds: seed.inputConverterIds ? seed.inputConverterIds.slice() : [],
    verdictServiceIds: seed.verdictServiceIds ? seed.verdictServiceIds.slice() : [],
  };
  converters.push(converter);
  selectedNode = { kind: "converter", id: converter.id };
  selectedNodeKeys = new Set([`converter:${converter.id}`]);
  renderAll();
}

function addVerdict(seed = {}) {
  const targetHost = seed.host || selectedHost();
  if (!targetHost) {
    $("scanStatus").textContent = "Select a host before adding a verdict service.";
    return;
  }
  const index = verdictServices.length + 1;
  const verdict = {
    id: uniqueRuntimeId(seed.id || `verdict_${index}`, verdictServices.map((item) => item.id)),
    class_path: seed.class_path || "custom.threshold:ThresholdVerdict",
    params: structuredClone(seed.params || []),
    host: ensureHost(targetHost),
  };
  verdictServices.push(verdict);
  selectedNode = { kind: "verdict", id: verdict.id };
  selectedNodeKeys = new Set([`verdict:${verdict.id}`]);
  renderAll();
}

function deleteNodeKey(key) {
  if (key.startsWith("source:")) {
    const index = sources.findIndex((item) => sourceId(item) === key);
    if (index >= 0) {
      const key = sourceKey(sources[index]);
      sources.splice(index, 1);
      monitors.forEach((monitor) => {
        monitor.sourceKeys = monitor.sourceKeys.filter((item) => item !== key);
      });
      converters.forEach((converter) => {
        converter.inputSourceKeys = converter.inputSourceKeys.filter((item) => item !== key);
      });
    }
  }
  if (key.startsWith("monitor:")) {
    const id = key.replace(/^monitor:/, "");
    monitors = monitors.filter((item) => item.id !== id);
  }
  if (key.startsWith("converter:")) {
    const id = key.replace(/^converter:/, "");
    converters = converters.filter((item) => item.id !== id);
    pruneConverterChains();
  }
  if (key.startsWith("verdict:")) {
    const id = key.replace(/^verdict:/, "");
    verdictServices = verdictServices.filter((item) => item.id !== id);
    converters.forEach((converter) => {
      converter.verdictServiceIds = converter.verdictServiceIds.filter((verdictId) => verdictId !== id);
    });
  }
  if (key.startsWith("host:")) {
    const host = key.replace(/^host:/, "");
    const sourceKeys = sources.filter((source) => source.host === host).map(sourceKey);
    hosts = hosts.filter((item) => item !== host);
    sources = sources.filter((source) => source.host !== host);
    monitors = monitors.filter((monitor) => monitor.host !== host);
    converters = converters.filter((converter) => converter.host !== host);
    verdictServices = verdictServices.filter((verdict) => verdict.host !== host);
    monitors.forEach((monitor) => {
      monitor.sourceKeys = monitor.sourceKeys.filter((key) => !sourceKeys.includes(key));
    });
    converters.forEach((converter) => {
      converter.inputSourceKeys = converter.inputSourceKeys.filter((key) => !sourceKeys.includes(key));
    });
    pruneConverterChains();
  }
}

function deleteSelectedResources() {
  const link = findSelectedLink();
  if (link) {
    (link.pairs || [link]).forEach(removeRuntimeLink);
    selectedLink = null;
    renderAll();
    return;
  }
  selectedKeys().forEach(deleteNodeKey);
  selectedNode = null;
  selectedNodeKeys.clear();
  renderAll();
}

function pruneConverterChains() {
  const converterIds = new Set(converters.map((item) => item.id));
  converters.forEach((converter) => {
    converter.inputConverterIds = (converter.inputConverterIds || []).filter((id) => converterIds.has(id));
  });
}

function applyConnection(mode) {
  const verb = mode === "connect" ? "Connected" : "Disconnected";
  if (!selectedNode) {
    $("scanStatus").textContent = "Select the source blocks first, then shift-click the target (monitor, converter, or verdict) last.";
    return;
  }
  const otherKeys = [...selectedNodeKeys].filter((key) => key !== nodeKeyFromSelection(selectedNode));
  if (!otherKeys.length) {
    $("scanStatus").textContent = "Select source blocks first (click, then shift-click or box-select to extend), and shift-click the target block last.";
    return;
  }
  if (selectedNode.kind === "monitor") {
    const monitor = monitors.find((item) => item.id === selectedNode.id);
    if (!monitor) return;
    const keys = otherKeys.filter((key) => key.startsWith("source:")).flatMap((key) => sourceKeysForNodeKey(key));
    if (!keys.length) {
      $("scanStatus").textContent = "A monitor target accepts robot source blocks only.";
      return;
    }
    if (mode === "connect") {
      keys.forEach((key) => {
        if (!monitor.sourceKeys.includes(key)) monitor.sourceKeys.push(key);
      });
    } else {
      monitor.sourceKeys = monitor.sourceKeys.filter((key) => !keys.includes(key));
    }
    $("scanStatus").textContent = `${verb} ${keys.length} robot source(s) ${mode === "connect" ? "to" : "from"} ${monitor.id}.`;
    renderAll();
    return;
  }
  if (selectedNode.kind === "converter") {
    const converter = converters.find((item) => item.id === selectedNode.id);
    if (!converter) return;
    const inputKeys = otherKeys.flatMap((key) => sourceKeysForNodeKey(key));
    const upstreamIds = otherKeys
      .flatMap((key) => converterIdsForNodeKey(key))
      .filter((id) => id !== converter.id);
    if (!inputKeys.length && !upstreamIds.length) {
      $("scanStatus").textContent = "A converter target accepts robot, monitor, or converter blocks.";
      return;
    }
    converter.inputConverterIds = converter.inputConverterIds || [];
    if (mode === "connect") {
      inputKeys.forEach((key) => {
        if (!converter.inputSourceKeys.includes(key)) converter.inputSourceKeys.push(key);
      });
      upstreamIds.forEach((id) => {
        if (!converter.inputConverterIds.includes(id)) converter.inputConverterIds.push(id);
      });
    } else {
      converter.inputSourceKeys = converter.inputSourceKeys.filter((key) => !inputKeys.includes(key));
      converter.inputConverterIds = converter.inputConverterIds.filter((id) => !upstreamIds.includes(id));
    }
    const parts = [];
    if (inputKeys.length) parts.push(`${inputKeys.length} source input(s)`);
    if (upstreamIds.length) parts.push(`${upstreamIds.length} converter feed(s)`);
    $("scanStatus").textContent = `${verb} ${parts.join(" and ")} ${mode === "connect" ? "to" : "from"} ${converter.id}.`;
    renderAll();
    return;
  }
  if (selectedNode.kind === "verdict") {
    const verdict = verdictServices.find((item) => item.id === selectedNode.id);
    if (!verdict) return;
    const converterIds = otherKeys.flatMap((key) => converterIdsForNodeKey(key));
    if (!converterIds.length) {
      $("scanStatus").textContent = "A verdict target accepts converter blocks.";
      return;
    }
    converterIds.forEach((converterId) => {
      const converter = converters.find((item) => item.id === converterId);
      if (!converter) return;
      if (mode === "connect" && !converter.verdictServiceIds.includes(verdict.id)) {
        converter.verdictServiceIds.push(verdict.id);
      }
      if (mode !== "connect") {
        converter.verdictServiceIds = converter.verdictServiceIds.filter((id) => id !== verdict.id);
      }
    });
    $("scanStatus").textContent = `${verb} ${converterIds.length} converter(s) ${mode === "connect" ? "to" : "from"} ${verdict.id}.`;
    renderAll();
    return;
  }
  $("scanStatus").textContent = "The target must be a monitor, converter, or verdict service.";
}

function connectSelectionToTarget() {
  applyConnection("connect");
}

function disconnectSelectionFromTarget() {
  applyConnection("disconnect");
}

function runtimeNodes() {
  const nodes = [];
  sources.forEach((source) => nodes.push({
    key: sourceId(source),
    kind: "robot",
    id: sourceId(source),
    host: source.host,
    stage: 0,
    title: source.name,
    subtitle: source.interface,
    status: isNodeRunning(sourceId(source)) ? "running" : "ROS source",
  }));
  monitors.forEach((monitor) => nodes.push({
    key: monitorKey(monitor),
    kind: "monitor",
    id: monitor.id,
    host: monitor.host,
    stage: 1,
    title: monitor.id,
    subtitle: `${monitor.sourceKeys.length} source(s)`,
    status: isNodeRunning(monitorKey(monitor)) ? "running" : monitor.host,
  }));
  converters.forEach((converter) => nodes.push({
    key: `converter:${converter.id}`,
    kind: "converter",
    id: converter.id,
    host: converter.host,
    stage: 2,
    title: converter.id,
    subtitle: converter.class_path,
    status: isNodeRunning(`converter:${converter.id}`) ? "running" : converter.host,
  }));
  verdictServices.forEach((verdict) => nodes.push({
    key: `verdict:${verdict.id}`,
    kind: "verdict",
    id: verdict.id,
    host: verdict.host,
    stage: 3,
    title: verdict.id,
    subtitle: verdict.class_path,
    status: isNodeRunning(`verdict:${verdict.id}`) ? "running" : verdict.host,
  }));
  return nodes;
}

function topologyModel() {
  const nodes = runtimeNodes();
  const runtimeLinks = [];
  const hostLinks = [];
  const seenRuntime = new Set();
  const seenHost = new Set();
  const nodeByKey = Object.fromEntries(nodes.map((node) => [node.key, node]));

  const addRuntimeLink = (from, to, payload = "local") => {
    const key = `${payload}|${from}|${to}`;
    if (seenRuntime.has(key) || from === to) return;
    seenRuntime.add(key);
    runtimeLinks.push({ key, from, to, payload });
  };
  const addHostLink = (fromHost, toHost, fromRuntime, toRuntime, payload) => {
    if (!fromHost || !toHost || fromHost === toHost) return;
    const key = `${payload}|host:${fromHost}|host:${toHost}`;
    const pair = { from: fromRuntime, to: toRuntime, payload };
    let existing = hostLinks.find((link) => link.key === key);
    if (!existing) {
      seenHost.add(key);
      existing = { key, from: fromHost, to: toHost, payload, pairs: [] };
      hostLinks.push(existing);
    }
    if (!existing.pairs.some((item) => item.from === pair.from && item.to === pair.to)) {
      existing.pairs.push(pair);
    }
  };

  sources.forEach((source) => {
    const key = sourceKey(source);
    monitors.filter((monitor) => monitor.sourceKeys.includes(key)).forEach((monitor) => {
      const fromKey = sourceId(source);
      const toKey = monitorKey(monitor);
      if (source.host === monitor.host) addRuntimeLink(fromKey, toKey, "ros");
      else addHostLink(source.host, monitor.host, fromKey, toKey, "ros");
    });
  });

  converters.forEach((converter) => {
    converter.inputSourceKeys.forEach((key) => {
      const source = sources.find((item) => sourceKey(item) === key);
      if (!source) return;
      const feedingMonitors = monitors.filter((monitor) => monitor.sourceKeys.includes(key));
      const converterKey = `converter:${converter.id}`;
      feedingMonitors.forEach((monitor) => {
        const monitorNodeKey = monitorKey(monitor);
        if (monitor.host === converter.host) addRuntimeLink(monitorNodeKey, converterKey, "records");
        else addHostLink(monitor.host, converter.host, monitorNodeKey, converterKey, "records");
      });
    });
    (converter.inputConverterIds || []).forEach((upstreamId) => {
      const upstream = converters.find((item) => item.id === upstreamId);
      if (!upstream || upstream.id === converter.id) return;
      const fromKey = `converter:${upstream.id}`;
      const toKey = `converter:${converter.id}`;
      if (upstream.host === converter.host) addRuntimeLink(fromKey, toKey, "chain");
      else addHostLink(upstream.host, converter.host, fromKey, toKey, "chain");
    });
    converter.verdictServiceIds.forEach((verdictId) => {
      const verdict = verdictServices.find((item) => item.id === verdictId);
      if (!verdict) return;
      const converterKey = `converter:${converter.id}`;
      const verdictKey = `verdict:${verdict.id}`;
      if (converter.host === verdict.host) addRuntimeLink(converterKey, verdictKey, "dsl");
      else addHostLink(converter.host, verdict.host, converterKey, verdictKey, "dsl");
    });
  });

  return {
    nodes,
    runtimeLinks: runtimeLinks.filter((link) => nodeByKey[link.from] && nodeByKey[link.to]),
    hostLinks,
  };
}

function topologyLayout() {
  const model = topologyModel();
  const hostMap = new Map();
  hosts.forEach((host) => hostMap.set(host, []));
  model.nodes.forEach((node) => {
    if (!hostMap.has(node.host)) hostMap.set(node.host, []);
    hostMap.get(node.host).push({ ...node });
  });

  const hostBoxes = [...hostMap.entries()].map(([host, hostNodes]) => {
    const stages = [...new Set(hostNodes.map((node) => node.stage))].sort((a, b) => b - a);
    const rowsByStage = Object.fromEntries(stages.map((stage) => [stage, hostNodes.filter((node) => node.stage === stage)]));
    const maxColumns = Math.max(1, ...Object.values(rowsByStage).map((items) => items.length));
    return {
      key: `host:${host}`,
      id: host,
      host,
      minStage: stages.length ? Math.min(...stages) : 0,
      maxStage: stages.length ? Math.max(...stages) : 0,
      stages,
      rowsByStage,
      nodes: hostNodes,
      width: HOST_PADDING * 2 + maxColumns * NODE_WIDTH + Math.max(0, maxColumns - 1) * RUNTIME_GAP_X,
      height: HOST_HEADER + HOST_PADDING + Math.max(1, stages.length) * NODE_HEIGHT + Math.max(0, stages.length - 1) * RUNTIME_GAP_Y + HOST_PADDING,
      x: 0,
      y: 0,
    };
  }).sort((a, b) => b.maxStage - a.maxStage || a.host.localeCompare(b.host));

  const rows = [];
  hostBoxes.forEach((box) => {
    let row = rows.find((item) => item.stage === box.maxStage);
    if (!row) {
      row = { stage: box.maxStage, boxes: [] };
      rows.push(row);
    }
    row.boxes.push(box);
  });
  rows.sort((a, b) => b.stage - a.stage);

  let cursorY = 52;
  rows.forEach((row) => {
    let cursorX = 42;
    const maxHeight = Math.max(...row.boxes.map((box) => box.height));
    row.boxes.forEach((box) => {
      box.x = cursorX;
      box.y = cursorY;
      cursorX += box.width + HOST_GAP_X;
    });
    cursorY += maxHeight + HOST_GAP_Y;
  });

  const layoutNodes = [];
  hostBoxes.forEach((box) => {
    box.stages.forEach((stage, stageIndex) => {
      const items = box.rowsByStage[stage];
      items.forEach((node, rowIndex) => {
        node.x = box.x + HOST_PADDING + rowIndex * (NODE_WIDTH + RUNTIME_GAP_X);
        node.y = box.y + HOST_HEADER + HOST_PADDING + stageIndex * (NODE_HEIGHT + RUNTIME_GAP_Y);
        layoutNodes.push(node);
      });
    });
  });

  const hostById = Object.fromEntries(hostBoxes.map((box) => [box.host, box]));
  const nodeByKey = Object.fromEntries(layoutNodes.map((node) => [node.key, node]));
  return { ...model, nodes: layoutNodes, nodeByKey, hostBoxes, hostById };
}

function iconFor(kind) {
  return { robot: "R", monitor: "M", host: "H", converter: "C", verdict: "V" }[kind] || "?";
}

function nodeSelectionKind(node) {
  if (node.kind === "host") return { kind: "host", id: node.id };
  if (node.kind === "robot") return { kind: "robot", id: node.id };
  if (node.kind === "monitor") return { kind: "monitor", id: node.id };
  return { kind: node.kind, id: node.id };
}

function nodeKeyFromSelection(node) {
  if (!node) return "";
  if (node.kind === "host") return `host:${node.id}`;
  if (node.kind === "robot") return node.id;
  if (node.kind === "monitor") return node.id;
  return `${node.kind}:${node.id}`;
}

function sourceKeysForNodeKey(key) {
  if (key.startsWith("source:")) {
    const source = sources.find((item) => sourceId(item) === key);
    return source ? [sourceKey(source)] : [];
  }
  if (key.startsWith("monitor:")) {
    const id = key.replace(/^monitor:/, "");
    return monitors.find((monitor) => monitor.id === id)?.sourceKeys || [];
  }
  return [];
}

function converterIdsForNodeKey(key) {
  if (!key.startsWith("converter:")) return [];
  const id = key.replace(/^converter:/, "");
  return converters.some((item) => item.id === id) ? [id] : [];
}

function describeLinkPair(pair) {
  return `${labelForNodeKey(pair.from)} → ${labelForNodeKey(pair.to)}`;
}

function removeRuntimeLink(pair) {
  const { from, to, payload } = pair;
  if (payload === "ros") {
    const monitor = monitors.find((item) => item.id === to.replace(/^monitor:/, ""));
    const key = from.startsWith("source:") ? from.slice("source:".length) : "";
    if (monitor && key) monitor.sourceKeys = monitor.sourceKeys.filter((item) => item !== key);
    return;
  }
  if (payload === "records") {
    const monitor = monitors.find((item) => item.id === from.replace(/^monitor:/, ""));
    const converter = converters.find((item) => item.id === to.replace(/^converter:/, ""));
    if (monitor && converter) {
      converter.inputSourceKeys = converter.inputSourceKeys.filter((key) => !monitor.sourceKeys.includes(key));
    }
    return;
  }
  if (payload === "dsl") {
    const converter = converters.find((item) => item.id === from.replace(/^converter:/, ""));
    const verdictId = to.replace(/^verdict:/, "");
    if (converter) converter.verdictServiceIds = converter.verdictServiceIds.filter((id) => id !== verdictId);
    return;
  }
  if (payload === "chain") {
    const upstreamId = from.replace(/^converter:/, "");
    const downstream = converters.find((item) => item.id === to.replace(/^converter:/, ""));
    if (downstream) {
      downstream.inputConverterIds = (downstream.inputConverterIds || []).filter((id) => id !== upstreamId);
    }
  }
}

function findSelectedLink() {
  if (!selectedLink) return null;
  const model = topologyModel();
  return [...model.runtimeLinks, ...model.hostLinks].find((link) => link.key === selectedLink) || null;
}

function runtimeKeysForHost(host) {
  const keys = [];
  sources.forEach((source) => {
    if (source.host === host) keys.push(sourceId(source));
  });
  monitors.forEach((monitor) => {
    if (monitor.host === host) keys.push(monitorKey(monitor));
  });
  converters.forEach((converter) => {
    if (converter.host === host) keys.push(`converter:${converter.id}`);
  });
  verdictServices.forEach((verdict) => {
    if (verdict.host === host) keys.push(`verdict:${verdict.id}`);
  });
  return keys;
}

function setHostRunning(host, running) {
  const keys = [`host:${host}`, ...runtimeKeysForHost(host).filter((key) => !key.startsWith("source:"))];
  keys.forEach((key) => {
    if (running) runningNodeKeys.add(key);
    else runningNodeKeys.delete(key);
  });
}

function isNodeRunning(key) {
  if (runningNodeKeys.has(key)) return true;
  const host = hostForNodeKey(key);
  return Boolean(host && runningNodeKeys.has(`host:${host}`) && !key.startsWith("source:"));
}

function isSelected(node) {
  return selectedNode && selectedNode.kind === nodeSelectionKind(node).kind && selectedNode.id === nodeSelectionKind(node).id;
}

function edgePoints(from, to) {
  if (Math.abs(from.y - to.y) < 2) {
    const x1 = from.x + NODE_WIDTH;
    const y1 = from.y + NODE_HEIGHT / 2;
    const x2 = to.x;
    const y2 = to.y + NODE_HEIGHT / 2;
    return `${x1},${y1} ${x2},${y2}`;
  }
  const upward = to.y < from.y;
  const x1 = from.x + NODE_WIDTH / 2;
  const y1 = upward ? from.y : from.y + NODE_HEIGHT;
  const x2 = to.x + NODE_WIDTH / 2;
  const y2 = upward ? to.y + NODE_HEIGHT : to.y;
  if (Math.abs(x1 - x2) < 2) return `${x1},${y1} ${x2},${y2}`;
  const midY = Math.round((y1 + y2) / 2);
  return `${x1},${y1} ${x1},${midY} ${x2},${midY} ${x2},${y2}`;
}

function hostEdgePoints(from, to) {
  if (Math.abs(from.y - to.y) < 2) {
    const x1 = from.x + from.width;
    const y1 = from.y + from.height / 2;
    const x2 = to.x;
    const y2 = to.y + to.height / 2;
    return `${x1},${y1} ${x2},${y2}`;
  }
  const upward = to.y < from.y;
  const x1 = from.x + from.width / 2;
  const y1 = upward ? from.y : from.y + from.height;
  const x2 = to.x + to.width / 2;
  const y2 = upward ? to.y + to.height : to.y;
  if (Math.abs(x1 - x2) < 2) return `${x1},${y1} ${x2},${y2}`;
  const midY = Math.round((y1 + y2) / 2);
  return `${x1},${y1} ${x1},${midY} ${x2},${midY} ${x2},${y2}`;
}

function polylineLabelPoint(points) {
  const pairs = points.split(" ").map((point) => point.split(",").map(Number));
  const midpoint = pairs[Math.floor(pairs.length / 2)] || pairs[0] || [0, 0];
  return { x: midpoint[0], y: midpoint[1] - 8 };
}

function toggleNodeSelection(key, node) {
  if (selectedNodeKeys.has(key)) {
    selectedNodeKeys.delete(key);
    if (nodeKeyFromSelection(selectedNode) === key) selectedNode = null;
  } else {
    selectedNodeKeys.add(key);
    if (node) selectedNode = nodeSelectionKind(node);
  }
  renderAll();
}

function setZoom(nextZoom) {
  zoom = Math.min(1.6, Math.max(0.55, Number(nextZoom.toFixed(2))));
  renderTopology();
}

function updateToolbarState() {
  const hostSelected = Boolean(selectedHost());
  ["addRobot", "addMonitor", "addConverter", "addVerdict"].forEach((id) => {
    const button = $(id);
    if (button) button.disabled = !hostSelected;
  });
  const hasNodeSelection = selectedKeys().length > 0;
  ["connectSelection", "disconnectSelection", "startRun", "stopRun", "restartSelected"].forEach((id) => {
    const button = $(id);
    if (button) button.disabled = !hasNodeSelection;
  });
  $("clearSelection").disabled = !hasNodeSelection && !selectedLink;
}

function topologyWarnings() {
  const warnings = [];
  const monitoredKeys = new Set(monitors.flatMap((monitor) => monitor.sourceKeys));
  const consumedKeys = new Set(converters.flatMap((converter) => converter.inputSourceKeys));
  sources.forEach((source) => {
    const key = sourceKey(source);
    if (!monitoredKeys.has(key) && !consumedKeys.has(key)) {
      warnings.push(`Robot source ${source.name} is not observed by any monitor.`);
    }
  });
  monitors.forEach((monitor) => {
    if (!monitor.sourceKeys.length) warnings.push(`Monitor ${monitor.id} subscribes to no robot sources.`);
  });
  const chainDownstreams = new Set(converters.flatMap((converter) => converter.inputConverterIds || []));
  converters.forEach((converter) => {
    const chainInputs = converter.inputConverterIds || [];
    if (!converter.inputSourceKeys.length && !chainInputs.length) {
      warnings.push(`Converter ${converter.id} has no inputs — connect robot, monitor, or converter blocks to it.`);
    }
    converter.inputSourceKeys.forEach((key) => {
      if (!monitoredKeys.has(key)) {
        warnings.push(`Converter ${converter.id} consumes ${key}, but no monitor subscribes to it (generation will fail).`);
      }
    });
    chainInputs.forEach((upstreamId) => {
      const upstream = converters.find((item) => item.id === upstreamId);
      if (upstream && upstream.host !== converter.host) {
        warnings.push(`Chained converters ${upstream.id} → ${converter.id} are on different hosts (${upstream.host} → ${converter.host}); chaining is in-process, co-locate them (generation will fail).`);
      }
    });
    if (!converter.verdictServiceIds.length && !chainDownstreams.has(converter.id)) {
      warnings.push(`Converter ${converter.id} feeds no verdict service or downstream converter.`);
    }
  });
  const fedVerdicts = new Set(converters.flatMap((converter) => converter.verdictServiceIds));
  verdictServices.forEach((verdict) => {
    if (!fedVerdicts.has(verdict.id)) warnings.push(`Verdict service ${verdict.id} is not fed by any converter.`);
  });
  return warnings;
}

function renderWarnings() {
  const box = $("topologyWarnings");
  if (!box) return;
  const warnings = topologyWarnings();
  box.innerHTML = warnings.map((warning) => `<div>⚠ ${escapeText(warning)}</div>`).join("");
  box.style.display = warnings.length ? "" : "none";
}

function pruneSelection(layout) {
  const validKeys = new Set([
    ...layout.hostBoxes.map((box) => box.key),
    ...layout.nodes.map((node) => node.key),
  ]);
  [...selectedNodeKeys].forEach((key) => {
    if (!validKeys.has(key)) selectedNodeKeys.delete(key);
  });
  if (selectedLink && ![...layout.runtimeLinks, ...layout.hostLinks].some((link) => link.key === selectedLink)) {
    selectedLink = null;
  }
}

function renderTopology() {
  const layout = topologyLayout();
  pruneSelection(layout);
  const nodes = layout.nodes;
  const visibleEdges = [...layout.runtimeLinks, ...layout.hostLinks];
  const width = Math.max(
    900,
    ...nodes.map((node) => node.x + NODE_WIDTH + 42),
    ...layout.hostBoxes.map((host) => host.x + host.width + 42),
    900,
  );
  const height = Math.max(
    680,
    ...nodes.map((node) => node.y + NODE_HEIGHT + 42),
    ...layout.hostBoxes.map((host) => host.y + host.height + 42),
    680,
  );
  $("edgeLayer").setAttribute("viewBox", `0 0 ${width} ${height}`);
  $("edgeLayer").style.minWidth = `${width * zoom}px`;
  $("edgeLayer").style.minHeight = `${height * zoom}px`;
  $("edgeLayer").style.width = `${width * zoom}px`;
  $("edgeLayer").style.height = `${height * zoom}px`;
  $("nodeLayer").style.minWidth = `${width * zoom}px`;
  $("nodeLayer").style.minHeight = `${height * zoom}px`;
  $("nodeLayer").style.width = `${width * zoom}px`;
  $("nodeLayer").style.height = `${height * zoom}px`;
  $("zoomLevel").textContent = `${Math.round(zoom * 100)}%`;

  const hostHtml = layout.hostBoxes.map((hostBox) => {
    const selected = selectedNode?.kind === "host" && selectedNode.id === hostBox.host;
    const checked = selectedNodeKeys.has(hostBox.key);
    const running = isNodeRunning(hostBox.key);
    return `
      <div class="host-box ${selected ? "selected" : ""} ${checked ? "checked" : ""} ${running ? "running" : ""}"
        role="button"
        tabindex="0"
        style="left:${hostBox.x * zoom}px; top:${hostBox.y * zoom}px; width:${hostBox.width * zoom}px; height:${hostBox.height * zoom}px"
        data-node-kind="host"
        data-node-id="${escapeAttr(hostBox.host)}"
        data-node-key="${escapeAttr(hostBox.key)}">
        <div class="host-title">
          <strong>${escapeText(hostBox.host)}</strong>
          <span>${escapeText(serviceNameForHost(hostBox.host))}</span>
        </div>
      </div>
    `;
  }).join("");

  const nodeHtml = nodes.map((node) => {
    const checked = selectedNodeKeys.has(node.key);
    const running = isNodeRunning(node.key);
    return `
      <div class="node ${node.kind} ${isSelected(node) ? "selected" : ""} ${checked ? "checked" : ""} ${running ? "running" : ""}"
        role="button"
        tabindex="0"
        style="left:${node.x * zoom}px; top:${node.y * zoom}px; transform:scale(${zoom})"
        data-node-kind="${node.kind}"
        data-node-id="${escapeAttr(node.id)}"
        data-node-key="${escapeAttr(node.key)}">
        <span class="node-icon" aria-hidden="true">${iconFor(node.kind)}</span>
        <span class="node-text">
          <span class="node-title">${escapeText(node.title)}</span>
          <span class="node-subtitle">${escapeText(node.subtitle)}</span>
          <span class="node-status">${escapeText(node.status)}</span>
        </span>
      </div>
    `;
  }).join("");
  $("nodeLayer").innerHTML = hostHtml + nodeHtml;

  const edgeMarkup = (edge, points, extraClass, labelText) => {
    const selected = selectedLink === edge.key ? "link-selected" : "";
    const label = polylineLabelPoint(points);
    return `
      <polyline class="edge-hit" data-link-key="${escapeAttr(edge.key)}" points="${points}"></polyline>
      <polyline class="edge ${extraClass} ${edge.payload} ${selected}" points="${points}"></polyline>
      <text class="edge-label ${selected}" data-link-key="${escapeAttr(edge.key)}" x="${label.x}" y="${label.y}">${escapeText(labelText)}</text>
    `;
  };
  const runtimePaths = layout.runtimeLinks.map((edge) => {
    const from = layout.nodeByKey[edge.from];
    const to = layout.nodeByKey[edge.to];
    if (!from || !to) return "";
    return edgeMarkup(edge, edgePoints(from, to), "runtime-edge", edge.payload);
  }).join("");
  const hostPaths = layout.hostLinks.map((edge) => {
    const from = layout.hostById[edge.from];
    const to = layout.hostById[edge.to];
    if (!from || !to) return "";
    const count = edge.pairs.length > 1 ? ` x${edge.pairs.length}` : "";
    return edgeMarkup(edge, hostEdgePoints(from, to), "host-edge", `${edge.payload}${count}`);
  }).join("");
  $("edgeLayer").innerHTML = runtimePaths + hostPaths;
  $("edgeLayer").querySelectorAll("[data-link-key]").forEach((element) => {
    element.addEventListener("click", (event) => {
      event.stopPropagation();
      selectedLink = element.dataset.linkKey;
      selectedNode = null;
      selectedNodeKeys.clear();
      renderAll();
    });
  });

  $("graphSummary").textContent = `${layout.hostBoxes.length} host(s), ${sources.length} robot source(s), ${monitors.length} monitor runtime(s), ${converters.length} converter(s), ${verdictServices.length} verdict service(s), ${visibleEdges.length} visible link(s), ${selectedNodeKeys.size} selected.`;
  renderWarnings();

  document.querySelectorAll("[data-node-kind]").forEach((button) => {
    button.addEventListener("click", (event) => {
      selectedLink = null;
      if (event.shiftKey || event.metaKey || event.ctrlKey) {
        toggleNodeSelection(button.dataset.nodeKey, { kind: button.dataset.nodeKind, id: button.dataset.nodeId });
        return;
      }
      selectedNode = nodeSelectionKind({ kind: button.dataset.nodeKind, id: button.dataset.nodeId });
      selectedNodeKeys = new Set([button.dataset.nodeKey]);
      renderAll();
      renderFocusedLogs();
    });
    button.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      selectedLink = null;
      selectedNode = nodeSelectionKind({ kind: button.dataset.nodeKind, id: button.dataset.nodeId });
      selectedNodeKeys = new Set([button.dataset.nodeKey]);
      renderAll();
      renderFocusedLogs();
    });
  });
  updateToolbarState();
}

function selectedSource() {
  if (selectedNode?.kind !== "robot") return null;
  return sources.find((source) => sourceId(source) === selectedNode.id) || null;
}

function selectedMonitorHost() {
  if (selectedNode?.kind !== "monitor") return "";
  return monitors.find((monitor) => monitor.id === selectedNode.id)?.host || "";
}

function selectedMonitor() {
  if (selectedNode?.kind !== "monitor") return null;
  return monitors.find((monitor) => monitor.id === selectedNode.id) || null;
}

function paramValueInput(target, row, index) {
  const type = row.type || "auto";
  if (type === "bool") {
    return `<label class="inline-check"><input data-param-value="${target}:${index}" type="checkbox" ${String(row.value).toLowerCase() === "true" ? "checked" : ""}> enabled</label>`;
  }
  if (type === "json") {
    return `<textarea data-param-value="${target}:${index}" spellcheck="false">${escapeText(row.value ?? "")}</textarea>`;
  }
  if (type === "enum") {
    return `<select data-param-value="${target}:${index}">
      ${(row.options || []).map((option) => `<option value="${escapeAttr(option)}" ${String(option) === String(row.value) ? "selected" : ""}>${escapeText(option)}</option>`).join("")}
    </select>`;
  }
  const inputType = type === "number" || type === "int" ? "number" : "text";
  return `<input data-param-value="${target}:${index}" type="${inputType}" value="${escapeAttr(row.value ?? "")}" spellcheck="false">`;
}

function formValueForDefault(value, type) {
  if (type === "json") return JSON.stringify(value ?? null);
  if (type === "bool") return value ? "true" : "false";
  if (value === null || value === undefined) return "";
  return String(value);
}

function manifestParamRows(manifest) {
  return (manifest.params || []).map((param) => ({
    key: param.key,
    label: param.label || param.key,
    value: formValueForDefault(param.default, param.type || "string"),
    type: param.type || "string",
    required: Boolean(param.required),
    options: (param.options || []).slice(),
    schema: true,
  }));
}

function manifestPicker(id, kind, classPath) {
  const rows = manifests.filter((manifest) => manifest.kind === kind);
  if (!rows.length) return "";
  const matched = rows.find((manifest) => manifest.class_path === classPath);
  return `
    <label>Plugin
      <select id="${id}">
        <option value="">— custom class path —</option>
        ${rows.map((manifest) => `<option value="${escapeAttr(manifest.id)}" ${manifest === matched ? "selected" : ""}>${escapeText(manifest.name || manifest.id)}</option>`).join("")}
      </select>
    </label>
  `;
}

function paramRows(target, rows) {
  if (!rows.length) return `<div class="empty">No parameters.</div>`;
  return rows.map((row, index) => `
    <div class="param-row">
      <label>
        Key
        <input data-param-key="${target}:${index}" value="${escapeAttr(row.key || "")}" ${row.schema ? "readonly" : ""} spellcheck="false">
      </label>
      <label>
        Value
        ${paramValueInput(target, row, index)}
      </label>
      <div class="param-actions">
        <select data-param-type="${target}:${index}" ${row.schema ? "disabled" : ""}>
          ${["auto", "string", "number", "int", "bool", "enum", "json"].map((type) => `<option value="${type}" ${type === (row.type || "auto") ? "selected" : ""}>${type}</option>`).join("")}
        </select>
        <button data-remove-param="${target}:${index}" type="button">Remove</button>
      </div>
    </div>
  `).join("");
}

function hasMqttTransport() {
  return topologyModel().hostLinks.some((link) => link.payload === "records" || link.payload === "dsl");
}

function configOverview() {
  return `
    <p class="notice">Create a host first, then select it to add robot, monitor, converter, or verdict runtimes.</p>
    <hr>
    <h3>Hosts</h3>
    ${hosts.length ? hosts.map((host) => `<label class="inline-check"><span>${escapeText(host)}</span></label>`).join("") : `<div class="empty">No hosts yet.</div>`}
  `;
}

function robotConfig(source) {
  const subscribers = monitors.filter((monitor) => monitor.sourceKeys.includes(sourceKey(source)));
  return `
    <p class="notice">A robot is an external ROS system — what it publishes is a property of the robot, not monitor configuration. Use Scan graph to discover its sources, then connect them to monitors.</p>
    <label>Advertised source<input value="${escapeAttr(`${source.name} (${source.source_kind}, ${source.interface})`)}" readonly></label>
    <label>Host<input id="sourceHost" value="${escapeAttr(source.host)}" spellcheck="false"></label>
    <label>Observed by<input value="${escapeAttr(subscribers.length ? subscribers.map((monitor) => monitor.id).join(", ") : "no monitor yet")}" readonly></label>
    <h3>Robot container</h3>
    <label>Robot Dockerfile<input id="robotDockerfile" value="${escapeAttr(robotDockerfile)}" spellcheck="false"></label>
    <label>Start command<textarea id="robotCommand" spellcheck="false">${escapeText(robotCommand)}</textarea></label>
    <details class="advanced">
      <summary>Edit source declaration (offline planning)</summary>
      <p class="notice">Normally the declaration comes from Scan graph. Edit it only when planning a deployment before the robot exists.</p>
      <label>Source kind
        <select id="sourceKind">
          ${["topic", "service", "action"].map((kind) => `<option value="${kind}" ${kind === source.source_kind ? "selected" : ""}>${kind}</option>`).join("")}
        </select>
      </label>
      <label>ROS name<input id="sourceName" value="${escapeAttr(source.name)}" spellcheck="false"></label>
      <label>Interface<input id="sourceInterface" value="${escapeAttr(source.interface)}" spellcheck="false"></label>
    </details>
  `;
}

function monitorConfig(monitor) {
  return `
    <p class="notice">A monitor runtime subscribes to selected robot sources and emits records.</p>
    <label>Monitor id<input id="monitorId" value="${escapeAttr(monitor.id)}" spellcheck="false"></label>
    <label>Host<input id="monitorHost" value="${escapeAttr(monitor.host)}" spellcheck="false"></label>
    <h3>Subscribed sources</h3>
    ${sources.length ? sources.map((source) => `
      <label class="inline-check">
        <input type="checkbox" data-monitor-source="${escapeAttr(sourceKey(source))}" ${monitor.sourceKeys.includes(sourceKey(source)) ? "checked" : ""}>
        <span>${escapeText(source.name)}</span>
      </label>`).join("") : `<div class="empty">Add robots first.</div>`}
  `;
}

function converterConfig(converter) {
  return `
    <label>Converter id<input id="converterId" value="${escapeAttr(converter.id)}" spellcheck="false"></label>
    ${manifestPicker("converterManifest", "converter", converter.class_path)}
    <label>Class path<input id="converterClass" value="${escapeAttr(converter.class_path)}" spellcheck="false"></label>
    <label>Host<input id="converterHost" value="${escapeAttr(converter.host)}" spellcheck="false"></label>
    <h3>Input robots</h3>
    ${sources.length ? sources.map((source) => `
      <label class="inline-check">
        <input type="checkbox" data-use-source="${escapeAttr(sourceKey(source))}" ${converter.inputSourceKeys.includes(sourceKey(source)) ? "checked" : ""}>
        <span>${escapeText(source.name)}</span>
      </label>`).join("") : `<div class="empty">Add robots first.</div>`}
    <h3>Input converters (chain)</h3>
    ${converters.filter((item) => item.id !== converter.id).length ? converters.filter((item) => item.id !== converter.id).map((item) => `
      <label class="inline-check">
        <input type="checkbox" data-chain-converter="${escapeAttr(item.id)}" ${(converter.inputConverterIds || []).includes(item.id) ? "checked" : ""}>
        <span>${escapeText(item.id)} (${escapeText(item.host)})</span>
      </label>`).join("") : `<div class="empty">Add another converter to build a filter pipeline.</div>`}
    <h3>Verdict services</h3>
    ${verdictServices.length ? verdictServices.map((verdict) => `
      <label class="inline-check">
        <input type="checkbox" data-use-verdict="${escapeAttr(verdict.id)}" ${converter.verdictServiceIds.includes(verdict.id) ? "checked" : ""}>
        <span>${escapeText(verdict.id)}</span>
      </label>`).join("") : `<div class="empty">Add verdict services first.</div>`}
    <h3>Parameters</h3>
    <div class="param-list">${paramRows("converter", converter.params)}</div>
    <div class="config-actions">
      <button id="addConverterParam" type="button">+ Param</button>
    </div>
  `;
}

function verdictConfig(verdict) {
  return `
    <label>Verdict id<input id="verdictId" value="${escapeAttr(verdict.id)}" spellcheck="false"></label>
    ${manifestPicker("verdictManifest", "verdict", verdict.class_path)}
    <label>Class path<input id="verdictClass" value="${escapeAttr(verdict.class_path)}" spellcheck="false"></label>
    <label>Host<input id="verdictHost" value="${escapeAttr(verdict.host)}" spellcheck="false"></label>
    <h3>Fed by converters</h3>
    ${converters.length ? converters.map((converter) => `
      <label class="inline-check">
        <input type="checkbox" data-fed-by-converter="${escapeAttr(converter.id)}" ${converter.verdictServiceIds.includes(verdict.id) ? "checked" : ""}>
        <span>${escapeText(converter.id)}</span>
      </label>`).join("") : `<div class="empty">Add converters first.</div>`}
    <h3>Parameters</h3>
    <div class="param-list">${paramRows("verdict", verdict.params)}</div>
    <div class="config-actions">
      <button id="addVerdictParam" type="button">+ Param</button>
    </div>
  `;
}

const LINK_EXPLANATIONS = {
  ros: "DDS subscription: the monitor runtime subscribes to this ROS source.",
  records: "DataRecords flow from the monitor to the converter. Cross-host, this becomes an MQTT link over the shared broker.",
  dsl: "The converter's DSL output feeds the verdict service. Cross-host, this becomes an MQTT link over the shared broker.",
  chain: "Converter chaining: the upstream converter's output feeds the downstream converter in-process. Both converters must run on the same host.",
};

function linkConfig(link) {
  const pairs = link.pairs || [link];
  const isHostLink = Boolean(link.pairs);
  const removalNote = link.payload === "records"
    ? `<p class="notice">Removing a records link removes the monitor's subscribed sources from the converter's inputs.</p>`
    : "";
  return `
    <p class="notice">${escapeText(LINK_EXPLANATIONS[link.payload] || "Data link.")}</p>
    <label>Payload<input value="${escapeAttr(link.payload)}" readonly></label>
    <label>From<input value="${escapeAttr(isHostLink ? `host ${link.from}` : labelForNodeKey(link.from))}" readonly></label>
    <label>To<input value="${escapeAttr(isHostLink ? `host ${link.to}` : labelForNodeKey(link.to))}" readonly></label>
    ${(link.payload === "records" || link.payload === "dsl") && isHostLink ? `
      <label>Broker<input value="${escapeAttr(`mqtt://${brokerHost}:${brokerPort}`)}" readonly></label>` : ""}
    ${removalNote}
    <h3>Runtime connection(s)</h3>
    ${pairs.map((pair, index) => `
      <div class="link-row">
        <span>${escapeText(describeLinkPair(pair))}</span>
      </div>
    `).join("")}
  `;
}

function brokerConfig() {
  return `
    <p class="notice">This broker is used for cross-host record links. Select source blocks, click a converter, then use Connect to target to create broker fan-in.</p>
    <label>Broker host<input id="brokerHostConfig" value="${escapeAttr(brokerHost)}" spellcheck="false"></label>
    <label>Port<input id="brokerPortConfig" value="${escapeAttr(brokerPort)}" type="number"></label>
  `;
}

function hostConfig(host) {
  const layout = topologyLayout();
  const hostBox = layout.hostBoxes.find((box) => box.host === host);
  const runtimeRows = (hostBox?.nodes || []).sort((a, b) => a.stage - b.stage || a.title.localeCompare(b.title));
  return `
    <p class="notice">A host is the deployment container boundary. Runtime logs and lifecycle are shared by all non-robot runtimes in this host.</p>
    <label>Host id<input id="hostIdConfig" value="${escapeAttr(host)}" spellcheck="false"></label>
    <label>Compose service<input value="${escapeAttr(serviceNameForHost(host))}" readonly></label>
    <h3>Runtimes</h3>
    ${runtimeRows.length ? runtimeRows.map((node) => `
      <button class="runtime-jump" data-jump-node="${escapeAttr(node.key)}" type="button">
        ${escapeText(iconFor(node.kind))} ${escapeText(node.title)}
      </button>
    `).join("") : `<div class="empty">No runtime in this host.</div>`}
  `;
}

function renderConfig() {
  const form = $("configForm");
  const link = findSelectedLink();
  if (link) {
    $("selectionHint").textContent = `Link ${link.from} → ${link.to} (${link.payload})`;
    form.innerHTML = linkConfig(link);
    bindConfigEvents();
    updateEditorTarget();
    return;
  }
  const source = selectedSource();
  const converter = selectedNode?.kind === "converter" ? converters.find((item) => item.id === selectedNode.id) : null;
  const verdict = selectedNode?.kind === "verdict" ? verdictServices.find((item) => item.id === selectedNode.id) : null;
  const monitor = selectedMonitor();
  const host = selectedNode?.kind === "host" ? selectedNode.id : "";

  if (source) {
    $("selectionHint").textContent = `Robot source on ${source.host}`;
    form.innerHTML = robotConfig(source);
  } else if (host) {
    $("selectionHint").textContent = `Host ${host}`;
    form.innerHTML = hostConfig(host);
  } else if (monitor) {
    $("selectionHint").textContent = `Monitor ${monitor.id}`;
    form.innerHTML = monitorConfig(monitor);
  } else if (converter) {
    $("selectionHint").textContent = `Converter ${converter.id}`;
    form.innerHTML = converterConfig(converter);
  } else if (verdict) {
    $("selectionHint").textContent = `Verdict service ${verdict.id}`;
    form.innerHTML = verdictConfig(verdict);
  } else {
    $("selectionHint").textContent = "Select a block on the playground.";
    form.innerHTML = configOverview();
  }
  bindConfigEvents();
  updateEditorTarget();
}

function bindConfigEvents() {
  const bind = (id, eventName, fn) => {
    const el = $(id);
    if (el) el.addEventListener(eventName, fn);
  };
  bind("sourceKind", "change", () => {
    const source = selectedSource();
    if (source) {
      const oldKey = sourceKey(source);
      source.source_kind = $("sourceKind").value;
      replaceSourceKey(oldKey, sourceKey(source));
    }
    selectedNode = source ? { kind: "robot", id: sourceId(source) } : selectedNode;
    renderAll();
  });
  bind("sourceName", "change", () => {
    const source = selectedSource();
    if (source) {
      const oldKey = sourceKey(source);
      source.name = $("sourceName").value.trim() || source.name;
      replaceSourceKey(oldKey, sourceKey(source));
    }
    selectedNode = source ? { kind: "robot", id: sourceId(source) } : selectedNode;
    renderAll();
  });
  bind("sourceInterface", "change", () => {
    const source = selectedSource();
    if (source) source.interface = $("sourceInterface").value.trim() || source.interface;
    renderAll();
  });
  bind("sourceHost", "change", () => {
    const source = selectedSource();
    if (source) source.host = ensureHost($("sourceHost").value, source.host);
    renderAll();
  });
  bind("robotDockerfile", "input", () => { robotDockerfile = $("robotDockerfile").value; updateEditorTarget(); });
  bind("robotCommand", "input", () => { robotCommand = $("robotCommand").value; });

  bind("monitorId", "change", () => {
    const monitor = selectedMonitor();
    if (!monitor) return;
    const oldId = monitor.id;
    monitor.id = uniqueRuntimeId($("monitorId").value, monitors.filter((item) => item !== monitor).map((item) => item.id));
    selectedNode = { kind: "monitor", id: monitor.id };
    selectedNodeKeys.delete(`monitor:${oldId}`);
    selectedNodeKeys.add(monitorKey(monitor));
    renderAll();
  });
  bind("monitorHost", "change", () => {
    const monitor = selectedMonitor();
    if (!monitor) return;
    monitor.host = ensureHost($("monitorHost").value, monitor.host);
    renderAll();
  });
  bind("hostIdConfig", "change", () => {
    const oldHost = selectedNode?.kind === "host" ? selectedNode.id : "";
    if (!oldHost) return;
    const newHost = slug($("hostIdConfig").value, oldHost);
    if (newHost === oldHost) return;
    hosts = [...new Set(hosts.map((host) => (host === oldHost ? newHost : host)))];
    sources.forEach((source) => {
      if (source.host === oldHost) source.host = newHost;
    });
    monitors.forEach((monitor) => {
      if (monitor.host === oldHost) monitor.host = newHost;
    });
    converters.forEach((converter) => {
      if (converter.host === oldHost) converter.host = newHost;
    });
    verdictServices.forEach((verdict) => {
      if (verdict.host === oldHost) verdict.host = newHost;
    });
    selectedNode = { kind: "host", id: newHost };
    selectedNodeKeys = new Set([`host:${newHost}`]);
    renderAll();
  });

  bind("converterId", "change", () => {
    const converter = selectedConverter();
    if (!converter) return;
    const oldId = converter.id;
    converter.id = uniqueRuntimeId($("converterId").value || oldId, converters.filter((item) => item !== converter).map((item) => item.id));
    converters.forEach((item) => {
      item.inputConverterIds = (item.inputConverterIds || []).map((id) => id === oldId ? converter.id : id);
    });
    selectedNode = { kind: "converter", id: converter.id };
    selectedNodeKeys.delete(`converter:${oldId}`);
    selectedNodeKeys.add(`converter:${converter.id}`);
    renderAll();
  });
  bind("converterManifest", "change", () => {
    const converter = selectedConverter();
    const manifest = manifests.find((item) => item.id === $("converterManifest").value);
    if (!converter || !manifest) return;
    converter.class_path = manifest.class_path;
    converter.params = manifestParamRows(manifest);
    renderAll();
  });
  bind("verdictManifest", "change", () => {
    const verdict = selectedVerdict();
    const manifest = manifests.find((item) => item.id === $("verdictManifest").value);
    if (!verdict || !manifest) return;
    verdict.class_path = manifest.class_path;
    verdict.params = manifestParamRows(manifest);
    renderAll();
  });
  bind("converterClass", "input", () => {
    const converter = selectedConverter();
    if (converter) converter.class_path = $("converterClass").value.trim();
    updateEditorTarget();
    renderTopology();
  });
  bind("converterHost", "change", () => {
    const converter = selectedConverter();
    if (converter) converter.host = ensureHost($("converterHost").value, converter.host);
    renderAll();
  });
  bind("addConverterParam", "click", () => {
    const converter = selectedConverter();
    if (converter) converter.params.push({ key: "", value: "", type: "auto" });
    renderAll();
  });

  bind("verdictId", "change", () => {
    const verdict = selectedVerdict();
    if (!verdict) return;
    const oldId = verdict.id;
    verdict.id = uniqueRuntimeId($("verdictId").value || oldId, verdictServices.filter((item) => item !== verdict).map((item) => item.id));
    converters.forEach((converter) => {
      converter.verdictServiceIds = converter.verdictServiceIds.map((id) => id === oldId ? verdict.id : id);
    });
    selectedNode = { kind: "verdict", id: verdict.id };
    selectedNodeKeys.delete(`verdict:${oldId}`);
    selectedNodeKeys.add(`verdict:${verdict.id}`);
    renderAll();
  });
  bind("verdictClass", "input", () => {
    const verdict = selectedVerdict();
    if (verdict) verdict.class_path = $("verdictClass").value.trim();
    updateEditorTarget();
    renderTopology();
  });
  bind("verdictHost", "change", () => {
    const verdict = selectedVerdict();
    if (verdict) verdict.host = ensureHost($("verdictHost").value, verdict.host);
    renderAll();
  });
  bind("addVerdictParam", "click", () => {
    const verdict = selectedVerdict();
    if (verdict) verdict.params.push({ key: "", value: "", type: "auto" });
    renderAll();
  });
  bind("brokerHostConfig", "input", () => {
    brokerHost = $("brokerHostConfig").value.trim() || "127.0.0.1";
    renderTopology();
  });
  bind("brokerPortConfig", "input", () => {
    brokerPort = Number($("brokerPortConfig").value) || 1883;
    renderTopology();
  });

  document.querySelectorAll("[data-use-source]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const converter = selectedConverter();
      if (!converter) return;
      const key = checkbox.dataset.useSource;
      if (checkbox.checked && !converter.inputSourceKeys.includes(key)) converter.inputSourceKeys.push(key);
      if (!checkbox.checked) converter.inputSourceKeys = converter.inputSourceKeys.filter((item) => item !== key);
      renderTopology();
    });
  });
  document.querySelectorAll("[data-chain-converter]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const converter = selectedConverter();
      if (!converter) return;
      const id = checkbox.dataset.chainConverter;
      converter.inputConverterIds = converter.inputConverterIds || [];
      if (checkbox.checked && !converter.inputConverterIds.includes(id)) converter.inputConverterIds.push(id);
      if (!checkbox.checked) converter.inputConverterIds = converter.inputConverterIds.filter((item) => item !== id);
      renderTopology();
    });
  });
  document.querySelectorAll("[data-use-verdict]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const converter = selectedConverter();
      if (!converter) return;
      const id = checkbox.dataset.useVerdict;
      if (checkbox.checked && !converter.verdictServiceIds.includes(id)) converter.verdictServiceIds.push(id);
      if (!checkbox.checked) converter.verdictServiceIds = converter.verdictServiceIds.filter((item) => item !== id);
      renderTopology();
    });
  });
  document.querySelectorAll("[data-fed-by-converter]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const verdict = selectedVerdict();
      const converter = converters.find((item) => item.id === checkbox.dataset.fedByConverter);
      if (!verdict || !converter) return;
      if (checkbox.checked && !converter.verdictServiceIds.includes(verdict.id)) converter.verdictServiceIds.push(verdict.id);
      if (!checkbox.checked) converter.verdictServiceIds = converter.verdictServiceIds.filter((id) => id !== verdict.id);
      renderTopology();
    });
  });
  document.querySelectorAll("[data-monitor-source]").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const monitor = selectedMonitor();
      if (!monitor) return;
      const key = checkbox.dataset.monitorSource;
      if (checkbox.checked && !monitor.sourceKeys.includes(key)) monitor.sourceKeys.push(key);
      if (!checkbox.checked) monitor.sourceKeys = monitor.sourceKeys.filter((item) => item !== key);
      renderTopology();
    });
  });
  document.querySelectorAll("[data-param-key]").forEach((input) => {
    input.addEventListener("input", () => updateParam(input.dataset.paramKey, "key", input.value));
  });
  document.querySelectorAll("[data-param-value]").forEach((input) => {
    const eventName = input.type === "checkbox" ? "change" : "input";
    input.addEventListener(eventName, () => updateParam(input.dataset.paramValue, "value", input.type === "checkbox" ? String(input.checked) : input.value));
  });
  document.querySelectorAll("[data-param-type]").forEach((select) => {
    select.addEventListener("change", () => updateParam(select.dataset.paramType, "type", select.value));
  });
  document.querySelectorAll("[data-remove-param]").forEach((button) => {
    button.addEventListener("click", () => {
      const [target, rawIndex] = button.dataset.removeParam.split(":");
      paramArray(target).splice(Number(rawIndex), 1);
      renderAll();
    });
  });
  document.querySelectorAll("[data-jump-node]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.jumpNode;
      const node = topologyLayout().nodeByKey[key];
      if (!node) return;
      selectedNode = nodeSelectionKind(node);
      selectedNodeKeys = new Set([key]);
      renderAll();
      renderFocusedLogs();
    });
  });
}

function paramArray(target) {
  return target === "converter" ? selectedConverter()?.params || [] : selectedVerdict()?.params || [];
}

function replaceSourceKey(oldKey, newKey) {
  monitors.forEach((monitor) => {
    monitor.sourceKeys = monitor.sourceKeys.map((key) => key === oldKey ? newKey : key);
  });
  converters.forEach((converter) => {
    converter.inputSourceKeys = converter.inputSourceKeys.map((key) => key === oldKey ? newKey : key);
  });
}

function updateParam(address, field, value) {
  const [target, rawIndex] = address.split(":");
  const row = paramArray(target)[Number(rawIndex)];
  if (row) row[field] = value;
}

function updateEditorTarget() {
  let path = "";
  if (selectedNode?.kind === "robot") path = robotDockerfile;
  if (selectedNode?.kind === "monitor") path = "monitor/monitor_node.py";
  if (selectedNode?.kind === "converter") path = classPathToFile(selectedConverter()?.class_path);
  if (selectedNode?.kind === "verdict") path = classPathToFile(selectedVerdict()?.class_path);
  if (selectedNode?.kind === "host") path = `generated/showcase/${slug(selectedNode.id, "host")}.yaml`;
  $("filePath").value = path;
  if (path && path !== editorTargetPath) {
    editorTargetPath = path;
    $("codeEditor").value = "";
    $("fileStatus").textContent = `Loading ${path}...`;
    loadFile();
  }
  if (!path) {
    editorTargetPath = "";
    $("filePath").value = "";
    $("codeEditor").value = "";
    $("fileStatus").textContent = "Select a block with an editable file.";
  }
}

async function loadFile() {
  const path = $("filePath").value.trim();
  if (!path) return;
  $("fileStatus").textContent = "Loading...";
  try {
    const data = await api(`/api/files?path=${encodeURIComponent(path)}`);
    editorTargetPath = data.path;
    $("codeEditor").value = data.content;
    $("fileStatus").textContent = `Loaded ${data.path}`;
  } catch (error) {
    $("fileStatus").textContent = error.message;
  }
}

async function saveFile() {
  const path = $("filePath").value.trim();
  if (!path) return;
  $("fileStatus").textContent = "Saving...";
  try {
    const data = await api("/api/files", {
      method: "POST",
      body: JSON.stringify({ path, content: $("codeEditor").value }),
    });
    $("fileStatus").textContent = `Saved ${data.path}`;
  } catch (error) {
    $("fileStatus").textContent = error.message;
  }
}

function switchEditorTab(name) {
  document.querySelectorAll(".editor-tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.editorTab === name);
  });
  document.querySelectorAll(".editor-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `editor-${name}`);
  });
}

function renderDiscoveryGroup(title, rows, kind) {
  if (!rows.length) return "";
  return `
    <div class="discovered-group">
      <h3>${title}</h3>
      ${rows.map((row) => `
        <div class="discovered-row">
          <strong>${kind}</strong>
          <span>${escapeText(row.name)}</span>
          <code>${escapeText(row.interface)}</code>
          <button data-add-discovered="${escapeAttr(JSON.stringify({ ...row, source_kind: kind }))}" type="button">Add</button>
        </div>
      `).join("")}
    </div>
  `;
}

function renderGraph(data) {
  $("graphResults").innerHTML = [
    renderDiscoveryGroup("Topics", data.topics || [], "topic"),
    renderDiscoveryGroup("Services", data.services || [], "service"),
    renderDiscoveryGroup("Actions", data.actions || [], "action"),
  ].join("") || `<div class="notice">No graph resources found.</div>`;
  document.querySelectorAll("[data-add-discovered]").forEach((button) => {
    button.addEventListener("click", () => addDiscoveredSource(JSON.parse(button.dataset.addDiscovered)));
  });
}

function ensureDiscoveredSource(seed, fallbackHost) {
  const normalized = {
    source_kind: seed.source_kind || "topic",
    name: seed.name,
    interface: seed.interface || "",
  };
  const key = sourceKey(normalized);
  let source = sources.find((item) => sourceKey(item) === key);
  let created = false;
  if (!source) {
    source = { ...normalized, host: ensureHost(fallbackHost) };
    sources.push(source);
    created = true;
  }
  return { source, key, created };
}

function addDiscoveredSource(seed) {
  if (selectedNode?.kind === "monitor") {
    const monitor = monitors.find((item) => item.id === selectedNode.id);
    if (!monitor) return;
    const { key, created } = ensureDiscoveredSource(seed, monitor.host);
    if (!monitor.sourceKeys.includes(key)) monitor.sourceKeys.push(key);
    $("scanStatus").textContent = created
      ? `Subscribed ${monitor.id} to ${seed.name}. A robot block was created on ${monitor.host} — move it to the robot's host if needed.`
      : `Subscribed ${monitor.id} to ${seed.name}.`;
    renderAll();
    return;
  }
  if (selectedNode?.kind === "converter") {
    const converter = converters.find((item) => item.id === selectedNode.id);
    if (!converter) return;
    const { key, created } = ensureDiscoveredSource(seed, converter.host);
    if (!converter.inputSourceKeys.includes(key)) converter.inputSourceKeys.push(key);
    $("scanStatus").textContent = created
      ? `Added ${seed.name} as an input of ${converter.id}. A robot block was created on ${converter.host} — move it to the robot's host if needed.`
      : `Added ${seed.name} as an input of ${converter.id}.`;
    renderAll();
    return;
  }
  const robotHost = selectedNode?.kind === "robot"
    ? sources.find((item) => sourceId(item) === selectedNode.id)?.host
    : "";
  const targetHost = selectedHost() || robotHost;
  if (!targetHost) {
    $("scanStatus").textContent = "Select where this source goes first: a host or robot (declares the source there), or a monitor / converter (subscribes it).";
    return;
  }
  addRobot({ ...seed, host: targetHost });
  $("scanStatus").textContent = `Declared ${seed.name} as a robot source on ${targetHost}. Connect it to a monitor to observe it.`;
}

function applyTemplate(templateId, options = {}) {
  const plugin = plugins.find((item) => item.id === templateId);
  if (!plugin) return;
  hosts = (plugin.hosts || []).slice();
  sources = [];
  monitors = [];
  converters = [];
  verdictServices = [];
  selectedNodeKeys.clear();
  if (templateId === "blank") {
    selectedNode = null;
    $("scanStatus").textContent = "";
    $("graphResults").innerHTML = "";
    renderAll();
    return;
  }
  const placement = plugin.placement || {};
  if (plugin.robot_command) robotCommand = plugin.robot_command;
  const converterId = plugin.converter_manifest || (templateId === "blank" ? "custom-converter" : templateId);
  const verdictId = plugin.verdict_manifest || (templateId === "blank" ? "custom-verdict" : `${templateId}-verdict`);
  const verdict = {
    id: slug(verdictId, "verdict_1"),
    class_path: plugin.verdict || "custom.threshold:ThresholdVerdict",
    params: structuredClone(plugin.verdict_params || []),
    host: ensureHost(placement.verdict || hosts[0]),
  };
  verdictServices.push(verdict);
  const converter = {
    id: slug(converterId, "converter_1"),
    class_path: plugin.converter || "custom.rule_based:RuleBasedConverter",
    params: structuredClone(plugin.converter_params || []),
    host: ensureHost(placement.converter || hosts[0]),
    inputSourceKeys: [],
    inputConverterIds: [],
    verdictServiceIds: [verdict.id],
  };
  converters.push(converter);
  if (options.applySources !== false) {
    const sourcesByHost = new Map();
    (plugin.sources || []).forEach((source) => {
      const normalized = {
        source_kind: source.source_kind || "topic",
        name: source.name || "/cmd_vel",
        interface: source.interface || "geometry_msgs/msg/Twist",
        host: ensureHost(source.host || hosts[0] || "robot"),
      };
      sources.push(normalized);
      converter.inputSourceKeys.push(sourceKey(normalized));
      if (!sourcesByHost.has(normalized.host)) sourcesByHost.set(normalized.host, []);
      sourcesByHost.get(normalized.host).push(sourceKey(normalized));
    });
    sourcesByHost.forEach((sourceKeys, host) => {
      monitors.push({
        id: uniqueRuntimeId(`monitor_${host}`, monitors.map((monitor) => monitor.id)),
        host,
        sourceKeys,
      });
    });
  }
  selectedNode = converters.length ? { kind: "converter", id: converters[0].id } : null;
  selectedNodeKeys = selectedNode ? new Set([`converter:${converters[0].id}`]) : new Set();
  renderAll();
}

function renderGenerated(data) {
  if (!data) return;
  generated = true;
}

function applyRunState(data) {
  generated = data.generated || generated;
  runActive = Boolean(data.running);
  renderTopology();
}

function applyRobotState(data) {
  robotRunning = Boolean(data.running);
  if (!robotRunning) {
    [...runningNodeKeys].filter((key) => key.startsWith("source:")).forEach((key) => runningNodeKeys.delete(key));
  }
  renderTopology();
}

function appendLogRows(rows) {
  if (!rows.length) return;
  const freshRows = rows.filter((row) => Number(row.id) > lastLogId);
  if (!freshRows.length) return;
  runLogRows.push(...freshRows);
  runLogRows = runLogRows.slice(-1000);
  lastLogId = Number(freshRows[freshRows.length - 1].id);
  renderFocusedLogs();
}

function appendRobotLogRows(rows) {
  if (!rows.length) return;
  const freshRows = rows.filter((row) => Number(row.id) > lastRobotLogId);
  if (!freshRows.length) return;
  robotLogRows.push(...freshRows);
  robotLogRows = robotLogRows.slice(-500);
  lastRobotLogId = Number(freshRows[freshRows.length - 1].id);
  renderFocusedLogs();
}

function renderFocusedLogs() {
  const key = primarySelectedKey();
  const logs = $("logs");
  if (!key) {
    logs.textContent = "Select a block to view its live output.";
    $("logStatus").textContent = "";
    return;
  }
  let rows = [];
  if (key.startsWith("source:")) {
    rows = robotLogRows;
  } else {
    const terms = logTermsForKey(key);
    rows = runLogRows.filter((row) => {
      const line = String(row.line || "").toLowerCase();
      return terms.some((term) => line.includes(term));
    });
    if (!rows.length && runLogRows.length && runningNodeKeys.has(key)) {
      rows = runLogRows.slice(-120);
    }
  }
  const label = labelForNodeKey(key);
  logs.textContent = rows.length
    ? rows.slice(-300).map((row) => row.line).join("\n")
    : `No live output for ${label} yet.`;
  logs.scrollTop = logs.scrollHeight;
  $("logStatus").textContent = `${label} · ${rows.length} line(s)`;
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
  if (!window.EventSource || eventSource) return;
  eventSource = new EventSource("/api/events");
  eventSource.addEventListener("open", () => { $("logStatus").textContent = "connected"; });
  eventSource.addEventListener("error", () => { $("logStatus").textContent = "SSE reconnecting"; });
  eventSource.addEventListener("run_state", (event) => {
    const data = parseEventData(event);
    if (data) applyRunState(data);
  });
  eventSource.addEventListener("robot_state", (event) => {
    const data = parseEventData(event);
    if (data) applyRobotState(data);
  });
  eventSource.addEventListener("logs", (event) => {
    const data = parseEventData(event);
    if (data) appendLogRows(data.logs || []);
  });
  eventSource.addEventListener("log", (event) => {
    const data = parseEventData(event);
    if (data) appendLogRows([data]);
  });
  eventSource.addEventListener("robot_logs", (event) => {
    const data = parseEventData(event);
    if (data) appendRobotLogRows(data.logs || []);
  });
  eventSource.addEventListener("robot_log", (event) => {
    const data = parseEventData(event);
    if (data) appendRobotLogRows([data]);
  });
  eventSource.addEventListener("generated", (event) => {
    const data = parseEventData(event);
    if (data) renderGenerated(data);
  });
}

async function startRobot() {
  switchEditorTab("logs");
  $("logs").textContent = "Building image and starting robot container...";
  lastRobotLogId = 0;
  try {
    const data = await api("/api/robots/start", {
      method: "POST",
      body: JSON.stringify({ dockerfile: robotDockerfile, command: robotCommand }),
    });
    applyRobotState(data);
    selectedKeys().filter((key) => key.startsWith("source:")).forEach((key) => runningNodeKeys.add(key));
    renderFocusedLogs();
  } catch (error) {
    if (String(error.message).includes("already running")) {
      selectedKeys().filter((key) => key.startsWith("source:")).forEach((key) => runningNodeKeys.add(key));
      renderTopology();
      renderFocusedLogs();
      return;
    }
    $("logs").textContent = error.message;
  }
}

async function stopRobot() {
  try {
    const data = await api("/api/robots/stop", { method: "POST", body: "{}" });
    lastRobotLogId = 0;
    applyRobotState(data);
    selectedKeys().filter((key) => key.startsWith("source:")).forEach((key) => runningNodeKeys.delete(key));
    renderFocusedLogs();
  } catch (error) {
    $("logs").textContent += `\n${error.message}`;
  }
}

async function startSelectedComponents() {
  switchEditorTab("logs");
  const keys = selectedKeys();
  if (!keys.length) {
    $("logs").textContent = "Select one or more blocks before starting.";
    return;
  }
  const robotKeys = keys.filter((key) => key.startsWith("source:"));
  const runtimeKeys = keys.filter((key) => !key.startsWith("source:"));
  if (robotKeys.length) {
    await startRobot();
  }
  if (!runtimeKeys.length) return;
  const targetServices = servicesForKeys(runtimeKeys);
  $("logs").textContent = runActive
    ? `Runtime stack is already active. Focusing ${labelForNodeKey(primarySelectedKey())}.`
    : `Generating runtime files and starting ${targetServices.join(", ")}...`;
  try {
    const data = await api("/api/runs/start", {
      method: "POST",
      body: JSON.stringify({ ...currentPayload(), target_services: targetServices }),
    });
    renderGenerated(data.generated_files);
    applyRunState(data);
    runtimeKeys.forEach((key) => {
      const host = hostForNodeKey(key);
      if (host) setHostRunning(host, true);
      runningNodeKeys.add(key);
    });
    renderTopology();
    renderFocusedLogs();
  } catch (error) {
    $("logs").textContent = error.message;
  }
}

async function stopSelectedComponents() {
  const keys = selectedKeys();
  if (!keys.length) {
    $("logs").textContent = "Select one or more blocks before stopping.";
    return;
  }
  const robotKeys = keys.filter((key) => key.startsWith("source:"));
  const runtimeKeys = keys.filter((key) => !key.startsWith("source:"));
  if (robotKeys.length) {
    await stopRobot();
  }
  if (!runtimeKeys.length) return;
  try {
    const targetServices = servicesForKeys(runtimeKeys);
    const data = await api("/api/runs/stop", {
      method: "POST",
      body: JSON.stringify({ target_services: targetServices }),
    });
    applyRunState(data);
    runtimeKeys.forEach((key) => {
      const host = hostForNodeKey(key);
      if (host) setHostRunning(host, false);
      runningNodeKeys.delete(key);
    });
    renderTopology();
    renderFocusedLogs();
  } catch (error) {
    $("logs").textContent += `\n${error.message}`;
  }
}

async function restartSelected() {
  await stopSelectedComponents();
  await startSelectedComponents();
}

function setupMarqueeSelection() {
  const playground = $("playground");
  const box = $("selectionBox");
  playground.addEventListener("mousedown", (event) => {
    if (event.button !== 0 || event.target.closest(".node") || event.target.closest(".host-box") || event.target.closest(".zoom-controls") || event.target.closest("#edgeLayer")) return;
    const rect = playground.getBoundingClientRect();
    marquee = {
      startClientX: event.clientX,
      startClientY: event.clientY,
      startX: event.clientX - rect.left + playground.scrollLeft,
      startY: event.clientY - rect.top + playground.scrollTop,
    };
    box.style.display = "block";
    box.style.left = `${marquee.startX}px`;
    box.style.top = `${marquee.startY}px`;
    box.style.width = "0px";
    box.style.height = "0px";
    event.preventDefault();
  });
  window.addEventListener("mousemove", (event) => {
    if (!marquee) return;
    const rect = playground.getBoundingClientRect();
    const currentX = event.clientX - rect.left + playground.scrollLeft;
    const currentY = event.clientY - rect.top + playground.scrollTop;
    box.style.left = `${Math.min(marquee.startX, currentX)}px`;
    box.style.top = `${Math.min(marquee.startY, currentY)}px`;
    box.style.width = `${Math.abs(currentX - marquee.startX)}px`;
    box.style.height = `${Math.abs(currentY - marquee.startY)}px`;
  });
  window.addEventListener("mouseup", (event) => {
    if (!marquee) return;
    const selectionRect = {
      left: Math.min(marquee.startClientX, event.clientX),
      right: Math.max(marquee.startClientX, event.clientX),
      top: Math.min(marquee.startClientY, event.clientY),
      bottom: Math.max(marquee.startClientY, event.clientY),
    };
    selectedNodeKeys.clear();
    selectedLink = null;
    document.querySelectorAll(".node").forEach((node) => {
      const nodeRect = node.getBoundingClientRect();
      const intersects = nodeRect.left <= selectionRect.right
        && nodeRect.right >= selectionRect.left
        && nodeRect.top <= selectionRect.bottom
        && nodeRect.bottom >= selectionRect.top;
      if (intersects) selectedNodeKeys.add(node.dataset.nodeKey);
    });
    marquee = null;
    box.style.display = "none";
    renderAll();
    renderFocusedLogs();
  });
}

function renderAll() {
  renderTopology();
  renderConfig();
}

async function init() {
  const health = await api("/api/health");
  const pluginPayload = await api("/api/plugins");
  plugins = pluginPayload.plugins || [];
  manifests = pluginPayload.manifests || [];
  $("template").innerHTML = plugins
    .map((plugin) => `<option value="${escapeAttr(plugin.id)}">${escapeText(plugin.name)}</option>`)
    .join("");
  const defaultTemplate = plugins[0]?.id || "blank";
  $("template").value = defaultTemplate;
  applyTemplate(defaultTemplate);
  setupMarqueeSelection();
  connectEventStream();
}

$("template").addEventListener("change", () => applyTemplate($("template").value));
$("addHost").addEventListener("click", () => addHost());
$("addRobot").addEventListener("click", () => addRobot());
$("addMonitor").addEventListener("click", () => addMonitor());
$("addConverter").addEventListener("click", () => addConverter());
$("addVerdict").addEventListener("click", () => addVerdict());
$("connectSelection").addEventListener("click", connectSelectionToTarget);
$("disconnectSelection").addEventListener("click", disconnectSelectionFromTarget);
$("clearSelection").addEventListener("click", deleteSelectedResources);
$("startRun").addEventListener("click", startSelectedComponents);
$("stopRun").addEventListener("click", stopSelectedComponents);
$("restartSelected").addEventListener("click", restartSelected);
$("loadFile").addEventListener("click", loadFile);
$("saveFile").addEventListener("click", saveFile);
$("zoomIn").addEventListener("click", () => setZoom(zoom + 0.1));
$("zoomOut").addEventListener("click", () => setZoom(zoom - 0.1));

document.querySelectorAll(".editor-tab").forEach((tab) => {
  tab.addEventListener("click", () => switchEditorTab(tab.dataset.editorTab));
});

$("scanGraph").addEventListener("click", async () => {
  $("scanStatus").textContent = "Scanning ROS graph...";
  $("graphResults").innerHTML = "";
  try {
    const data = await api("/api/discovery/graph");
    if (!data.available) {
      $("scanStatus").textContent = data.error || "Discovery failed.";
      $("graphResults").innerHTML = `<div class="notice">Discovery failed. You can still add robot sources manually.</div>`;
      return;
    }
    $("scanStatus").textContent = `Scan complete via ${data.method}.`;
    renderGraph(data);
  } catch (error) {
    $("scanStatus").textContent = error.message;
  }
});

init().catch((error) => {
  $("scanStatus").textContent = error.message;
  renderAll();
});
