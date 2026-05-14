/**
 * Legal & Tax Assistant — Solution Architecture PowerPoint Generator
 * Uses pptxgenjs with react-icons for Microsoft-style icons
 */

const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");

// react-icons imports
const { VscAzure } = require("react-icons/vsc");
const { SiMicrosoftazure } = require("react-icons/si");
const { 
  MdOutlineSecurity, MdOutlineStorage, MdOutlineSmartToy, 
  MdOutlineAccountTree, MdOutlinePerson, MdOutlineGavel,
  MdOutlineAccountBalance, MdOutlineQuestionAnswer, MdOutlineHub
} = require("react-icons/md");
const { 
  TbRobot, TbDatabase, TbServer, TbBrain, TbPlugConnected,
  TbUserScan, TbScale, TbReceipt2
} = require("react-icons/tb");
const { 
  HiOutlineUserGroup, HiOutlineChatBubbleLeftRight 
} = require("react-icons/hi2");
const { BiNetworkChart } = require("react-icons/bi");
const { RiFlowChart } = require("react-icons/ri");

// ─── Helpers ─────────────────────────────────────────────────────────────────

function renderIconSvg(IconComponent, color = "#FFFFFF", size = 256) {
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color, size: String(size) })
  );
}

async function iconToBase64Png(IconComponent, color = "#FFFFFF", size = 256) {
  const svg = renderIconSvg(IconComponent, color, size);
  const pngBuffer = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + pngBuffer.toString("base64");
}

// Factory for fresh shadow objects (avoid mutation bug)
const makeShadow = () => ({ type: "outer", blur: 6, offset: 2, angle: 135, color: "000000", opacity: 0.15 });

// ─── Color Palette (Microsoft Azure-inspired) ────────────────────────────────

const colors = {
  primary: "0078D4",       // Microsoft Blue
  secondary: "5C2D91",    // Purple (Foundry)
  accent: "00B7C3",       // Teal
  success: "107C10",      // Green
  warning: "D83B01",      // Orange
  dark: "1B1A19",         // Near black
  darkBg: "1E2761",       // Navy
  lightBg: "F3F5F9",      // Light gray
  white: "FFFFFF",
  text: "323130",         // Dark text
  lightText: "8A8886",    // Muted text
  cardBg: "FFFFFF",
};

// ─── Main ────────────────────────────────────────────────────────────────────

