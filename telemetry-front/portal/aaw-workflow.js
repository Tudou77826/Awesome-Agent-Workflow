(() => {
  "use strict";

  // Keep stage descriptions and assets aligned with scripts/cli/definitions/flow.yaml.
  const node = (title, summary, skill, input, action, output, done, note = "", kind = "") =>
    ({ title, summary, skill, input, action, output, done, note, kind });
  const nodes = {
    "sr-init": node("建立架构上下文", "生成或复用仓库架构基线", "repo-init",
      "当前业务代码仓、SR 编号及原始需求文件。",
      "梳理模块职责、依赖关系与工程约束，建立或复用架构基线。",
      ".sdd/software_architecture.md",
      "新建或修改的架构成果经用户确认；有效的已有基线可直接复用。"),
    "sr-design": node("SR 需求设计", "与人循环对齐目标和范围", "sr-design",
      "original-requirement.md 与软件架构基线。",
      "结合代码事实提出问题，与人确认目标、范围、流程、约束和验收口径；有新问题则继续对齐。",
      ".sdd/<SR>/SR-design.md",
      "必要决策收敛，问答摘要经确认，形成可评审的系统需求设计。",
      "保留原始需求原文，不能把未确认的推测写成既定结论。", "loop"),
    "sr-design-gate": node("SR 设计门禁", "检查需求、边界与验收", "sr-design-gate",
      "software_architecture.md、original-requirement.md、SR-design.md。",
      "检查需求一致性、边界冲突、风险、待决问题与可拆分性。",
      ".sdd/<SR>/SR-design-gate.md，每轮均生成或更新。",
      "只有 pass 才能继续 AR 拆分。",
      "fail 时原地修正设计，blocked 时补齐输入或决策，再重新检查；不自动回滚工作流。", "gate"),
    "ar-split": node("确认 AR 拆分", "拆成多个变更，或整体推进", "aaw-workflow（编排）",
      "通过门禁的 SR-design.md。",
      "向用户确认是否拆分；拆分时确定各 AR 的稳定编号、标题与范围。",
      ".sdd/<SR>/AR-split.md，以及 AR 列表或整体推进决策。",
      "拆分方案经用户确认。每个 AR 进入澄清；不拆分则使用 ALL 目录并直接进入模块边界设计。"),
    "ar-init": node("确认变更来源", "基于已有架构建立 AR 上下文", "aaw-workflow（编排）",
      "已有 .sdd/software_architecture.md、SR / AR 编号和本次变更描述。",
      "确认变更身份与来源；有原始材料时保存为可追溯的输入。",
      ".sdd/<SR>/<AR>/AR-source.md（有来源材料时生成）。",
      "架构基线和变更信息就绪，进入 AR 澄清。",
      "AR 入口不会先生成 SR 设计与 SR 门禁文档；缺少架构时先完成仓库初始化。"),
    "ar-clarify": node("AR 需求澄清", "确认本次变更与验收边界", "ar-clarify",
      "AR 编号与描述；SR-design.md 或 AR-source.md 作为来源上下文。",
      "明确本次变更的目标、范围、约束、受影响模块和验收标准。",
      ".sdd/<SR>/<AR>/AR-clarify.md",
      "用户确认澄清成果后，进入模块边界设计。",
      "多人协作时，SE / DE 在此完成评审，将完整 .sdd 上下文合入业务仓，开发拉取后继续。入库和拉取属于角色交接动作。"),
    "module-boundary-design": node("模块边界设计", "明确职责、影响面与交互", "module-boundary-design",
      "软件架构与 AR-clarify.md；ALL 模式直接使用 SR-design.md。",
      "确定受影响模块、职责划分、依赖和交互，检查边界是否闭合。",
      ".sdd/<SR>/<AR>/module-boundary-design.md",
      "展示成果并经用户确认，继续模块分组。"),
    "module-detail-design-split": node("模块设计分组", "为每个模块组建立设计链", "aaw-workflow（编排）",
      "已确认的 module-boundary-design.md。",
      "按耦合关系将模块分组并请用户确认；小需求可以只保留一个组。",
      "模块分组清单，以及对应模块组目录中的下游工作流。",
      "分组确认，每个模块组分别进入现状探索。",
      "目录使用稳定的中文模块名或模块组名；强耦合交互应放在同组。"),
    "module-asis-analysis": node("现状探索", "与代码仓循环对齐事实", "module-asis-analysis",
      "架构基线、模块边界设计与当前模块组代码。",
      "提出探索问题，查证代码、接口和调用链，复核证据并补查缺口，持续更新对现状的认知。",
      "<模块组>/.context/详细设计上下文.md",
      "关键代码事实有可引用的证据，足以支撑目标设计。",
      "以架构文档为模块边界依据；现状分析只陈述已查证事实。", "loop"),
    "module-tobe-design": node("详细设计", "将事实转化为可实现方案", "module-tobe-design",
      "当前模块组的 .context/详细设计上下文.md。",
      "明确目标结构、接口、数据、异常、兼容策略与工程落点，引用现状证据。",
      "<模块组>/模块详细设计说明书.md",
      "方案与契约清晰，可进入测试设计。",
      "代码事实不足时补查现状；未决的设计选择先收敛。"),
    "module-test-design": node("测试设计", "明确用例、断言与覆盖", "module-test-design",
      "当前模块组的详细设计说明书。",
      "围绕正常行为、边界、异常、兼容与风险设计最小充分用例集。",
      "<模块组>/模块测试用例设计.md",
      "关键行为均有可执行的验证方法和预期结果。",
      "如果设计不可验证，先补齐设计，再进行门禁。"),
    "module-design-gate": node("AR 设计门禁", "按模块组检查设计闭环", "module-design-gate",
      "现状上下文、详细设计、测试用例设计。",
      "检查证据、职责边界、决策收敛、工程可执行性、测试覆盖与风险闭环。",
      "<模块组>/.context/模块设计门禁结果.md",
      "只有 pass 才可继续任务拆分。",
      "此门禁在每个模块组执行。未通过时原地修正相应成果或补齐输入，再复检。", "gate"),
    "task-split": node("任务拆分与确认", "按依赖形成可验收的任务计划", "task-split",
      "已通过门禁的详细设计和测试设计。",
      "把设计组织为 T1、T2…任务条目，记录范围、依赖、设计引用和验证责任，并请用户确认。",
      "<模块组>/tasks-overview.md",
      "任务计划经用户确认，按该列表依次执行。",
      "任务集中记录在计划中，不生成独立的 T1 / T2 任务文件。"),
    "code-implement": node("实现与测试", "按已确认设计完成当前任务", "task-dev",
      "任务计划、详细设计、测试用例、已通过的设计门禁及架构基线。",
      "实现当前任务，将测试设计落实为可执行验证，完成相关测试与必要构建检查。",
      "当前任务代码与实现、测试证据。",
      "当前任务的核心验证通过，提交实现报告后进入代码开发门禁。",
      "若设计与代码事实冲突，暂停并回流澄清；不自行改变既定契约。"),
    "code-gate": node("代码开发门禁", "审查 → 修复重验 → CodeCheck", "task-dev / code-check",
      "当前任务变更、权威设计与实现测试证据。",
      "两个只读 Reviewer 分别检查需求正确性与工程质量；主 Agent 处置发现、修复并重验，再执行 CodeCheck。",
      "语义审查报告、修复重验记录、CodeCheck 结果与完成证据。",
      "所有成立的问题闭环，受影响测试通过，CodeCheck 检查完成，证据满足完成要求。",
      "属于每个 task-dev 的内部阶段；SR、AR、DEV 共用此流程。未通过时继续修正并验证，不能跳过检查。", "gate"),
    "task-done": node("任务完成与交接", "记录结果、证据和残余风险", "task-dev",
      "已通过检查的代码与开发过程证据。",
      "回填 tasks-overview.md 中的执行记录、实现期补充和残余风险，核对候选提交信息。",
      "任务交接记录、候选提交信息及完成报告。",
      "完成检查通过，当前任务标记完成；全部分支与任务完成后，工作流完成。",
      "每个任务完成后停止，后续任务待继续指令。不会自动执行 git add、commit 或 push。"),
    "dev-init": node("确认需求", "对齐一人可独立完成的范围", "aaw-workflow（编排）",
      "需求描述与用于组织本次工作的 SR 编号。",
      "确认目标、约束与验收范围；较长原文可保存为来源材料。",
      ".sdd/<SR>/requirement.md（可选）。",
      "需求经确认，适合由同一人贯穿设计与开发。",
      "不要求预先提供需求文件或架构文档；多人复杂协作应选择 SR 入口。"),
    "dev-design": node("统一设计", "在一份文档中收敛意图和事实", "dev-design",
      "已确认需求、当前代码与存在时的架构基线。",
      "在同一个问题池中向人确认决策、向代码仓核查事实，形成方案、模块边界、契约和验收标准。",
      ".sdd/<SR>/dev-design.md",
      "设计决策收敛，代码论断有可回溯引用。",
      "DEV 的两个对齐方向整合在统一设计中，不单独生成 SR 与模块详设文档。", "loop"),
    "dev-test-design": node("测试设计", "生成最小充分的验证用例", "module-test-design（轻量模式）",
      "dev-design.md。",
      "生成最小充分用例集、覆盖矩阵与缺口清单。",
      ".sdd/<SR>/test-design.md",
      "契约与验收能够通过用例验证；关键缺口已闭环。"),
    "dev-design-gate": node("轻量设计门禁", "检查决策、证据与可验证性", "dev-design-gate",
      "dev-design.md 和 test-design.md。",
      "检查决策已收敛、代码论断可回溯、契约与验收可执行。",
      ".sdd/<SR>/.context/dev-design-gate.md，每轮生成或更新。",
      "只有 pass 才可进入任务拆分。",
      "未通过时修正设计或测试设计；阻塞时补齐输入和决策，再复检。", "gate"),
    "dev-task-split": node("任务拆分与确认", "圈定任务范围与验证责任", "task-split（轻量模式）",
      "dev-design.md、test-design.md 与已通过的轻量设计门禁。",
      "形成串行任务计划，指定各任务负责的用例，并回填测试覆盖矩阵的首次可验证阶段。",
      ".sdd/<SR>/tasks-overview.md",
      "用户确认计划后，按顺序逐任务开发。",
      "任务计划、设计与测试设计集中在同一个 SR 目录。")
  };

  const entries = {
    sr: {
      title: "从系统需求出发，支撑跨角色协作",
      description: "适合涉及多个模块、需要需求设计与开发交接的工作。先对齐系统需求，再按 AR 和模块组逐层展开，直到代码交付。",
      preparation: "准备原始需求文件与 SR 编号。已有架构基线可复用，没有则在初始化阶段建立。",
      directoryNote: "示例采用 AR 拆分。若不拆分，AR 目录改为 ALL/，并跳过 AR-clarify.md；其余模块设计与开发链相同。"
    },
    ar: {
      title: "已有架构与明确变更，从 AR 开始",
      description: "适合系统架构已清楚、可以直接界定的一次变更。完成 AR 澄清后，继续模块设计、门禁与开发。",
      preparation: "已有 software_architecture.md；提供 SR / AR 编号与变更描述。无需先运行 SR 设计链。",
      directoryNote: "“已有基线”为输入，AR-source.md 按需生成；其余展示本入口的主要产物。不会额外生成 SR 设计、SR 门禁或 AR 拆分文档。"
    },
    dev: {
      title: "一个人贯穿设计与实现，轻量推进",
      description: "适合规模可控、边界清晰且无需多角色交接的需求。以统一设计和测试设计承接全过程，开发质量检查保持完整。",
      preparation: "准备需求描述与 SR 编号。原始需求文件、架构基线均可选；复杂跨角色需求请选择 SR。",
      directoryNote: "产物直接放在 SR 目录下，没有 AR 和模块组层级。SR 编号在此用于组织一次工作，不代表必须先做 SR 设计。"
    }
  };

  const escape = (value) => String(value).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  function detailsFor(key, entry) {
    const detail = { ...nodes[key] };
    if (entry === "dev" && ["code-implement", "code-gate", "task-done"].includes(key)) {
      detail.skill += "（轻量模式）";
      if (key === "code-implement") {
        detail.input = "tasks-overview.md、dev-design.md、test-design.md，以及存在时的架构等仓库基线。";
      }
    }
    return detail;
  }

  function nodeTone(key, item) {
    if (item.kind === "gate") return "gate";
    if (item.kind === "loop") return "loop";
    if (key === "ar-split") return "branch";
    if (key.endsWith("-init")) return "context";
    if (key.includes("split")) return "branch";
    if (["code-implement", "task-done"].includes(key)) return "delivery";
    return "design";
  }

  const toneMeta = {
    context: { icon: "◎", label: "CONTEXT" },
    loop: { icon: "↻", label: "ALIGNMENT LOOP" },
    gate: { icon: "◇", label: "QUALITY GATE" },
    branch: { icon: "◆", label: "DECISION" },
    design: { icon: "◆", label: "DESIGN" },
    delivery: { icon: "✓", label: "DELIVERY" }
  };

  function renderNode(key, entry) {
    const item = detailsFor(key, entry);
    const tone = nodeTone(key, item);
    const meta = toneMeta[tone];
    return '<div class="flow-cell" data-tone="' + tone + '"><button type="button" class="flow-node' +
      (item.kind ? " flow-node--" + item.kind : "") + '" id="' + entry + '-node-' + key +
      '" data-node="' + key + '" data-tone="' + tone + '" aria-expanded="false" aria-controls="detail-' + entry + '">' +
      '<span class="node-meta"><i aria-hidden="true">' + meta.icon + '</i><span>' + meta.label + '</span></span>' +
      "<b>" + escape(item.title) + "</b></button></div>";
  }

  function phase(index, title, keys, entry) {
    return '<section class="flow-stage flow-stage--phase-' + index + ' flow-stage--nodes-' + keys.length + '"><header class="stage-label"><small>' + index +
      "</small><b>" + title + '</b></header><div class="flow-track">' +
      keys.map((key) => renderNode(key, entry)).join("") + "</div></section>";
  }

  function connector() {
    return '<div class="flow-connector" aria-hidden="true"></div>';
  }

  function taskFlow(entry) {
    return '<section class="flow-stage task-group"><header class="stage-label"><small>LOOP / TASK</small><b>每个任务</b></header>' +
      '<div class="flow-track">' + ["code-implement", "code-gate", "task-done"].map((key) => renderNode(key, entry)).join("") +
      '</div><small class="stage-note">按任务列表依次执行，门禁未通过则回到当前任务修正。</small></section>';
  }

  function flowSubsection(title, keys, entry, note = "") {
    return '<section class="flow-subsection"><span class="flow-subsection-label">' + title +
      '</span><div class="flow-track">' + keys.map((key) => renderNode(key, entry)).join("") +
      "</div>" + (note ? '<small class="stage-note">' + note + "</small>" : "") + "</section>";
  }

  function workflowStage(index, title, content) {
    return '<section class="workflow-stage workflow-stage--' + index + '"><header class="workflow-stage-label"><small>' + index +
      "</small><b>" + title + '</b></header><div class="workflow-stage-content">' + content + "</div></section>";
  }

  function flowRow(index, title, content, compact = false) {
    return '<section class="flow-row' + (compact ? " flow-row--workflow" : "") + '" aria-label="第 ' + index + ' 阶段"><div class="flow-row-track">' + content + "</div></section>";
  }

  function rowTurn(label) {
    return '<div class="flow-turn" aria-hidden="true"></div>';
  }

  function moduleGroup(content, options = {}) {
    const { label = "MODULE GROUP", continuation = false, description = "设计、门禁与任务开发" } = options;
    return '<section class="flow-group"><header class="group-label"><span>' + label + "</span><b>每个模块组" +
      (continuation ? " · 继续" : "") + "</b><small>" + description + "</small></header><div class=\"group-sequence\">" + content + "</div></section>";
  }

  function sharedDesignAndDeliveryRows(entry) {
    return rowTurn("进入 AR 设计") +
      flowRow("02", "AR设计", workflowStage("02", "AR设计",
        flowSubsection("变更边界", ["module-boundary-design", "module-detail-design-split"], entry) +
        connector() + flowSubsection("每个模块组", ["module-asis-analysis", "module-tobe-design", "module-test-design", "module-design-gate"], entry)), true) +
      rowTurn("AR设计门禁通过") +
      flowRow("03", "开发", workflowStage("03", "开发",
        flowSubsection("任务拆分", ["task-split"], entry) + connector() +
        flowSubsection("每个任务", ["code-implement", "code-gate", "task-done"], entry, "按任务列表依次执行，门禁未通过则回到当前任务修正。")), true);
  }

  function renderFlow(entry) {
    let flow;
    if (entry === "sr") {
      flow = flowRow("01", "SR设计", workflowStage("01", "SR设计", '<div class="flow-track">' +
        ["sr-init", "sr-design", "sr-design-gate", "ar-split"].map((key) => renderNode(key, entry)).join("") + "</div>"), true) +
        sharedDesignAndDeliveryRows(entry);
    } else if (entry === "ar") {
      flow = flowRow("01", "变更澄清", workflowStage("01", "变更澄清", '<div class="flow-track">' +
        ["ar-init", "ar-clarify"].map((key) => renderNode(key, entry)).join("") + "</div>"), true) +
        sharedDesignAndDeliveryRows(entry);
    } else {
      flow = flowRow("01", "设计与准备", phase("01", "设计与验证", ["dev-init", "dev-design", "dev-test-design", "dev-design-gate"], entry) +
        connector() + phase("02", "开发准备", ["dev-task-split"], entry)) +
        rowTurn("确认任务计划") +
        flowRow("02", "开发与交付", taskFlow(entry));
    }
    return '<div class="flow-board">' + flow + "</div>";
  }

  const fileItem = (name, note, badge = "") => ({ name, note, badge });
  const folder = (name, note, children) => ({ name, note, children });

  function moduleAssets() {
    return [
      fileItem("模块详细设计说明书.md", "目标方案、接口与工程落点"),
      fileItem("模块测试用例设计.md", "验证用例与预期结果"),
      fileItem("tasks-overview.md", "任务计划、执行记录与交接"),
      folder(".context/", "现状与门禁证据", [
        fileItem("详细设计上下文.md", "代码现状与事实引用"),
        fileItem("模块设计门禁结果.md", "AR 设计门禁结论")
      ])
    ];
  }

  function arAssets(entry) {
    const assets = [];
    if (entry === "ar") assets.push(fileItem("AR-source.md", "原始材料与变更来源", "可选"));
    assets.push(fileItem("AR-clarify.md", "本次变更的范围、约束与验收"),
      fileItem("module-boundary-design.md", "模块职责与交互边界"),
      folder("<模块组>/", "每个模块组各一份", moduleAssets()));
    return assets;
  }

  function assetsFor(entry) {
    const baselineBadge = entry === "ar" ? "已有基线" : entry === "dev" ? "可选" : "生成 / 复用";
    const root = [fileItem("software_architecture.md", "仓库级架构基线", baselineBadge)];
    const sr = [fileItem("workflow.yaml", "当前入口的进度与产物索引")];
    if (entry === "sr") {
      sr.push(fileItem("original-requirement.md", "保留原始需求原文"),
        fileItem("SR-design.md", "已确认的系统需求设计"),
        fileItem("SR-design-gate.md", "每轮 SR 设计门禁结论"),
        fileItem("AR-split.md", "已确认的 AR 拆分决策"),
        folder("<AR>/", "拆分时每个 AR 各一份", arAssets(entry)));
    } else if (entry === "ar") {
      sr.push(folder("<AR>/", "本次变更的工作目录", arAssets(entry)));
    } else {
      sr.push(fileItem("requirement.md", "较长的原始需求材料", "可选"),
        fileItem("dev-design.md", "需求、代码事实、方案与验收"),
        fileItem("test-design.md", "用例集与覆盖矩阵"),
        fileItem("tasks-overview.md", "任务计划、执行记录与交接"),
        folder(".context/", "设计门禁证据", [fileItem("dev-design-gate.md", "轻量设计门禁结论")]));
    }
    root.push(folder("<SR>/", "本次工作", sr));
    return [folder(".sdd/", "随业务代码仓版本管理", root)];
  }

  function tree(items) {
    return '<ul class="tree">' + items.map((item) =>
      '<li' + (item.children ? ' class="tree-folder"' : "") + '><div class="tree-row"><code>' +
      escape(item.name) + (item.badge ? '<span class="tree-badge' +
        (item.badge === "可选" ? " tree-badge--optional" : "") + '">' + escape(item.badge) + "</span>" : "") +
      "</code><small>" + escape(item.note) + "</small></div>" +
      (item.children ? tree(item.children) : "") + "</li>").join("") + "</ul>";
  }

  function directory(entry) {
    const auxiliary = [folder(".sdd/<SR>/.aaw/", "运行过程中的辅助文件", [
      folder("data/", "节点数据文件", []),
      folder("task-dev/<step-id>/<attempt>/", "按开发节点与执行轮次保存", [
        fileItem("state.json", "开发阶段与审计状态")
      ])
    ])];
    return '<section class="directory" aria-labelledby="directory-' + entry + '"><div class="directory-heading"><h4 id="directory-' +
      entry + '">产物放在哪里</h4><p>' + entry.toUpperCase() + ' 入口 · 主要目录与文件用途</p></div>' +
      '<div class="directory-box">' + tree(assetsFor(entry)) +
      '<details class="directory-extra"><summary>展开辅助文件与运行证据</summary>' + tree(auxiliary) +
      '<p class="directory-note">开发报告、审查与检查证据也保存在对应执行目录。任务记录集中在 tasks-overview.md，不另建 T1 / T2 文件。</p></details></div>' +
      '<p class="directory-note">' + escape(entries[entry].directoryNote) + "</p></section>";
  }

  function renderPanel(entry) {
    return '<section class="entry-panel" id="panel-' + entry + '" role="tabpanel" aria-labelledby="tab-' + entry +
      '" tabindex="0"' + (entry === "sr" ? "" : " hidden") + '><div class="diagram-shell"><div class="diagram-viewport" data-camera-viewport tabindex="0" role="group" aria-label="' + entry.toUpperCase() + ' 入口完整流程图"><div class="diagram-overlay" role="group" aria-label="流程图图例与视图控制"><div class="diagram-legend"><span class="legend-flow">普通流程</span><span class="legend-loop">对齐 / 决策</span><span class="legend-gate">质量门禁</span><span class="diagram-hint">点击节点查看详情</span></div><div class="camera-controls" role="group" aria-label="流程图视图控制"><button type="button" data-camera-action="zoom-out" aria-label="缩小流程图">−</button><output data-camera-readout>120%</output><button type="button" data-camera-action="zoom-in" aria-label="放大流程图">＋</button><button type="button" data-camera-action="fit" aria-label="适配流程图">适配</button></div></div><div class="diagram-camera" data-camera><div class="diagram" data-camera-content><svg class="flow-connectors" data-flow-connectors aria-hidden="true" focusable="false"></svg>' + renderFlow(entry) + "</div></div>" +
      '<section class="node-detail" id="detail-' + entry + '" tabindex="-1" aria-labelledby="detail-title-' + entry + '" hidden></section></div></div>' +
      directory(entry) + "</section>";
  }

  const panelsRoot = document.getElementById("entry-panels");
  panelsRoot.innerHTML = Object.keys(entries).map(renderPanel).join("");
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const usageSection = document.getElementById("usage");
  const siteBar = document.querySelector(".site-bar");
  const minimumCanvasHeight = 430;
  let activeNode = null;

  function activeEntryPanel() {
    return document.querySelector(".entry-panel:not([hidden])");
  }

  function syncUsageViewport(panel = activeEntryPanel()) {
    if (!panel || panel.hidden) return;
    const viewport = panel.querySelector("[data-camera-viewport]");
    const usageRect = usageSection.getBoundingClientRect();
    const viewportRect = viewport.getBoundingClientRect();
    const siteBarHeight = siteBar.getBoundingClientRect().height;
    const chromeHeight = viewportRect.top - usageRect.top;
    const availableHeight = Math.floor(window.innerHeight - siteBarHeight - chromeHeight - 1);
    const height = Math.max(minimumCanvasHeight, availableHeight);
    viewport.style.height = height + "px";
    viewport.style.minHeight = height + "px";
  }

  function alignUsage(behavior = "auto") {
    const top = usageSection.getBoundingClientRect().top + window.scrollY - siteBar.getBoundingClientRect().height;
    window.scrollTo({ top: Math.max(0, Math.round(top)), behavior });
  }

  function scheduleUsageLayout(options = {}) {
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
      const panel = activeEntryPanel();
      syncUsageViewport(panel);
      if (panel && panel._fitCamera) panel._fitCamera();
      if (options.align) alignUsage(options.behavior || "auto");
    }));
  }

  function setupCamera(panel) {
    const viewport = panel.querySelector("[data-camera-viewport]");
    const camera = panel.querySelector("[data-camera]");
    const content = panel.querySelector("[data-camera-content]");
    const readout = panel.querySelector("[data-camera-readout]");
    const detail = panel.querySelector(".node-detail");
    const connectorLayer = panel.querySelector("[data-flow-connectors]");
    if (!viewport || !camera || !content) return;
    const state = { scale: 1, x: 0, y: 0, pointerId: null, startX: 0, startY: 0, originX: 0, originY: 0, moved: false };
    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
    const svgNamespace = "http://www.w3.org/2000/svg";
    const markerId = (tone = "default") => "aaw-flow-arrow-" + panel.id + (tone === "default" ? "" : "-" + tone);
    const defaultCameraScale = 1.2;
    let flowEdges = [];
    let connectorDefs = null;
    let edgeGroup = null;
    let hoveredNode = null;
    let cameraFrame = null;
    let cameraGeneration = 0;
    const supportsLayoutZoom = typeof CSS !== "undefined" && CSS.supports && CSS.supports("zoom", "1");
    let scaleCommitted = false;

    const toneColor = (tone) => {
      if (["loop", "branch"].includes(tone)) return "#3b6f87";
      if (tone === "gate") return "#d56a28";
      return "#18745a";
    };
    const relativeRect = (element, diagramRect) => {
      const rect = element.getBoundingClientRect();
      const scale = state.scale || 1;
      return {
        left: (rect.left - diagramRect.left) / scale,
        right: (rect.right - diagramRect.left) / scale,
        top: (rect.top - diagramRect.top) / scale,
        bottom: (rect.bottom - diagramRect.top) / scale,
        width: rect.width / scale,
        height: rect.height / scale
      };
    };
    const anchor = (element, side, diagramRect) => {
      const rect = relativeRect(element, diagramRect);
      if (side === "left") return { x: rect.left, y: rect.top + rect.height / 2 };
      if (side === "right") return { x: rect.right, y: rect.top + rect.height / 2 };
      if (side === "top") return { x: rect.left + rect.width / 2, y: rect.top };
      return { x: rect.left + rect.width / 2, y: rect.bottom };
    };
    const orthogonalPath = (from, to, direction) => {
      if (direction === "vertical") {
        if (Math.abs(from.x - to.x) < 1) return "M " + from.x + " " + from.y + " L " + to.x + " " + to.y;
        const midY = from.y + (to.y - from.y) / 2;
        return "M " + from.x + " " + from.y + " L " + from.x + " " + midY + " L " + to.x + " " + midY + " L " + to.x + " " + to.y;
      }
      if (Math.abs(from.y - to.y) < 1) return "M " + from.x + " " + from.y + " L " + to.x + " " + to.y;
      const midX = from.x + (to.x - from.x) / 2;
      return "M " + from.x + " " + from.y + " L " + midX + " " + from.y + " L " + midX + " " + to.y + " L " + to.x + " " + to.y;
    };
    const makePath = (d, className, tone, marker = false) => {
      const path = document.createElementNS(svgNamespace, "path");
      path.setAttribute("d", d);
      path.setAttribute("class", className);
      path.setAttribute("pathLength", "1");
      path.dataset.flowTone = tone;
      path.style.setProperty("--flow-edge-color", toneColor(tone));
      if (marker) path.setAttribute("marker-end", "url(#" + markerId() + ")");
      return path;
    };
    const logicalNodeBox = (node) => node.closest(".flow-cell") || node;
    const ensureConnectorLayer = () => {
      if (!connectorLayer) return null;
      if (!connectorDefs) {
        connectorDefs = document.createElementNS(svgNamespace, "defs");
        const markerColors = { default: "#aebbb1", context: "#18745a", design: "#18745a", delivery: "#18745a", loop: "#3b6f87", branch: "#3b6f87", gate: "#d56a28" };
        Object.entries(markerColors).forEach(([tone, color]) => {
          const marker = document.createElementNS(svgNamespace, "marker");
          marker.id = markerId(tone);
          marker.setAttribute("viewBox", "0 0 10 10");
          marker.setAttribute("refX", "10");
          marker.setAttribute("refY", "5");
          marker.setAttribute("markerWidth", "10");
          marker.setAttribute("markerHeight", "10");
          marker.setAttribute("orient", "auto");
          marker.setAttribute("markerUnits", "userSpaceOnUse");
          const arrow = document.createElementNS(svgNamespace, "path");
          arrow.setAttribute("d", "M 0 0 L 10 5 L 0 10 Z");
          arrow.setAttribute("fill", color);
          marker.appendChild(arrow);
          connectorDefs.appendChild(marker);
        });
        connectorLayer.appendChild(connectorDefs);
      }
      if (!edgeGroup) {
        edgeGroup = document.createElementNS(svgNamespace, "g");
        edgeGroup.setAttribute("class", "flow-edge-layer");
        connectorLayer.appendChild(edgeGroup);
      }
      return edgeGroup;
    };
    const clearFocus = () => {
      panel.classList.remove("has-active-node");
      panel.querySelectorAll("[data-node].flow-node--focus-related").forEach((button) => button.classList.remove("flow-node--focus-related"));
      flowEdges.forEach((edge) => {
        edge.base.classList.remove("is-focus-related", "is-focus-muted");
        edge.base.setAttribute("marker-end", "url(#" + markerId() + ")");
      });
    };
    const activateFocus = (button) => {
      if (!connectorLayer || !button) return;
      clearHover();
      const related = flowEdges.filter((edge) => edge.sourceNode === button || edge.targetNode === button);
      panel.classList.add("has-active-node");
      panel.querySelectorAll("[data-node]").forEach((nodeButton) => {
        const isRelated = nodeButton === button || related.some((edge) => edge.sourceNode === nodeButton || edge.targetNode === nodeButton);
        nodeButton.classList.toggle("flow-node--focus-related", isRelated);
      });
      flowEdges.forEach((edge) => {
        const isRelated = related.includes(edge);
        edge.base.classList.toggle("is-focus-related", isRelated);
        edge.base.classList.toggle("is-focus-muted", !isRelated);
        edge.base.setAttribute("marker-end", isRelated ? "url(#" + markerId(edge.base.dataset.flowTone) + ")" : "url(#" + markerId() + ")");
      });
    };
    const clearHover = () => {
      if (!connectorLayer) return;
      hoveredNode = null;
      panel.classList.remove("has-hover-node");
      panel.querySelectorAll("[data-node].flow-node--hover-related").forEach((button) => button.classList.remove("flow-node--hover-related"));
      flowEdges.forEach((edge) => {
        edge.base.classList.remove("is-related", "is-muted");
        edge.base.setAttribute("marker-end", "url(#" + markerId() + ")");
        edge.pulse.classList.remove("is-pulsing");
      });
    };
    const activateHover = (button) => {
      if (!connectorLayer) return;
      if (panel.classList.contains("has-active-node")) return;
      hoveredNode = button;
      const related = flowEdges.filter((edge) => edge.sourceNode === button || edge.targetNode === button);
      panel.classList.add("has-hover-node");
      panel.querySelectorAll("[data-node]").forEach((nodeButton) => {
        nodeButton.classList.toggle("flow-node--hover-related", nodeButton === button || related.some((edge) => edge.sourceNode === nodeButton || edge.targetNode === nodeButton));
      });
      flowEdges.forEach((edge) => {
        const isRelated = related.includes(edge);
        edge.base.classList.toggle("is-related", isRelated);
        edge.base.classList.toggle("is-muted", !isRelated);
        edge.base.setAttribute("marker-end", isRelated ? "url(#" + markerId(edge.base.dataset.flowTone) + ")" : "url(#" + markerId() + ")");
        edge.pulse.classList.remove("is-pulsing");
      });
      related.forEach((edge) => {
        void edge.pulse.getBoundingClientRect();
        edge.pulse.classList.add("is-pulsing");
      });
    };
    const renderConnectors = () => {
      if (!connectorLayer || !content.offsetWidth) return;
      const activeFocus = panel.querySelector('[data-node][aria-expanded="true"]');
      const activeHover = activeFocus ? null : hoveredNode;
      const diagramRect = content.getBoundingClientRect();
      const width = Math.max(1, content.offsetWidth);
      const height = Math.max(1, content.offsetHeight);
      connectorLayer.setAttribute("viewBox", "0 0 " + width + " " + height);
      connectorLayer.setAttribute("width", width);
      connectorLayer.setAttribute("height", height);
      const group = ensureConnectorLayer();
      if (!group) return;
      const nodeButtons = Array.from(content.querySelectorAll("[data-node]"));
      const edges = nodeButtons.slice(0, -1).map((sourceNode, index) => {
        const targetNode = nodeButtons[index + 1];
        const sourceElement = logicalNodeBox(sourceNode);
        const targetElement = logicalNodeBox(targetNode);
        const sourceRect = relativeRect(sourceElement, diagramRect);
        const targetRect = relativeRect(targetElement, diagramRect);
        const isNextRow = targetRect.top > sourceRect.top + Math.max(48, sourceRect.height * .65);
        const sourceSide = isNextRow ? "bottom" : "right";
        const targetSide = isNextRow ? "top" : "left";
        return {
          sourceNode,
          targetNode,
          tone: (sourceNode || targetNode)?.dataset.tone || "context",
          d: orthogonalPath(anchor(sourceElement, sourceSide, diagramRect), anchor(targetElement, targetSide, diagramRect), isNextRow ? "vertical" : "horizontal")
        };
      });

      while (flowEdges.length > edges.length) {
        const edge = flowEdges.pop();
        edge.base.remove();
        edge.pulse.remove();
      }
      edges.forEach((edgeData, index) => {
        let edge = flowEdges[index];
        if (!edge) {
          edge = {
            base: makePath(edgeData.d, "flow-edge", edgeData.tone, true),
            pulse: makePath(edgeData.d, "flow-edge-pulse", edgeData.tone, false),
            sourceNode: edgeData.sourceNode,
            targetNode: edgeData.targetNode
          };
          group.appendChild(edge.base);
          group.appendChild(edge.pulse);
          flowEdges.push(edge);
        }
        edge.sourceNode = edgeData.sourceNode;
        edge.targetNode = edgeData.targetNode;
        edge.base.setAttribute("d", edgeData.d);
        edge.pulse.setAttribute("d", edgeData.d);
        edge.base.dataset.flowTone = edgeData.tone;
        edge.pulse.dataset.flowTone = edgeData.tone;
        edge.base.style.setProperty("--flow-edge-color", toneColor(edgeData.tone));
        edge.pulse.style.setProperty("--flow-edge-color", toneColor(edgeData.tone));
      });

      if (activeFocus) activateFocus(activeFocus);
      else if (activeHover && content.contains(activeHover)) activateHover(activeHover);
      else clearHover();
    };
    const positionDetail = () => {
      const target = panel._activeFocusElement;
      if (!detail || detail.hidden || !target) return;
      const padding = 16;
      detail.style.visibility = "hidden";
      detail.style.left = padding + "px";
      detail.style.top = padding + "px";
      detail.style.visibility = "visible";
    };
    const apply = () => {
      camera.style.transform = "translate(" + state.x + "px, " + state.y + "px) scale(" + (scaleCommitted ? 1 : state.scale) + ")";
      if (supportsLayoutZoom) content.style.zoom = scaleCommitted ? String(state.scale) : "";
      if (readout) readout.value = Math.round(state.scale * 100) + "%";
      if (readout) readout.textContent = Math.round(state.scale * 100) + "%";
      positionDetail();
    };
    const setCamera = (target) => {
      state.scale = target.scale;
      state.x = target.x;
      state.y = target.y;
      apply();
    };
    const releaseScale = () => {
      if (!scaleCommitted) return;
      scaleCommitted = false;
      apply();
    };
    const commitScale = () => {
      if (!supportsLayoutZoom || scaleCommitted) return;
      scaleCommitted = true;
      apply();
    };
    const stopCameraMotion = () => {
      cameraGeneration += 1;
      if (cameraFrame !== null) window.cancelAnimationFrame(cameraFrame);
      cameraFrame = null;
      camera.classList.remove("is-camera-moving");
    };
    const animateCamera = (target, duration) => {
      releaseScale();
      const start = { scale: state.scale, x: state.x, y: state.y };
      stopCameraMotion();
      const generation = ++cameraGeneration;
      const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduceMotion || !duration) {
        setCamera(target);
        commitScale();
        renderConnectors();
        return;
      }
      let startedAt = 0;
      camera.classList.add("is-camera-moving");
      const step = (timestamp) => {
        if (generation !== cameraGeneration) return;
        if (!startedAt) startedAt = timestamp;
        const progress = Math.min(1, Math.max(0, (timestamp - startedAt) / duration));
        const eased = 1 - Math.pow(1 - progress, 3);
        setCamera({
          scale: start.scale + (target.scale - start.scale) * eased,
          x: start.x + (target.x - start.x) * eased,
          y: start.y + (target.y - start.y) * eased
        });
        if (progress < 1) {
          cameraFrame = window.requestAnimationFrame(step);
          return;
        }
        cameraFrame = null;
        camera.classList.remove("is-camera-moving");
        commitScale();
        renderConnectors();
      };
      cameraFrame = window.requestAnimationFrame(step);
    };
    const centeredTarget = (scale) => {
      const width = Math.max(1, content.offsetWidth);
      const height = Math.max(1, content.offsetHeight);
      return {
        scale,
        x: (viewport.clientWidth - width * scale) / 2,
        y: (viewport.clientHeight - height * scale) / 2
      };
    };
    const defaultView = (options = {}) => {
      releaseScale();
      const target = centeredTarget(defaultCameraScale);
      if (options.animate) animateCamera(target, options.duration || 420);
      else {
        stopCameraMotion();
        setCamera(target);
        commitScale();
        renderConnectors();
      }
    };
    const fit = (options = {}) => {
      releaseScale();
      const padding = 42;
      const width = Math.max(1, content.offsetWidth);
      const height = Math.max(1, content.offsetHeight);
      const scale = Math.min(1, (viewport.clientWidth - padding) / width, (viewport.clientHeight - padding) / height);
      const target = centeredTarget(clamp(scale, .7, 1));
      if (options.animate) animateCamera(target, options.duration || 420);
      else {
        stopCameraMotion();
        setCamera(target);
        commitScale();
        renderConnectors();
      }
    };
    const zoom = (delta) => {
      const next = clamp(state.scale + delta, .42, 1.6);
      if (next === state.scale) return;
      const centerX = viewport.clientWidth / 2;
      const centerY = viewport.clientHeight / 2;
      const contentX = (centerX - state.x) / state.scale;
      const contentY = (centerY - state.y) / state.scale;
      animateCamera({
        scale: next,
        x: centerX - contentX * next,
        y: centerY - contentY * next
      }, 220);
    };
    const focus = (target) => {
      if (!target) return;
      const viewportRect = viewport.getBoundingClientRect();
      const targetRect = target.getBoundingClientRect();
      const currentScale = state.scale || 1;
      const targetCenterX = targetRect.left + targetRect.width / 2 - viewportRect.left;
      const targetCenterY = targetRect.top + targetRect.height / 2 - viewportRect.top;
      const contentX = (targetCenterX - state.x) / currentScale;
      const contentY = (targetCenterY - state.y) / currentScale;
      const nextScale = clamp(Math.max(currentScale, .92), .42, 1.6);
      animateCamera({
        scale: nextScale,
        x: viewport.clientWidth / 2 - contentX * nextScale,
        y: viewport.clientHeight / 2 - contentY * nextScale
      }, 420);
    };
    const resetView = () => { closeDetails(panel); defaultView({ animate: true, duration: 420 }); };
    panel.querySelectorAll("[data-camera-action]").forEach((button) => {
      button.addEventListener("click", () => {
        if (button.dataset.cameraAction === "fit") {
          closeDetails(panel);
          fit({ animate: true, duration: 420 });
        }
        if (button.dataset.cameraAction === "zoom-in") zoom(.1);
        if (button.dataset.cameraAction === "zoom-out") zoom(-.1);
      });
    });
    viewport.addEventListener("wheel", (event) => {
      event.preventDefault();
      zoom(event.deltaY > 0 ? -.06 : .06);
    }, { passive: false });
    viewport.addEventListener("pointerdown", (event) => {
      if (event.target.closest("button, a, input, output, .node-detail, .diagram-overlay")) return;
      stopCameraMotion();
      commitScale();
      state.pointerId = event.pointerId;
      state.startX = event.clientX;
      state.startY = event.clientY;
      state.originX = state.x;
      state.originY = state.y;
      state.moved = false;
      viewport.classList.add("is-panning");
      viewport.setPointerCapture(event.pointerId);
    });
    viewport.addEventListener("pointermove", (event) => {
      if (state.pointerId !== event.pointerId) return;
      const dx = event.clientX - state.startX;
      const dy = event.clientY - state.startY;
      if (Math.abs(dx) + Math.abs(dy) > 4) state.moved = true;
      state.x = state.originX + dx;
      state.y = state.originY + dy;
      apply();
    });
    const endPan = (event) => {
      if (state.pointerId !== event.pointerId) return;
      const shouldReset = event.type === "pointerup" && !state.moved;
      state.pointerId = null;
      viewport.classList.remove("is-panning");
      try { viewport.releasePointerCapture(event.pointerId); } catch (_) { /* already released */ }
      if (shouldReset) resetView();
    };
    viewport.addEventListener("pointerup", endPan);
    viewport.addEventListener("pointercancel", endPan);
    viewport.addEventListener("keydown", (event) => {
      if (event.key === "+" || event.key === "=") { event.preventDefault(); zoom(.1); }
      if (event.key === "-") { event.preventDefault(); zoom(-.1); }
      if (event.key === "0") { event.preventDefault(); resetView(); }
    });
    content.querySelectorAll("[data-node]").forEach((button) => {
      button.addEventListener("mouseenter", () => activateHover(button));
      button.addEventListener("mouseleave", () => {
        if (hoveredNode === button) clearHover();
      });
    });
    panel._fitCamera = defaultView;
    panel._focusCamera = focus;
    panel._resetView = resetView;
    panel._stopCameraMotion = stopCameraMotion;
    panel._activateNodeFocus = activateFocus;
    panel._clearNodeFocus = clearFocus;
    document.addEventListener("click", (event) => {
      if (panel.hidden) return;
      const openDetail = panel.querySelector(".node-detail:not([hidden])");
      if (!openDetail || openDetail.contains(event.target)) return;
      if (event.target.closest("[data-node], [data-camera-action], .entry-tab")) return;
      resetView();
    });
    requestAnimationFrame(defaultView);
  }

  tabs.forEach((tab) => setupCamera(document.getElementById(tab.getAttribute("aria-controls"))));
  window.addEventListener("resize", () => {
    const panel = activeEntryPanel();
    syncUsageViewport(panel);
    if (panel && panel._fitCamera) panel._fitCamera();
  });

  function closeDetails(panel, restoreFocus = false) {
    const detail = panel.querySelector(".node-detail");
    detail.hidden = true;
    detail.style.removeProperty("left");
    detail.style.removeProperty("top");
    detail.style.removeProperty("visibility");
    if (panel._clearNodeFocus) panel._clearNodeFocus();
    else panel.classList.remove("has-active-node");
    panel._activeFocusElement = null;
    panel.querySelectorAll("[data-node]").forEach((button) => button.setAttribute("aria-expanded", "false"));
    if (restoreFocus && activeNode && panel.contains(activeNode)) activeNode.focus();
    activeNode = null;
  }

  function selectEntry(entry, focus = false) {
    tabs.forEach((tab) => {
      const selected = tab.dataset.entry === entry;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      const panel = document.getElementById(tab.getAttribute("aria-controls"));
      if (panel._stopCameraMotion) panel._stopCameraMotion();
      closeDetails(panel);
      panel.hidden = !selected;
      if (selected && panel._fitCamera) requestAnimationFrame(() => {
        syncUsageViewport(panel);
        panel._fitCamera();
      });
      if (selected && focus) tab.focus();
    });
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectEntry(tab.dataset.entry));
    tab.addEventListener("keydown", (event) => {
      let target;
      if (event.key === "ArrowRight") target = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") target = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") target = 0;
      if (event.key === "End") target = tabs.length - 1;
      if (target === undefined) return;
      event.preventDefault();
      selectEntry(tabs[target].dataset.entry, true);
    });
  });

  document.querySelectorAll('a[href="#usage"]').forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      try {
        if (window.location.hash !== "#usage") window.history.pushState(null, "", "#usage");
      } catch (_) {
        window.location.hash = "usage";
      }
      scheduleUsageLayout({ align: true, behavior: "smooth" });
    });
  });
  window.addEventListener("hashchange", () => {
    if (window.location.hash === "#usage") scheduleUsageLayout({ align: true });
  });
  window.addEventListener("load", () => {
    scheduleUsageLayout({ align: window.location.hash === "#usage" });
  }, { once: true });

  function showDetail(button) {
    const panel = button.closest(".entry-panel");
    const entry = panel.id.replace("panel-", "");
    const detail = panel.querySelector(".node-detail");
    if (button.getAttribute("aria-expanded") === "true") {
      if (panel._resetView) panel._resetView();
      else closeDetails(panel);
      return;
    }
    const item = detailsFor(button.dataset.node, entry);
    closeDetails(panel);
    activeNode = button;
    panel._activeFocusElement = button;
    panel.classList.add("has-active-node");
    button.setAttribute("aria-expanded", "true");
    if (panel._activateNodeFocus) panel._activateNodeFocus(button);
    detail.dataset.tone = nodeTone(button.dataset.node, item);
    const fields = [["做什么", item.action], ["输入是什么", item.input], ["产出什么", item.output], ["何时完成", item.done]];
    detail.innerHTML = '<header><div><h4 id="detail-title-' + entry + '">' + escape(item.title) +
      '</h4><code class="detail-skill">对应 skill：' + escape(item.skill) +
      '</code></div><button type="button" class="detail-close" aria-label="关闭节点详情">收起 ×</button></header>' +
      '<dl class="detail-fields">' + fields.map(([label, value]) =>
        "<div><dt>" + label + "</dt><dd>" + escape(value) + "</dd></div>").join("") + "</dl>" +
      (item.note ? '<p class="detail-note">' + escape(item.note) + "</p>" : "");
    detail.hidden = false;
    if (panel._focusCamera) panel._focusCamera(button);
    detail.focus({ preventScroll: true });
  }

  panelsRoot.addEventListener("click", (event) => {
    const button = event.target.closest("[data-node]");
    if (button) showDetail(button);
    const close = event.target.closest(".detail-close");
    if (close) {
      const panel = close.closest(".entry-panel");
      if (panel._resetView) panel._resetView();
      else closeDetails(panel, true);
    }
  });
  panelsRoot.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && event.target.closest(".node-detail")) {
      event.preventDefault();
      const panel = event.target.closest(".entry-panel");
      if (panel._resetView) panel._resetView();
      else closeDetails(panel, true);
    }
  });

  async function copyCommand() {
    const text = document.getElementById("start-command").textContent;
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return;
      } catch (_) { /* Fall back for local pages or restricted clipboard permissions. */ }
    }
    const input = document.createElement("textarea");
    input.value = text;
    input.setAttribute("readonly", "");
    input.style.cssText = "position:fixed;left:-9999px;top:0";
    document.body.appendChild(input);
    try {
      input.select();
      if (!document.execCommand("copy")) throw new Error("Clipboard unavailable");
    } finally {
      input.remove();
    }
  }

  document.getElementById("copy-command").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const status = document.getElementById("copy-status");
    button.disabled = true;
    try {
      await copyCommand();
      status.textContent = "已复制启动命令";
    } catch (_) {
      status.textContent = "复制失败，请选中命令手动复制。";
    } finally {
      button.disabled = false;
      button.focus({ preventScroll: true });
    }
  });
})();