async function generatePresentation() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = "LegalTaxAssistant";
  pres.title = "Legal & Tax Assistant - Solution Architecture";

  // Pre-render all icons
  const icons = {
    robot: await iconToBase64Png(TbRobot, "#FFFFFF", 256),
    brain: await iconToBase64Png(TbBrain, "#FFFFFF", 256),
    database: await iconToBase64Png(TbDatabase, "#FFFFFF", 256),
    server: await iconToBase64Png(TbServer, "#FFFFFF", 256),
    plug: await iconToBase64Png(TbPlugConnected, "#FFFFFF", 256),
    userScan: await iconToBase64Png(TbUserScan, "#FFFFFF", 256),
    scale: await iconToBase64Png(TbScale, "#FFFFFF", 256),
    receipt: await iconToBase64Png(TbReceipt2, "#FFFFFF", 256),
    users: await iconToBase64Png(HiOutlineUserGroup, "#FFFFFF", 256),
    chat: await iconToBase64Png(HiOutlineChatBubbleLeftRight, "#FFFFFF", 256),
    security: await iconToBase64Png(MdOutlineSecurity, "#FFFFFF", 256),
    network: await iconToBase64Png(BiNetworkChart, "#FFFFFF", 256),
    flow: await iconToBase64Png(RiFlowChart, "#FFFFFF", 256),
    hub: await iconToBase64Png(MdOutlineHub, "#FFFFFF", 256),
    // Colored versions for architecture slide
    robotBlue: await iconToBase64Png(TbRobot, "#0078D4", 256),
    brainPurple: await iconToBase64Png(TbBrain, "#5C2D91", 256),
    serverGreen: await iconToBase64Png(TbServer, "#107C10", 256),
    dbOrange: await iconToBase64Png(TbDatabase, "#D83B01", 256),
    securityGray: await iconToBase64Png(MdOutlineSecurity, "#505050", 256),
    usersTeal: await iconToBase64Png(HiOutlineUserGroup, "#00B7C3", 256),
    scaleTeal: await iconToBase64Png(TbScale, "#00B7C3", 256),
    receiptTeal: await iconToBase64Png(TbReceipt2, "#00B7C3", 256),
    userScanTeal: await iconToBase64Png(TbUserScan, "#00B7C3", 256),
  };

  // ═══════════════════════════════════════════════════════════════════════════
  // SLIDE 1: Title Slide
  // ═══════════════════════════════════════════════════════════════════════════
  let slide1 = pres.addSlide();
  slide1.background = { color: colors.darkBg };

  // Accent bar at top
  slide1.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: colors.primary } });

  // Title
  slide1.addText("Legal & Tax Assistant", {
    x: 0.8, y: 1.5, w: 8, h: 1.2,
    fontSize: 42, fontFace: "Segoe UI Light", color: colors.white, bold: false
  });

  // Subtitle
  slide1.addText("Solution Architecture", {
    x: 0.8, y: 2.6, w: 8, h: 0.8,
    fontSize: 28, fontFace: "Segoe UI", color: colors.accent, bold: true
  });

  // Description
  slide1.addText("Multi-Agent AI System on Microsoft Foundry", {
    x: 0.8, y: 3.5, w: 8, h: 0.6,
    fontSize: 16, fontFace: "Segoe UI", color: "CADCFC"
  });

  // Icon cluster
  slide1.addImage({ data: icons.robot, x: 8.2, y: 1.5, w: 1.2, h: 1.2 });
  slide1.addImage({ data: icons.brain, x: 8.8, y: 2.8, w: 0.8, h: 0.8 });
  slide1.addImage({ data: icons.database, x: 8.0, y: 3.4, w: 0.7, h: 0.7 });

  // Bottom bar
  slide1.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.3, w: 10, h: 0.325, fill: { color: colors.primary } });
  slide1.addText("Microsoft Foundry  |  Azure Container Apps  |  Azure Cosmos DB  |  MCP Protocol", {
    x: 0.5, y: 5.32, w: 9, h: 0.3,
    fontSize: 10, fontFace: "Segoe UI", color: colors.white, align: "center"
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // SLIDE 2: High-Level Architecture
  // ═══════════════════════════════════════════════════════════════════════════
  let slide2 = pres.addSlide();
  slide2.background = { color: colors.lightBg };

  // Header
  slide2.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: colors.primary } });
  slide2.addText("High-Level Architecture", {
    x: 0.5, y: 0.2, w: 9, h: 0.6,
    fontSize: 24, fontFace: "Segoe UI Semibold", color: colors.text
  });

  // === USER LAYER (left) ===
  slide2.addShape(pres.shapes.RECTANGLE, { x: 0.3, y: 1.8, w: 1.8, h: 2.2, fill: { color: colors.white }, shadow: makeShadow() });
  slide2.addShape(pres.shapes.RECTANGLE, { x: 0.3, y: 1.8, w: 1.8, h: 0.06, fill: { color: colors.primary } });
  slide2.addImage({ data: icons.usersTeal, x: 0.9, y: 2.1, w: 0.6, h: 0.6 });
  slide2.addText("Users", { x: 0.3, y: 2.75, w: 1.8, h: 0.35, fontSize: 11, fontFace: "Segoe UI Semibold", color: colors.text, align: "center" });
  slide2.addText("Requestors\nLegal Experts\nTax Experts", { x: 0.3, y: 3.05, w: 1.8, h: 0.8, fontSize: 9, fontFace: "Segoe UI", color: colors.lightText, align: "center" });

  // === FOUNDRY (center) ===
  slide2.addShape(pres.shapes.RECTANGLE, { x: 2.6, y: 1.0, w: 4.6, h: 4.2, fill: { color: "F0ECFA" }, line: { color: colors.secondary, width: 1.5, dashType: "dash" } });
  slide2.addText("Microsoft Foundry", { x: 2.6, y: 1.05, w: 4.6, h: 0.35, fontSize: 10, fontFace: "Segoe UI Semibold", color: colors.secondary, align: "center" });

  // Orchestrator
  slide2.addShape(pres.shapes.RECTANGLE, { x: 3.1, y: 1.5, w: 3.6, h: 1.2, fill: { color: colors.white }, shadow: makeShadow() });
  slide2.addShape(pres.shapes.RECTANGLE, { x: 3.1, y: 1.5, w: 3.6, h: 0.06, fill: { color: colors.primary } });
  slide2.addImage({ data: icons.robotBlue, x: 3.3, y: 1.7, w: 0.5, h: 0.5 });
  slide2.addText("LegalTaxOrchestrator", { x: 3.8, y: 1.65, w: 2.8, h: 0.35, fontSize: 11, fontFace: "Segoe UI Semibold", color: colors.text, margin: 0 });
  slide2.addText("Hosted Agent | ResponsesHostServer", { x: 3.8, y: 1.95, w: 2.8, h: 0.3, fontSize: 9, fontFace: "Segoe UI", color: colors.lightText, margin: 0 });
  slide2.addText("FoundryChatClient | Agent Framework", { x: 3.8, y: 2.2, w: 2.8, h: 0.3, fontSize: 9, fontFace: "Segoe UI", color: colors.lightText, margin: 0 });

  // Prompt Agents row
  const agentY = 3.2;
  const agentW = 1.55;
  const agents = [
    { name: "Classifier\nAgent", icon: icons.userScanTeal, x: 2.8 },
    { name: "Requestor\nAgent", icon: icons.receiptTeal, x: 4.45 },
    { name: "Legal\nAgent", icon: icons.scaleTeal, x: 6.1 },
  ];
  agents.forEach(a => {
    slide2.addShape(pres.shapes.RECTANGLE, { x: a.x, y: agentY, w: agentW, h: 1.6, fill: { color: colors.white }, shadow: makeShadow() });
    slide2.addShape(pres.shapes.RECTANGLE, { x: a.x, y: agentY, w: agentW, h: 0.05, fill: { color: colors.accent } });
    slide2.addImage({ data: a.icon, x: a.x + 0.5, y: agentY + 0.2, w: 0.5, h: 0.5 });
    slide2.addText(a.name, { x: a.x, y: agentY + 0.8, w: agentW, h: 0.7, fontSize: 9, fontFace: "Segoe UI Semibold", color: colors.text, align: "center" });
  });

  // Tax Agent (separate since we ran out of the row)
  // Add a "+" for Tax Agent alongside Legal
  slide2.addText("+ Tax Agent", { x: 6.1, y: agentY + 1.3, w: agentW, h: 0.3, fontSize: 8, fontFace: "Segoe UI", color: colors.lightText, align: "center" });

  // === MCP SERVER (right-center) ===
  slide2.addShape(pres.shapes.RECTANGLE, { x: 7.8, y: 1.8, w: 1.9, h: 1.6, fill: { color: colors.white }, shadow: makeShadow() });
  slide2.addShape(pres.shapes.RECTANGLE, { x: 7.8, y: 1.8, w: 1.9, h: 0.06, fill: { color: colors.success } });
  slide2.addImage({ data: icons.serverGreen, x: 8.4, y: 2.0, w: 0.5, h: 0.5 });
  slide2.addText("MCP Server", { x: 7.8, y: 2.55, w: 1.9, h: 0.3, fontSize: 11, fontFace: "Segoe UI Semibold", color: colors.text, align: "center" });
  slide2.addText("FastMCP\nContainer App", { x: 7.8, y: 2.8, w: 1.9, h: 0.5, fontSize: 9, fontFace: "Segoe UI", color: colors.lightText, align: "center" });

  // === COSMOS DB (right-bottom) ===
  slide2.addShape(pres.shapes.RECTANGLE, { x: 7.8, y: 3.7, w: 1.9, h: 1.5, fill: { color: colors.white }, shadow: makeShadow() });
  slide2.addShape(pres.shapes.RECTANGLE, { x: 7.8, y: 3.7, w: 1.9, h: 0.06, fill: { color: colors.warning } });
  slide2.addImage({ data: icons.dbOrange, x: 8.4, y: 3.9, w: 0.5, h: 0.5 });
  slide2.addText("Cosmos DB", { x: 7.8, y: 4.4, w: 1.9, h: 0.3, fontSize: 11, fontFace: "Segoe UI Semibold", color: colors.text, align: "center" });
  slide2.addText("Users | Requests\nQuestions | Audit", { x: 7.8, y: 4.65, w: 1.9, h: 0.5, fontSize: 9, fontFace: "Segoe UI", color: colors.lightText, align: "center" });

  // === ENTRA ID (bottom) ===
  slide2.addImage({ data: icons.securityGray, x: 0.5, y: 4.6, w: 0.4, h: 0.4 });
  slide2.addText("Microsoft Entra ID — Managed Identity & RBAC", { x: 1.0, y: 4.65, w: 4, h: 0.35, fontSize: 9, fontFace: "Segoe UI", color: colors.lightText });

  // ═══════════════════════════════════════════════════════════════════════════
  // SLIDE 3: Agent Routing Flow
  // ═══════════════════════════════════════════════════════════════════════════
  let slide3 = pres.addSlide();
  slide3.background = { color: colors.white };

  slide3.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: colors.primary } });
  slide3.addText("Agent Orchestration Flow", {
    x: 0.5, y: 0.2, w: 9, h: 0.6,
    fontSize: 24, fontFace: "Segoe UI Semibold", color: colors.text
  });

  // Flow steps
  const steps = [
    { num: "1", title: "User Message", desc: "Chat via Responses Protocol", color: colors.primary, icon: icons.chat },
    { num: "2", title: "Identify & Classify", desc: "OBO Token → ClassifierAgent\n→ get_user_role (MCP)", color: colors.secondary, icon: icons.userScan },
    { num: "3", title: "Route to Specialist", desc: "RequestorAgent / LegalAgent\n/ TaxAgent based on role", color: colors.accent, icon: icons.flow },
    { num: "4", title: "MCP Tool Calls", desc: "create_request, add_questions,\nsubmit_answer, etc.", color: colors.success, icon: icons.plug },
    { num: "5", title: "Persist to Cosmos", desc: "CRUD + Audit Trail\nfor all operations", color: colors.warning, icon: icons.database },
  ];

  const stepW = 1.65;
  const stepGap = 0.2;
  const startX = 0.4;
  const stepY = 1.2;

  steps.forEach((s, i) => {
    const sx = startX + i * (stepW + stepGap);
    
    // Card
    slide3.addShape(pres.shapes.RECTANGLE, { x: sx, y: stepY, w: stepW, h: 3.6, fill: { color: colors.lightBg }, shadow: makeShadow() });
    
    // Top accent
    slide3.addShape(pres.shapes.RECTANGLE, { x: sx, y: stepY, w: stepW, h: 0.06, fill: { color: s.color } });
    
    // Number circle
    slide3.addShape(pres.shapes.OVAL, { x: sx + 0.55, y: stepY + 0.25, w: 0.55, h: 0.55, fill: { color: s.color } });
    slide3.addText(s.num, { x: sx + 0.55, y: stepY + 0.25, w: 0.55, h: 0.55, fontSize: 16, fontFace: "Segoe UI", color: colors.white, align: "center", valign: "middle", bold: true });
    
    // Icon
    slide3.addImage({ data: s.icon, x: sx + 0.55, y: stepY + 1.0, w: 0.55, h: 0.55 });
    
    // Title
    slide3.addText(s.title, { x: sx + 0.05, y: stepY + 1.7, w: stepW - 0.1, h: 0.5, fontSize: 11, fontFace: "Segoe UI Semibold", color: colors.text, align: "center" });
    
    // Description
    slide3.addText(s.desc, { x: sx + 0.05, y: stepY + 2.2, w: stepW - 0.1, h: 1.2, fontSize: 9, fontFace: "Segoe UI", color: colors.lightText, align: "center" });
  });

  // Arrow connectors between steps
  for (let i = 0; i < steps.length - 1; i++) {
    const arrowX = startX + (i + 1) * (stepW + stepGap) - stepGap + 0.02;
    slide3.addText("→", { x: arrowX - 0.15, y: stepY + 1.5, w: 0.35, h: 0.4, fontSize: 18, fontFace: "Segoe UI", color: colors.primary, align: "center", bold: true });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SLIDE 4: MCP Server & Data Model
  // ═══════════════════════════════════════════════════════════════════════════
  let slide4 = pres.addSlide();
  slide4.background = { color: colors.white };

  slide4.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: colors.primary } });
  slide4.addText("MCP Server & Data Layer", {
    x: 0.5, y: 0.2, w: 9, h: 0.6,
    fontSize: 24, fontFace: "Segoe UI Semibold", color: colors.text
  });

  // MCP Tools Section
  slide4.addText("MCP Tools (FastMCP)", { x: 0.5, y: 0.9, w: 4.5, h: 0.4, fontSize: 14, fontFace: "Segoe UI Semibold", color: colors.success });
  
  const tools = [
    "get_user_role — User identity lookup",
    "create_request — New request creation",
    "add_questions_to_request — Question categorization",
    "send_request — Auto-assign to experts",
    "get_assigned_questions — Expert queue",
    "submit_answer — Expert response",
    "mark_question_submitted — Finalize answer",
    "get_requests_by_user — Request history",
    "get_request_status — Status tracking",
  ];

  slide4.addText(tools.map(t => ({ text: t, options: { bullet: true, breakLine: true } })), {
    x: 0.7, y: 1.35, w: 4.3, h: 3.8, fontSize: 10, fontFace: "Segoe UI", color: colors.text
  });

  // Cosmos DB Collections
  slide4.addText("Azure Cosmos DB Collections", { x: 5.3, y: 0.9, w: 4.5, h: 0.4, fontSize: 14, fontFace: "Segoe UI Semibold", color: colors.warning });

  const collections = [
    { name: "Users", desc: "email, displayName, role, expertType" },
    { name: "Requests", desc: "id, requestorEmail, title, status, timestamps" },
    { name: "Questions", desc: "id, requestId, questionText, type, assignedTo, answer" },
    { name: "AuditLog", desc: "entityType, entityId, action, performedBy, timestamp" },
  ];

  let collY = 1.4;
  collections.forEach(c => {
    slide4.addShape(pres.shapes.RECTANGLE, { x: 5.5, y: collY, w: 4.2, h: 0.85, fill: { color: colors.lightBg }, shadow: makeShadow() });
    slide4.addShape(pres.shapes.RECTANGLE, { x: 5.5, y: collY, w: 0.06, h: 0.85, fill: { color: colors.warning } });
    slide4.addText(c.name, { x: 5.7, y: collY + 0.05, w: 3.9, h: 0.35, fontSize: 11, fontFace: "Segoe UI Semibold", color: colors.text, margin: 0 });
    slide4.addText(c.desc, { x: 5.7, y: collY + 0.4, w: 3.9, h: 0.35, fontSize: 9, fontFace: "Segoe UI", color: colors.lightText, margin: 0 });
    collY += 0.95;
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // SLIDE 5: Technology Stack
  // ═══════════════════════════════════════════════════════════════════════════
  let slide5 = pres.addSlide();
  slide5.background = { color: colors.white };

  slide5.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: colors.primary } });
  slide5.addText("Technology Stack", {
    x: 0.5, y: 0.2, w: 9, h: 0.6,
    fontSize: 24, fontFace: "Segoe UI Semibold", color: colors.text
  });

  const techGroups = [
    {
      title: "AI & Agents",
      color: colors.secondary,
      items: ["Microsoft Foundry (Hosted Agent)", "Agent Framework + FoundryChatClient", "GPT-5.4 Model Deployment", "Prompt Agents (YAML-defined)"]
    },
    {
      title: "Infrastructure",
      color: colors.primary,
      items: ["Azure Container Apps", "Azure Cosmos DB (NoSQL)", "Bicep IaC (azd)", "Docker Containers"]
    },
    {
      title: "Integration",
      color: colors.success,
      items: ["MCP Protocol (FastMCP)", "Streamable HTTP Transport", "Responses Protocol", "OpenTelemetry Tracing"]
    },
    {
      title: "Security",
      color: colors.dark,
      items: ["Microsoft Entra ID", "Managed Identity (RBAC)", "DefaultAzureCredential", "OBO Token Flow"]
    },
  ];

  const gridStartY = 1.0;
  const cardW = 4.4;
  const cardH = 2.0;

  techGroups.forEach((g, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const gx = 0.4 + col * (cardW + 0.4);
    const gy = gridStartY + row * (cardH + 0.3);

    slide5.addShape(pres.shapes.RECTANGLE, { x: gx, y: gy, w: cardW, h: cardH, fill: { color: colors.lightBg }, shadow: makeShadow() });
    slide5.addShape(pres.shapes.RECTANGLE, { x: gx, y: gy, w: cardW, h: 0.05, fill: { color: g.color } });
    slide5.addText(g.title, { x: gx + 0.2, y: gy + 0.1, w: 4, h: 0.4, fontSize: 13, fontFace: "Segoe UI Semibold", color: g.color, margin: 0 });
    slide5.addText(g.items.map(item => ({ text: item, options: { bullet: true, breakLine: true } })), {
      x: gx + 0.3, y: gy + 0.55, w: 3.9, h: 1.4, fontSize: 10, fontFace: "Segoe UI", color: colors.text
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // SLIDE 6: Closing
  // ═══════════════════════════════════════════════════════════════════════════
  let slide6 = pres.addSlide();
  slide6.background = { color: colors.darkBg };

  slide6.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.06, fill: { color: colors.primary } });

  slide6.addImage({ data: icons.robot, x: 4.5, y: 1.2, w: 1.0, h: 1.0 });

  slide6.addText("Legal & Tax Assistant", {
    x: 1, y: 2.4, w: 8, h: 0.8,
    fontSize: 32, fontFace: "Segoe UI Light", color: colors.white, align: "center"
  });

  slide6.addText("Intelligent multi-agent orchestration powered by Microsoft Foundry", {
    x: 1, y: 3.2, w: 8, h: 0.5,
    fontSize: 14, fontFace: "Segoe UI", color: "CADCFC", align: "center"
  });

  // Key stats
  const stats = [
    { value: "4", label: "Prompt Agents" },
    { value: "1", label: "Hosted Agent" },
    { value: "9+", label: "MCP Tools" },
    { value: "4", label: "Cosmos Collections" },
  ];

  const statW = 2.0;
  const statStartX = 1.0;
  stats.forEach((st, i) => {
    const stx = statStartX + i * statW;
    slide6.addText(st.value, { x: stx, y: 3.9, w: statW, h: 0.6, fontSize: 28, fontFace: "Segoe UI", color: colors.accent, align: "center", bold: true });
    slide6.addText(st.label, { x: stx, y: 4.4, w: statW, h: 0.4, fontSize: 10, fontFace: "Segoe UI", color: "CADCFC", align: "center" });
  });

  slide6.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.3, w: 10, h: 0.325, fill: { color: colors.primary } });

  // ─── Save ──────────────────────────────────────────────────────────────────
  const outputPath = "LegalTaxAssistant_Architecture.pptx";
  await pres.writeFile({ fileName: outputPath });
  console.log(`✅ Presentation saved: ${outputPath}`);
}

generatePresentation().catch(err => {
  console.error("Error generating presentation:", err);
  process.exit(1);
});
