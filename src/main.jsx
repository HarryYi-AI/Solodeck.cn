import React, { lazy, useEffect, useMemo, useRef, useState, Suspense } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity, ArrowRight, BarChart3, Check, CheckCircle2, ChevronDown, Circle,
  Database, FileText, FileUp, GitBranch, History, Layers3, Loader2, Menu,
  MessageSquare, Mic, MicOff, PanelRightClose, PanelRightOpen, PauseCircle,
  LogIn, LogOut, Plus, Rocket, Search, Send, ShieldCheck, Sparkles, Table2,
  Trash2, UploadCloud, UserRound, Workflow, X
} from "lucide-react";
import "./styles.css";

const pages = [
  { id: "chat", label: "分析工作台", icon: MessageSquare },
  { id: "upload", label: "数据源", icon: Database },
  { id: "runs", label: "任务记录", icon: History },
  { id: "diagnose", label: "质量检查", icon: BarChart3 },
  { id: "decision", label: "进阶分析", icon: ShieldCheck },
  { id: "agent", label: "关系探索", icon: GitBranch },
  { id: "actions", label: "行动方案", icon: CheckCircle2 }
];

const ResultChart = lazy(() => import("./ResultChart.jsx"));

const questions = [
  { id: "pain_point_title", label: "痛点标题是否提升咨询" },
  { id: "platform_conversion", label: "哪个平台更适合转化" },
  { id: "series_continue", label: "这个系列是否继续" },
  { id: "favorite_to_product", label: "高收藏内容是否值得产品化" }
];

const cache = new Map();
const displayMap = {
  platform: "平台",
  title_style: "标题风格",
  topic: "主题",
  series_id: "内容系列",
  consultations: "咨询数",
  conversions: "成交数",
  revenue: "收入",
  favorite_rate: "收藏率",
  pain_point: "痛点型",
  tutorial: "教程型",
  tiktok: "TikTok",
  douyin: "抖音",
  bilibili: "B站",
  xiaohongshu: "小红书",
  wechat: "公众号/视频号",
  zhihu: "知乎",
  substack: "Substack",
  instagram: "Instagram",
  x: "X / Twitter",
  twitter: "X / Twitter",
  uploaded_data: "当前上传数据",
  "Continue": "继续放大",
  "Reduce-Pause": "减少投入",
  "Validate Next Week": "下周验证"
};

function cn(value) {
  return displayMap[value] || value || "";
}

function actionIcon(type) {
  const label = cn(type);
  if (label === "继续放大") return Rocket;
  if (label === "减少投入") return PauseCircle;
  return CheckCircle2;
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value || 0);
}

function percent(value) {
  return `${((value || 0) * 100).toFixed(2)}%`;
}

function ciStatus(effect) {
  const low = Number(effect?.ci_95?.[0] || 0);
  const high = Number(effect?.ci_95?.[1] || 0);
  if (low > 0) return { level: "good", title: "结果较稳", detail: "整个区间都高于 0，可以考虑小幅放大。" };
  if (high < 0) return { level: "bad", title: "可能无效", detail: "整个区间都低于 0，建议暂停或换变量验证。" };
  return { level: "watch", title: "先验证", detail: "区间穿过 0，说明结果还不够稳定，不适合直接放大。" };
}

const API_UNAVAILABLE =
  "分析服务暂时繁忙，请稍后重试。";

async function parseApiResponse(res) {
  const raw = await res.text();
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    if (/^\s*</.test(raw) || /<!doctype/i.test(raw)) {
      throw new Error(API_UNAVAILABLE);
    }
    throw new Error(raw.slice(0, 160) || "请求失败");
  }
}

async function apiPost(path, body) {
  const key = `${path}:${JSON.stringify(body || {})}`;
  const noCache = path.includes("/api/v4/chat") || path.includes("/api/data-agent/query") || path.includes("/api/auth/");
  if (!noCache && cache.has(key)) return cache.get(key);
  const promise = fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {})
  }).then(async (res) => {
    const data = await parseApiResponse(res);
    if (!res.ok) throw new Error(data.error || API_UNAVAILABLE);
    return data;
  });
  if (!noCache) cache.set(key, promise);
  return promise;
}

async function apiGet(path) {
  const res = await fetch(path);
  const data = await parseApiResponse(res);
  if (!res.ok) throw new Error(data.error || API_UNAVAILABLE);
  return data;
}

async function apiDelete(path) {
  const res = await fetch(path, { method: "DELETE" });
  const data = await parseApiResponse(res);
  if (!res.ok) throw new Error(data.error || API_UNAVAILABLE);
  return data;
}

function AuthModal({ open, onClose, onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!open) return null;

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const data = await apiPost(`/api/auth/${mode}`, {
        email,
        password,
        display_name: displayName
      });
      cache.clear();
      onAuthenticated(data);
      onClose();
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="auth-modal" role="dialog" aria-modal="true" aria-label="SoloDeck 账号">
        <button className="modal-close" type="button" onClick={onClose} aria-label="关闭"><X size={18} /></button>
        <span className="auth-mark"><span className="mini-logo" /></span>
        <h2>{mode === "login" ? "欢迎回来" : "建立你的分析空间"}</h2>
        <p>登录后，数据、对话与分析记录只保存在你的工作区。</p>
        <div className="auth-tabs">
          <button className={mode === "login" ? "active" : ""} type="button" onClick={() => { setMode("login"); setError(""); }}>登录</button>
          <button className={mode === "register" ? "active" : ""} type="button" onClick={() => { setMode("register"); setError(""); }}>注册</button>
        </div>
        <form onSubmit={submit}>
          {mode === "register" ? <label>称呼<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="例如：林杰" autoComplete="name" /></label> : null}
          <label>邮箱或手机号<input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@example.com" autoComplete="username" required /></label>
          <label>密码<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="至少 6 位" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={6} required /></label>
          {error ? <div className="auth-error">{error}</div> : null}
          <button className="auth-submit" type="submit" disabled={loading}>{loading ? <Loader2 className="spin" size={17} /> : null}{mode === "login" ? "登录" : "注册并进入"}</button>
        </form>
        <small>未登录时也可试用，记录只保存在当前浏览器工作区。</small>
      </section>
    </div>
  );
}

function Trace({ trace }) {
  useEffect(() => {
    if (trace?.length) {
      window.__SOLODECK_TRACE__ = trace;
    }
  }, [trace]);
  return null;
}

function DataIntakePanel({ datasetId, setDatasetId, setMapping, setPage, workspaceId, onUploaded, compact = false }) {
  const inputRef = useRef(null);
  const [files, setFiles] = useState([]);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [tasks, setTasks] = useState([]);

  async function upload(selected) {
    if (!selected.length && !text.trim()) return;
    setLoading(true);
    setNotice("正在识别字段和截图内容。");
    const form = new FormData();
    selected.forEach((file) => form.append("files", file));
    form.append("text", text);
    form.append("workspace_id", workspaceId);
    if (datasetId) form.append("append_to_dataset_id", datasetId);
    try {
      const res = await fetch("/api/upload", { method: "POST", body: form });
      const data = await parseApiResponse(res);
      if (!res.ok) throw new Error(data.error || "上传失败");
      setDatasetId(data.dataset_id);
      setMapping(data.mapping);
      setTasks(data.tasks || []);
      onUploaded?.(data.dataset);
      cache.clear();
      setNotice(data.appended ? `已补充 ${data.added_rows} 条记录，可以沿用当前对话继续分析。` : "资料已进入分析区，可以直接开始提问。");
      setTimeout(() => setPage?.("chat"), 240);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={`panel intake-panel ${compact ? "compact" : ""}`}>
      <div className="intake-head">
        <div>
          <span className="eyebrow">{compact ? "快速接入" : "上传"}</span>
          <h3>{compact ? "截图、表格、文字都能直接进入分析" : "连接需要分析的数据"}</h3>
          <p>支持 CSV / Excel / ZIP / PNG / JPG / WEBP / TXT。截图会自动抽取关键信息，不展示原始明细。</p>
        </div>
        {datasetId ? <div className="dataset-chip">当前数据集已就绪</div> : null}
      </div>

      <div className={`intake-grid ${compact ? "compact" : ""}`}>
        <div className="upload-card" onClick={() => inputRef.current?.click()}>
          {loading ? <Loader2 className="spin" size={34} /> : <UploadCloud size={38} />}
          <strong>{loading ? "正在处理" : "点击上传资料或截图"}</strong>
          <span>后台报表、收入截图、聊天记录、A/B 结果、反馈图片都可以直接放进来。</span>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".csv,.xlsx,.xls,.zip,.png,.jpg,.jpeg,.webp,.txt,.md,.json"
            onChange={(event) => {
              const selected = [...event.target.files];
              setFiles(selected);
              upload(selected);
            }}
          />
        </div>

        <div className="panel text-panel inner">
          <h3>也可以直接粘贴文字</h3>
          <p>适合补充会议纪要、用户反馈、商单进度、待办事项。</p>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="例如：小红书咨询多但成交慢；今天收到品牌方报价；周五前要交付复盘。"
          />
          <button className="primary-btn" onClick={() => upload(files)}>读取并进入分析</button>
        </div>
      </div>

      <div className="file-row">
        {files.length ? files.map((file) => <span key={file.name}>{file.name}</span>) : <span>上传后会保存到当前工作区，可随时继续分析。</span>}
      </div>

      {tasks.length ? (
        <div className="task-hints">
          {tasks.slice(0, 3).map((task, index) => (
            <div key={`${task.title}-${index}`} className="task-hint">
              <strong>{task.title}</strong>
              <small>{task.detail || task.due_at || "已加入后续分析线索"}</small>
            </div>
          ))}
        </div>
      ) : null}

      {notice && <div className="notice">{notice}</div>}
    </div>
  );
}

const operationLabels = {
  retrieve_memory: "检索上下文",
  compile_task: "编译任务",
  plan_steps: "生成计划",
  execute_analysis: "执行分析",
  validate_artifacts: "校验结果",
  compose_response: "生成回答",
  clarify: "澄清问题",
  LoadDataset: "读取数据",
  ProfileSchema: "检查字段",
  ResolveEntities: "匹配业务含义",
  JoinTables: "连接数据表",
  CreateMetric: "计算指标",
  Describe: "比较数据",
  CausalReadiness: "检查分析条件",
  Bootstrap: "评估稳定性",
  Regression: "调整影响因素",
  ValidateClaim: "核对结论",
  GenerateReport: "整理回答",
  SchemaSkill: "识别数据结构",
  DataQualitySkill: "检查数据质量",
  AutoInsightsSkill: "扫描数据洞察",
  DescriptiveComparisonSkill: "计算分组结果",
  KGConstructionSkill: "构建关系证据",
  CausalDiscoverySkill: "生成候选关系",
  CausalReadinessSkill: "检查分析条件",
  BootstrapSkill: "计算稳定区间",
  RegressionSkill: "调整影响因素",
  DIDSkill: "估计前后差异",
  CounterfactualSkill: "模拟策略变化",
  ReportSkill: "整理结果"
};

const liveStages = [
  { label: "理解问题", detail: "识别目标、指标和比较对象" },
  { label: "匹配数据", detail: "定位数据表、字段与历史状态" },
  { label: "执行分析", detail: "运行真实的数据与统计技能" },
  { label: "检查结果", detail: "重算关键指标并限制结论强度" },
  { label: "保存状态", detail: "记录产物血缘，支持继续追问" }
];

function evidenceLabel(level) {
  const labels = {
    descriptive_pattern: "直接观察",
    adjusted_association: "调整后关联",
    exploratory_causal_hypothesis: "待验证假设",
    quasi_causal_estimate: "准实验估计",
    experimental_evidence: "实验结果"
  };
  const numericLevels = {
    1: "直接观察",
    2: "调整后关联",
    3: "待验证假设",
    4: "准实验估计",
    5: "实验结果"
  };
  return labels[level] || numericLevels[level] || "已核对结果";
}

function ResultArtifact({ message }) {
  const artifact = message.artifact || {};
  const run = message.run || {};
  const resultView = run.result_view || {};
  const actions = artifact.action_cards || artifact.actions || [];
  const validation = run.validation_report || message.validation || {};
  const state = run.analytical_state_summary || {};
  if (!actions.length && !run.state_id && !resultView.rows?.length) return null;
  return (
    <div className="answer-artifacts">
      {resultView.rows?.length ? (
        <div className="result-view">
          <div className="result-view-head"><strong>{resultView.title}</strong><span>{resultView.rows.length} 项结果</span></div>
          <div className="result-view-grid">
            <div className="result-table-wrap">
              <table className="result-table">
                <thead><tr>{resultView.columns.map((column) => <th key={column}>{resultView.column_labels?.[column] || column}</th>)}</tr></thead>
                <tbody>{resultView.rows.slice(0, 8).map((row, index) => (
                  <tr key={`${row.name || row.metric || "row"}-${index}`}>{resultView.columns.map((column) => <td key={column}>{row[column] ?? "-"}</td>)}</tr>
                ))}</tbody>
              </table>
            </div>
            {resultView.chart ? <Suspense fallback={<div className="chart-loading"><Loader2 className="spin" size={18} />正在绘制</div>}><ResultChart chart={resultView.chart} /></Suspense> : null}
          </div>
        </div>
      ) : null}
      {actions.length ? (
        <div className="answer-actions">
          {actions.slice(0, 3).map((card, index) => (
            <div className="answer-action" key={`${card.title || card.action}-${index}`}>
              <span>{index + 1}</span>
              <div>
                <strong>{cn(card.recommendation || card.title || card.action)}</strong>
                <small>{card.next_step || card.explanation || card.evidence || "按建议继续记录结果。"}</small>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      <div className="answer-proof">
        <span><ShieldCheck size={14} />{evidenceLabel(run.evidence_level || state.evidence_level)}</span>
        <span className={validation.valid === false ? "check-bad" : "check-good"}>
          {validation.valid === false ? "需要复核" : "检查通过"}
        </span>
        {run.state_id ? <span>状态 {run.state_id.slice(-8)}</span> : null}
      </div>
    </div>
  );
}

function RunInspector({ run, loading, phase, history, collapsed, setCollapsed, onRestore }) {
  const [tab, setTab] = useState("run");
  const workflow = run?.workflow_summary || {};
  const state = run?.analytical_state_summary || {};
  const agentTrace = run?.data_agent_trace || {};
  const acquisitionSteps = agentTrace.trace || [];
  const operations = run?.executed_skills?.length ? run.executed_skills : (workflow.operations || []);
  const validation = run?.validation_report || workflow.validation || {};
  const task = run?.task_spec || {};

  if (collapsed) {
    return (
      <button className="inspector-restore" type="button" onClick={() => setCollapsed(false)} title="打开分析过程">
        <PanelRightOpen size={18} />
      </button>
    );
  }

  return (
    <aside className="run-inspector">
      <div className="inspector-head">
        <div>
          <span>分析过程</span>
          <strong>{loading ? "正在运行" : run ? "本次分析已完成" : "等待问题"}</strong>
        </div>
        <button type="button" onClick={() => setCollapsed(true)} title="收起分析过程"><PanelRightClose size={18} /></button>
      </div>

      <div className="inspector-tabs" role="tablist">
        <button className={tab === "run" ? "active" : ""} onClick={() => setTab("run")}>运行</button>
        <button className={tab === "data" ? "active" : ""} onClick={() => setTab("data")}>数据</button>
        <button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>状态</button>
      </div>

      {tab === "run" && (
        <div className="inspector-body">
          {loading ? liveStages.map((item, index) => (
            <div className={`run-step ${index < phase ? "done" : index === phase ? "current" : "waiting"}`} key={item.label}>
              <span className="step-dot">{index < phase ? <Check size={12} /> : index === phase ? <Loader2 className="spin" size={12} /> : <Circle size={9} />}</span>
              <div><strong>{item.label}</strong><small>{item.detail}</small></div>
            </div>
          )) : acquisitionSteps.length ? acquisitionSteps.map((item, index) => (
            <div className={`run-step ${item.status === "success" ? "done" : "failed"}`} key={item.step_id || index}>
              <span className="step-dot">{item.status === "success" ? <Check size={12} /> : <X size={12} />}</span>
              <div><strong>{item.goal}</strong><small>{item.observation} · {Number(item.latency_ms || 0).toFixed(1)} 毫秒</small></div>
            </div>
          )) : operations.length ? operations.map((item, index) => (
            <div className="run-step done" key={`${item}-${index}`}>
              <span className="step-dot"><Check size={12} /></span>
              <div><strong>{operationLabels[item] || item}</strong><small>{index === operations.length - 1 ? "回答及分析状态已保存" : "已生成可追溯的中间结果"}</small></div>
            </div>
          )) : (
            <div className="inspector-empty"><Workflow size={25} /><p>提出问题后，这里会显示真实的数据匹配、计算和检查过程。</p></div>
          )}
          {run ? (
            <div className="run-summary">
              <div><span>结论等级</span><strong>{evidenceLabel(run.evidence_level || state.evidence_level)}</strong></div>
              <div><span>结果检查</span><strong>{validation.valid === false ? "需要复核" : "通过"}</strong></div>
              <div><span>本次成本</span><strong>{Number(run.cost_spent || 0).toFixed(2)}</strong></div>
              <div><span>工具调用</span><strong>{acquisitionSteps.length || operations.length}</strong></div>
            </div>
          ) : null}
        </div>
      )}

      {tab === "data" && (
        <div className="inspector-body">
          <div className="scope-block"><span>分析目标</span><strong>{task.objective || task.user_goal || agentTrace.task_spec?.user_goal || "等待问题"}</strong></div>
          <div className="scope-block"><span>使用数据</span><strong>{(state.selected_tables || []).map(cn).join("、") || "演示数据"}</strong></div>
          <div className="scope-block"><span>关键字段</span><div className="field-list">{(state.selected_columns?.length ? state.selected_columns : agentTrace.task_spec?.candidate_columns || []).slice(0, 10).map((item) => <code key={item}>{cn(item)}</code>)}</div></div>
          <div className="scope-block"><span>分析产物</span><strong>{agentTrace.artifact_count ?? (state.artifacts || []).length} 个</strong></div>
          <div className="scope-block"><span>结果校验</span><strong>{agentTrace.critique?.valid === false ? "发现问题" : "已通过"}</strong></div>
        </div>
      )}

      {tab === "history" && (
        <div className="inspector-body">
          {history.length ? history.slice().reverse().map((item, index) => (
            <div className={`state-row ${index === 0 ? "current" : ""}`} key={item.state_id || index}>
              <History size={15} />
              <div><strong>{index === 0 ? "当前分析" : `历史分析 ${history.length - index}`}</strong><small>{item.summary || `状态 ${(item.state_id || "").slice(-8)}`}</small></div>
              {index > 0 && item.state_id ? <button type="button" onClick={() => onRestore(item.state_id)}>恢复</button> : null}
            </div>
          )) : <div className="inspector-empty"><History size={25} /><p>每次完成分析后都会保存状态，后续可以继续追问、比较或回退。</p></div>}
        </div>
      )}
    </aside>
  );
}

function ChatPage({ datasetId, dataset, mapping, setPage, workspaceId, threadId, setThreadId, onRunComplete }) {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [runPhase, setRunPhase] = useState(0);
  const [latestRun, setLatestRun] = useState(null);
  const [runHistory, setRunHistory] = useState([]);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(
    () => typeof window !== "undefined" && window.innerWidth < 760
  );
  const [listening, setListening] = useState(false);
  const [voiceTip, setVoiceTip] = useState("");
  const bottomRef = useRef(null);
  const recognitionRef = useRef(null);

  function speakReply(text) {
    if (!text || typeof window === "undefined" || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new window.SpeechSynthesisUtterance(text.slice(0, 140));
    utterance.lang = "zh-CN";
    utterance.rate = 1;
    window.speechSynthesis.speak(utterance);
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (!loading) return undefined;
    setRunPhase(0);
    const timer = window.setInterval(() => setRunPhase((value) => Math.min(value + 1, liveStages.length - 1)), 900);
    return () => window.clearInterval(timer);
  }, [loading]);

  useEffect(() => {
    setSessionId(null);
    setMessages([]);
    setLatestRun(null);
    setRunHistory([]);
  }, [datasetId]);

  useEffect(() => {
    if (!threadId) return;
    let active = true;
    apiGet(`/api/data-agent/threads/${threadId}?workspace_id=${encodeURIComponent(workspaceId)}`)
      .then((thread) => {
        if (!active) return;
        setSessionId(thread.session_id || null);
        const restored = (thread.messages || []).map((message) => ({
          role: message.role,
          content: message.content,
          artifact: message.result?.user_artifact,
          validation: message.result?.validation_report,
          run: message.result
        }));
        setMessages(restored);
        const assistantRuns = restored.filter((message) => message.role === "assistant" && message.run);
        setLatestRun(assistantRuns.at(-1)?.run || null);
        setRunHistory(assistantRuns.map((message) => ({
          state_id: message.run?.state_id,
          summary: message.content?.slice(0, 80)
        })).filter((item) => item.state_id));
      })
      .catch(() => {
        if (active) setThreadId(null);
      });
    return () => { active = false; };
  }, [threadId, workspaceId]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 760px)");
    const collapseOnMobile = (event) => {
      if (event.matches) setInspectorCollapsed(true);
    };
    media.addEventListener?.("change", collapseOnMobile);
    return () => media.removeEventListener?.("change", collapseOnMobile);
  }, []);

  async function send(preset) {
    const text = (preset || input).trim();
    if (!text || loading) return;
    if (!datasetId) {
      setMessages((prev) => [...prev, { role: "assistant", content: "请先上传或选择一个数据集，再开始分析。", error: true }]);
      setPage("upload");
      return;
    }
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);
    try {
      const data = await apiPost("/api/data-agent/query", {
        session_id: sessionId,
        thread_id: threadId,
        dataset_id: datasetId,
        workspace_id: workspaceId,
        message: text
      });
      setSessionId(data.session_id);
      setThreadId(data.thread_id);
      window.__SOLODECK_AGENT_RUN__ = data;
      setLatestRun(data);
      if (data.state_id) setRunHistory((prev) => [...prev, { state_id: data.state_id, summary: text }]);
      onRunComplete?.(data.run);
      setMessages((prev) => [...prev, {
        role: "assistant",
        content: data.reply,
        artifact: data.user_artifact,
        validation: data.validation_report,
        run: data
      }]);
      speakReply(data.reply);
    } catch (error) {
      setMessages((prev) => [...prev, { role: "assistant", content: error.message, error: true }]);
    } finally {
      setLoading(false);
    }
  }

  async function sendVoice(transcript) {
    const text = transcript.trim();
    if (!text || loading) return;
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);
    setVoiceTip("正在把语音转成经营建议…");
    try {
      const data = await apiPost("/api/data-agent/query", {
        session_id: sessionId,
        thread_id: threadId,
        dataset_id: datasetId,
        workspace_id: workspaceId,
        message: text
      });
      setSessionId(data.session_id || sessionId);
      setThreadId(data.thread_id);
      window.__SOLODECK_AGENT_RUN__ = data;
      setLatestRun(data);
      if (data.state_id) setRunHistory((prev) => [...prev, { state_id: data.state_id, summary: text }]);
      onRunComplete?.(data.run);
      setMessages((prev) => [...prev, {
        role: "assistant",
        content: data.reply,
        artifact: data.user_artifact,
        run: data
      }]);
      speakReply(data.reply);
    } catch (error) {
      setMessages((prev) => [...prev, { role: "assistant", content: error.message, error: true }]);
    } finally {
      setLoading(false);
      setVoiceTip("");
    }
  }

  function toggleVoice() {
    const Recognition = typeof window !== "undefined" ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
    if (!Recognition) {
      setVoiceTip("当前浏览器不支持直接语音输入，请改用 Chrome 或 Edge。");
      return;
    }
    if (listening && recognitionRef.current) {
      recognitionRef.current.stop();
      setListening(false);
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "zh-CN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => {
      setListening(true);
      setVoiceTip("正在听，请直接说出经营问题。");
    };
    recognition.onresult = (event) => {
      const transcript = event?.results?.[0]?.[0]?.transcript || "";
      setInput(transcript);
      sendVoice(transcript);
    };
    recognition.onerror = () => {
      setVoiceTip("没有听清楚，可以再说一次。");
      setListening(false);
    };
    recognition.onend = () => {
      setListening(false);
    };
    recognitionRef.current = recognition;
    recognition.start();
  }

  const starters = [
    "小红书痛点标题是不是比教程标题更能带来咨询？",
    "哪个平台转化更好？",
    "继续看成交数的变化"
  ];

  return (
    <section className={`page workspace-page ${inspectorCollapsed ? "inspector-hidden" : ""}`}>
      <header className="workspace-head">
        <div><span className="workspace-kicker">有状态 · 可验证 · 可追溯</span><h1>SoloDeck 数据智能体</h1></div>
        <div className="workspace-status"><span className={loading ? "busy" : "ready"} />{loading ? "正在分析" : "可以提问"}</div>
      </header>

      <div className="data-context">
        <div className="data-context-main"><span className="source-icon"><Database size={17} /></span><div><strong>{dataset?.name || (datasetId ? "当前数据已连接" : "尚未连接数据")}</strong><span>{dataset ? `${dataset.row_count} 行 · ${dataset.column_count} 列` : "上传表格、截图或文字后开始分析"}</span></div></div>
        <div className="data-context-meta"><span><Table2 size={14} />{mapping?.mapped_fields?.length || 0} 个已识别字段</span><span><ShieldCheck size={14} />数据仅用于本次分析</span></div>
        <button className="icon-text-btn" type="button" onClick={() => setPage("upload")}><FileUp size={16} />添加数据</button>
      </div>

      <div className="agent-workbench">
        <div className="conversation-column">
          <div className="chat-panel">
            {messages.length === 0 && (
              <div className="chat-empty workspace-empty">
                <div className="empty-mark"><Sparkles size={22} /></div>
                <span className="empty-eyebrow">你的数据分析助手</span>
                <h2>{datasetId ? "今天想从数据里确认什么？" : "连接数据，然后直接提问"}</h2>
                <p>{datasetId ? "描述目标即可。系统会定位字段、编排技能、执行计算并核对答案。" : "支持表格、截图和文字。无需整理字段，也不用先选择分析方法。"}</p>
                <div className="agent-capabilities execution-flow">
                  <span><Database size={14} /><b>发现</b>数据源</span><i><ArrowRight size={12} /></i>
                  <span><Search size={14} /><b>检查</b>字段</span><i><ArrowRight size={12} /></i>
                  <span><Activity size={14} /><b>执行</b>计算</span><i><ArrowRight size={12} /></i>
                  <span><ShieldCheck size={14} /><b>核对</b>结果</span>
                </div>
                {!datasetId ? <button className="connect-data-btn" type="button" onClick={() => setPage("upload")}><FileUp size={16} />连接第一份数据<ArrowRight size={15} /></button> : null}
                <div className="starter-grid">
                  {starters.map((item) => <button key={item} type="button" onClick={() => send(item)}><Search size={15} /><span>{item}</span><ArrowRight size={15} /></button>)}
                </div>
              </div>
            )}
            {messages.map((msg, index) => (
              <article key={index} className={`chat-bubble ${msg.role}${msg.error ? " error" : ""}`}>
                <div className="message-avatar">{msg.role === "user" ? "你" : <span className="mini-logo" />}</div>
                <div className="message-content">
                  <span className="chat-role">{msg.role === "user" ? "你" : "SoloDeck"}</span>
                  <p>{msg.content}</p>
                  {msg.role === "assistant" ? <ResultArtifact message={msg} /> : null}
                </div>
              </article>
            ))}
            {loading && <div className="chat-loading"><Loader2 className="spin" size={17} /><span>{liveStages[runPhase].label}：{liveStages[runPhase].detail}</span></div>}
            <div ref={bottomRef} />
          </div>

          <div className="composer">
            <textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder="询问数据中的变化、原因、风险或下一步行动…" onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
            <div className="composer-actions">
              <div>
                <button className="composer-icon" type="button" onClick={() => setPage("upload")} title="添加数据"><FileUp size={18} /></button>
                <button className={`composer-icon ${listening ? "active" : ""}`} type="button" onClick={toggleVoice} title={listening ? "停止录音" : "语音提问"}>{listening ? <MicOff size={18} /> : <Mic size={18} />}</button>
              </div>
              <button className="send-btn" type="button" disabled={loading || !input.trim()} onClick={() => send()} title="发送"><Send size={18} /></button>
            </div>
          </div>
          {voiceTip ? <div className="voice-tip">{voiceTip}</div> : null}
        </div>
        <RunInspector
          run={latestRun}
          loading={loading}
          phase={runPhase}
          history={runHistory}
          collapsed={inspectorCollapsed}
          setCollapsed={setInspectorCollapsed}
          onRestore={(stateId) => send(`回到 ${stateId}，并告诉我当时的结论`)}
        />
      </div>
    </section>
  );
}

function Sidebar({ page, setPage, collapsed, setCollapsed, threads, threadId, onNewThread, onSelectThread, onArchiveThread, auth, onOpenAuth, onLogout }) {
  return (
    <>
      <button className="sidebar-toggle" onClick={() => setCollapsed(!collapsed)} aria-label="切换侧栏">
        {collapsed ? <Menu size={19} /> : <X size={19} />}
      </button>
      <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
        <div className="brand">
          <span className="logo" />
          <div>
            <strong>SoloDeck</strong>
            <small>Northstar Labs</small>
          </div>
        </div>
        <p className="side-copy">从问题到证据，再到可执行结论。</p>
        <nav>
          {pages.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={page === item.id ? "active" : ""}
                onClick={() => setPage(item.id)}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="thread-section">
          <div className="thread-heading"><span>最近对话</span><button type="button" onClick={onNewThread} title="新对话"><Plus size={16} /></button></div>
          <div className="thread-list">
            {threads.length ? threads.map((thread) => (
              <div className={`thread-row ${threadId === thread.thread_id ? "active" : ""}`} key={thread.thread_id}>
                <button className="thread-open" type="button" onClick={() => onSelectThread(thread)} title={thread.title}><MessageSquare size={14} /><span>{thread.title}</span></button>
                <button className="thread-delete" type="button" title="移除对话" onClick={() => onArchiveThread(thread.thread_id)}><Trash2 size={13} /></button>
              </div>
            )) : <p className="thread-empty">分析后的对话会保存在这里</p>}
          </div>
        </div>
        <div className="account-area">
          {auth?.authenticated ? (
            <button type="button" className="account-button" onClick={onLogout} title="退出登录">
              <span className="account-avatar"><UserRound size={16} /></span>
              <span><strong>{auth.user?.display_name}</strong><small>个人工作区</small></span>
              <LogOut size={15} />
            </button>
          ) : (
            <button type="button" className="account-button" onClick={onOpenAuth}>
              <span className="account-avatar"><LogIn size={16} /></span>
              <span><strong>登录或注册</strong><small>跨设备保存记录</small></span>
            </button>
          )}
        </div>
      </aside>
    </>
  );
}

function UploadPage({ datasetId, mapping, setDatasetId, setMapping, setPage, workspaceId, datasets, refreshWorkspace, selectDataset }) {
  const [demoLoading, setDemoLoading] = useState(false);
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    if (!datasetId) {
      setDetail(null);
      return;
    }
    apiGet(`/api/data-agent/datasets/${datasetId}?workspace_id=${encodeURIComponent(workspaceId)}`)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [datasetId, workspaceId, datasets.length]);

  async function loadDemo() {
    setDemoLoading(true);
    try {
      const data = await apiPost("/api/data-agent/demo", { workspace_id: workspaceId });
      setDatasetId(data.dataset_id);
      setMapping(data.mapping);
      await refreshWorkspace();
    } finally {
      setDemoLoading(false);
    }
  }

  return (
    <section className="page">
      <header className="page-head">
        <div>
          <span className="eyebrow">数据资产</span>
          <h1>数据目录</h1>
          <p>统一管理表格、截图和文字资料。选择数据集后，工作台会始终基于它回答。</p>
        </div>
        <button className="primary-btn subtle" type="button" onClick={loadDemo} disabled={demoLoading}>
          {demoLoading ? <Loader2 className="spin" size={16} /> : <Sparkles size={16} />}载入演示数据
        </button>
      </header>
      <DataIntakePanel
        datasetId={datasetId}
        setDatasetId={setDatasetId}
        setMapping={setMapping}
        setPage={setPage}
        workspaceId={workspaceId}
        onUploaded={refreshWorkspace}
      />
      <div className="catalog-layout">
        <div className="dataset-list panel">
          <div className="section-title"><div><span className="eyebrow">已连接</span><h3>{datasets.length} 个数据集</h3></div></div>
          {datasets.length ? datasets.map((item) => (
            <button type="button" className={`dataset-row ${datasetId === item.dataset_id ? "active" : ""}`} key={item.dataset_id} onClick={() => selectDataset(item)}>
              <Database size={18} /><div><strong>{item.name}</strong><span>{item.row_count} 行 · {item.column_count} 列 · {item.source_type}</span></div><ArrowRight size={16} />
            </button>
          )) : <div className="catalog-empty"><Database size={24} /><strong>还没有数据</strong><span>上传自己的资料，或显式载入演示数据。</span></div>}
        </div>
        <div className="dataset-detail panel">
          {detail ? <>
            <div className="section-title"><div><span className="eyebrow">当前数据</span><h3>{detail.name}</h3></div><button className="primary-btn" onClick={() => setPage("chat")}>开始分析</button></div>
            <div className="profile-strip">
              <Kpi label="数据行" value={formatNumber(detail.row_count)} />
              <Kpi label="字段数" value={formatNumber(detail.column_count)} />
              <Kpi label="完整度" value={percent(detail.profile?.quality_score)} />
              <Kpi label="重复行" value={formatNumber(detail.profile?.duplicate_rows)} />
            </div>
            <div className="field-catalog">
              {(detail.profile?.columns || []).map((column) => <span key={column}><Table2 size={13} />{cn(column)}</span>)}
            </div>
            <p className="privacy-note"><ShieldCheck size={14} />这里只展示字段与质量摘要，不向前端返回原始记录。</p>
          </> : <div className="catalog-empty"><Table2 size={24} /><strong>选择一个数据集</strong><span>这里会显示字段概况和脱敏预览。</span></div>}
        </div>
      </div>
    </section>
  );
}

function RunsPage({ runs, datasets, selectDataset, setPage }) {
  const datasetNames = Object.fromEntries(datasets.map((item) => [item.dataset_id, item.name]));
  return (
    <section className="page">
      <header className="page-head"><div><span className="eyebrow">可追溯执行</span><h1>运行记录</h1><p>每次问题、工具选择、结果视图和耗时都保存在当前工作区。</p></div></header>
      <div className="runs-list">
        {runs.length ? runs.map((run) => (
          <article className="run-card" key={run.run_id}>
            <div className="run-card-head"><span className={`run-status ${run.status}`}>{run.status === "completed" ? "已完成" : "需复核"}</span><time>{new Date(run.created_at).toLocaleString("zh-CN")}</time></div>
            <h3>{run.user_task}</h3>
            <p>{run.reply}</p>
            <div className="run-meta"><span><Database size={13} />{datasetNames[run.dataset_id] || "历史数据集"}</span><span><Activity size={13} />{Math.round(run.latency_ms)} 毫秒</span></div>
            <div className="tool-chips">{run.selected_tools.map((tool) => <code key={tool}>{operationLabels[tool] || tool}</code>)}</div>
            <button type="button" className="text-action" onClick={() => { const item = datasets.find((dataset) => dataset.dataset_id === run.dataset_id); if (item) selectDataset(item); setPage("chat"); }}>基于该数据继续提问 <ArrowRight size={14} /></button>
          </article>
        )) : <div className="catalog-empty panel"><History size={26} /><strong>还没有运行记录</strong><span>在数据工作台提出第一个问题后，完整记录会出现在这里。</span></div>}
      </div>
    </section>
  );
}

function MappingSummary({ mapping }) {
  if (!mapping) return null;
  return (
    <div className="panel">
      <span className="eyebrow">字段识别</span>
      <h3>识别 {mapping.rows} 行，字段置信度 {Math.round((mapping.mapping_confidence || 0) * 100)}%</h3>
      <p>已映射：{mapping.mapped_fields?.slice(0, 8).join("、") || "待识别"}</p>
      {mapping.missing_fields?.length ? <p>缺失字段：{mapping.missing_fields.join("、")}</p> : null}
    </div>
  );
}

function DiagnosePage({ datasetId, questionId, setDiag }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let mounted = true;
    setLoading(true);
    apiPost("/api/diagnose", { dataset_id: datasetId, question_id: questionId })
      .then((payload) => {
        if (!mounted) return;
        setData(payload);
        setDiag(payload);
      })
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, [datasetId, questionId, setDiag]);

  if (loading && !data) return <LoadingPage title="正在诊断数据" />;
  const k = data?.kpis || {};
  return (
    <section className="page">
      <header className="page-head">
        <div>
          <span className="eyebrow">诊断</span>
          <h1>经营诊断</h1>
          <p>只保留 5 个指标和 3 条观察，避免把用户拖进仪表盘。</p>
        </div>
      </header>
      <div className="kpi-grid">
        <Kpi label="总播放" value={formatNumber(k.total_views)} />
        <Kpi label="收藏率" value={percent(k.favorite_rate)} />
        <Kpi label="咨询率" value={percent(k.consultation_rate)} />
        <Kpi label="收入" value={`¥${formatNumber(k.revenue)}`} />
        <Kpi label="千次播放收入" value={`¥${(k.rpm || 0).toFixed(1)}`} />
      </div>
      <div className="three-grid">
        {data?.observations?.map((item) => (
          <article className="insight" key={item.title}>
            <span>观察</span>
            <h3>{item.title}</h3>
            <p>{item.detail}</p>
          </article>
        ))}
      </div>
      <MappingSummary mapping={data?.mapping} />
      <Trace trace={data?.trace} />
    </section>
  );
}

function Kpi({ label, value }) {
  return (
    <div className="kpi">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DecisionPage({ datasetId, questionId, setQuestionId, setDecision }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let mounted = true;
    setLoading(true);
    apiPost("/api/decision", { dataset_id: datasetId, question_id: questionId })
      .then((payload) => {
        if (!mounted) return;
        setData(payload);
        setDecision(payload);
      })
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, [datasetId, questionId, setDecision]);

  const d = data?.decision;
  const effect = d?.effect;
  const readiness = d?.readiness;
  const ci = ciStatus(effect);
  return (
    <section className="page">
      <header className="page-head">
        <div>
          <span className="eyebrow">决策检查</span>
          <h1>这件事值得做吗？</h1>
          <p>把“看起来有效”拆成处理组、对照组、结果指标和置信区间。</p>
        </div>
        <select value={questionId} onChange={(e) => setQuestionId(e.target.value)}>
          {questions.map((q) => <option key={q.id} value={q.id}>{q.label}</option>)}
        </select>
      </header>
      {loading && !d ? <LoadingPage title="正在估计增量" /> : (
        <>
          <div className="decision-card">
            <span className="eyebrow">策略对比</span>
            <h2>{d?.query?.label}</h2>
            <p>策略：{cn(d?.query?.treatment)} = {cn(d?.query?.treatment_value) || "最佳组"}；对照：其他方案；指标：{cn(d?.query?.outcome)}</p>
          </div>
          <div className="kpi-grid four">
            <Kpi label="直接差异" value={(effect?.ate || 0).toFixed(2)} />
            <Kpi label="调整后增量" value={(effect?.adjusted_effect || 0).toFixed(2)} />
            <Kpi label="相对提升" value={percent(effect?.relative_lift)} />
            <Kpi label="样本量" value={formatNumber(effect?.sample_size)} />
          </div>
          <div className="panel">
            <div className={`ci-card ${ci.level}`}>
              <div>
                <span>重采样 95% 区间</span>
                <strong>[{(effect?.ci_95?.[0] || 0).toFixed(2)}, {(effect?.ci_95?.[1] || 0).toFixed(2)}]</strong>
              </div>
              <div>
                <span>{ci.title}</span>
                <p>{ci.detail}</p>
              </div>
            </div>
            <p>{effect?.explanation}</p>
            <p>可靠性：{readiness?.risk_level}风险；{readiness?.can_make_causal_claim ? "可以谨慎作为因果增量判断。" : "更适合作为下周验证计划。"}</p>
            {(effect?.warnings || readiness?.warnings || []).slice(0, 3).map((w) => <p className="warn" key={w}>{w}</p>)}
          </div>
          <Trace trace={data?.trace} />
        </>
      )}
    </section>
  );
}

function ActionPage({ datasetId, questionId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let mounted = true;
    setLoading(true);
    const label = questions.find((q) => q.id === questionId)?.label || "评估内容策略增量";
    apiPost("/api/v3-agent", { dataset_id: datasetId, task: `${label}，生成下周三张行动卡。` })
      .then((payload) => {
        if (!mounted) return;
        setData({
          dataset_id: datasetId,
          action_cards: payload?.user_artifact?.actions || [],
          trace: payload?.developer_trace?.executed_skills || []
        });
      })
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, [datasetId, questionId]);
  if (loading && !data) return <LoadingPage title="正在生成行动卡" />;
  return (
    <section className="page">
      <header className="page-head">
        <div>
          <span className="eyebrow">行动计划</span>
          <h1>下周只做这 3 件事</h1>
          <p>每张卡都包含依据、风险、下一步和要看的指标。</p>
        </div>
      </header>
      <div className="action-grid">
        {data?.action_cards?.map((card, index) => {
          const type = card.type || card.title || "下周验证";
          const title = card.recommendation || card.title;
          const evidence = card.evidence || card.explanation;
          const risk = card.risk || `可信度：${card.confidence || "需要验证"}`;
          const metric = card.metric_to_watch || "按卡片说明记录";
          return (
          <article className="action" key={`${title}-${index}`}>
            {React.createElement(actionIcon(type))}
            <span>{cn(type)}</span>
            <h3>{title}</h3>
            <p><strong>依据：</strong>{evidence}</p>
            <p><strong>风险：</strong>{risk}</p>
            <p><strong>下一步：</strong>{card.next_step}</p>
            <small>观察指标：{cn(metric)}</small>
          </article>
          );
        })}
      </div>
      <Trace trace={data?.trace} />
    </section>
  );
}

function AgentPage({ datasetId, questionId }) {
  const [data, setData] = useState(null);
  const [v3, setV3] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showTrace, setShowTrace] = useState(false);
  useEffect(() => {
    let mounted = true;
    setLoading(true);
    Promise.all([
      apiPost("/api/full-agent", { dataset_id: datasetId, question_id: questionId }),
      apiPost("/api/v3-agent", { dataset_id: datasetId, task: "评估内容策略增量，生成可验证的下一步行动。" })
    ])
      .then(([agentPayload, v3Payload]) => {
        if (!mounted) return;
        setData(agentPayload);
        setV3(v3Payload);
      })
      .finally(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, [datasetId, questionId]);
  if (loading && !data) return <LoadingPage title="正在构建图谱与候选因果图" />;
  const effect = data?.decision?.effect;
  const ci = ciStatus(effect);
  return (
    <section className="page">
      <header className="page-head">
        <div>
          <span className="eyebrow">图谱与因果</span>
          <h1>图谱与因果检查</h1>
          <p>先解释数据关系，再检查建议是否稳，避免把相关性误当成结论。</p>
        </div>
      </header>

      <div className="agent-grid">
        <div className="panel">
          <span className="eyebrow">知识图谱</span>
          <h3>先看清关系，再决定要不要放大</h3>
          <p>{data?.kg?.summary?.explanation}</p>
          <KnowledgeDigest kg={data?.kg} dag={data?.dag} />
        </div>
        <div className="panel">
          <span className="eyebrow">候选关系图</span>
          <h3>{data?.dag?.method}</h3>
          <p>{data?.dag?.explanation}</p>
          <DagList edges={data?.dag?.edges || []} />
        </div>
      </div>

      <div className="agent-grid">
        <div className="panel">
          <span className="eyebrow">置信区间</span>
          <h3>{ci.title}</h3>
          <CiPlot effect={effect} />
          <p>{ci.detail}</p>
        </div>
        <div className="panel">
          <span className="eyebrow">工作流判断</span>
          <h3>{data?.decision?.evaluation?.confidence || "中"}可信度</h3>
          <p>{data?.decision?.validation_loop?.message}</p>
          <p>{data?.decision?.evaluation?.constraint_check}</p>
          <button className="primary-btn subtle" onClick={() => setShowTrace(!showTrace)}>
            {showTrace ? "隐藏开发追踪" : "查看开发追踪"}
          </button>
        </div>
      </div>
      <div className="agent-grid">
        <div className="panel">
          <span className="eyebrow">用户结果视图</span>
          <h3>{v3?.user_artifact?.title || "可验证经营建议"}</h3>
          <p>{v3?.user_artifact?.result}</p>
          <p>可信度：{v3?.user_artifact?.confidence || "需要验证"}；验证：{v3?.user_artifact?.validation_passed ? "通过" : "已降级为验证建议"}。</p>
          <p>{v3?.user_artifact?.limitations}</p>
        </div>
        <div className="panel">
          <span className="eyebrow">系统判断</span>
          <h3>{v3?.validation_report?.valid ? "当前建议已通过基础校验" : "当前建议需要更多数据"}</h3>
          <p>系统会检查字段、数据质量、混杂因素、区间稳定性和隐私风险，再生成行动卡。</p>
          <p>想查看完整执行链，可以打开开发追踪。</p>
          <button className="primary-btn subtle" onClick={() => setShowTrace(!showTrace)}>
            {showTrace ? "隐藏开发追踪" : "查看开发追踪"}
          </button>
        </div>
      </div>
      {showTrace && <DeveloperTracePanel panel={v3?.developer_trace || {}} />}
    </section>
  );
}

function KnowledgeDigest({ kg, dag }) {
  const topTopics = (kg?.summary?.top_topics || []).slice(0, 4);
  const nodeTypes = kg?.summary?.node_types || {};
  const topContent = (kg?.nodes || [])
    .filter((node) => node.type === "内容")
    .sort((a, b) => Number(b.revenue || 0) - Number(a.revenue || 0))
    .slice(0, 3);
  const paths = (dag?.edges || []).slice(0, 4);
  return (
    <div className="knowledge-digest">
      <div className="knowledge-stats">
        <div className="digest-card">
          <span>实体</span>
          <strong>{kg?.summary?.node_count || 0}</strong>
          <small>内容 {nodeTypes["内容"] || 0}｜主题 {nodeTypes["主题"] || 0}｜特征 {nodeTypes["特征"] || 0}</small>
        </div>
        <div className="digest-card">
          <span>关系</span>
          <strong>{kg?.summary?.edge_count || 0}</strong>
          <small>用于解释主题、内容、特征与结果之间的连接。</small>
        </div>
      </div>
      <div className="knowledge-columns">
        <div className="digest-list">
          <h4>最强主题</h4>
          {topTopics.map((topic) => (
            <div key={topic.label} className="digest-item">
              <strong>{topic.label}</strong>
              <small>累计收入 ¥{formatNumber(topic.revenue)}</small>
            </div>
          ))}
        </div>
        <div className="digest-list">
          <h4>高价值内容</h4>
          {topContent.map((item) => (
            <div key={item.id} className="digest-item">
              <strong>{item.label.slice(0, 22)}</strong>
              <small>收入 ¥{formatNumber(item.revenue)}｜成交 {formatNumber(item.conversions)}</small>
            </div>
          ))}
        </div>
        <div className="digest-list">
          <h4>关键路径</h4>
          {paths.map((edge, index) => (
            <div key={`${edge.source}-${edge.target}-${index}`} className="digest-item arrow">
              <strong>{cn(edge.source)} → {cn(edge.target)}</strong>
              <small>影响强度 {Number(edge.weight || 0).toFixed(2)}</small>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function DagList({ edges }) {
  return (
    <div className="dag-list">
      {edges.slice(0, 7).map((edge) => (
        <div key={`${edge.source}-${edge.target}`}>
          <strong>{cn(edge.source)}</strong>
          <span>→</span>
          <strong>{cn(edge.target)}</strong>
          <small>强度 {Number(edge.weight || 0).toFixed(2)}｜{edge.reason}</small>
        </div>
      ))}
    </div>
  );
}

function CiPlot({ effect }) {
  const low = Number(effect?.ci_95?.[0] || 0);
  const high = Number(effect?.ci_95?.[1] || 0);
  const ate = Number(effect?.adjusted_effect || effect?.ate || 0);
  const min = Math.min(low, high, ate, 0);
  const max = Math.max(low, high, ate, 0);
  const scale = (value) => 30 + ((value - min) / Math.max(1e-6, max - min)) * 340;
  return (
    <svg className="ci-svg" viewBox="0 0 400 96" role="img" aria-label="置信区间图">
      <line className="axis" x1="30" y1="50" x2="370" y2="50" />
      <line className="zero" x1={scale(0)} y1="22" x2={scale(0)} y2="76" />
      <line className="interval" x1={scale(low)} y1="50" x2={scale(high)} y2="50" />
      <circle cx={scale(ate)} cy="50" r="7" />
      <text x="30" y="88">{low.toFixed(2)}</text>
      <text x={scale(0) - 7} y="18">0</text>
      <text x="318" y="88">{high.toFixed(2)}</text>
    </svg>
  );
}

function DeveloperTrace({ trace, audit }) {
  return (
    <div className="panel dev-trace">
      <span className="eyebrow">开发追踪</span>
      <h3>只展示步骤摘要，不展示原始上传数据</h3>
      <div className="trace-line">
        {trace.map((step) => <code key={step}>{step}</code>)}
      </div>
      <div className="audit-list">
        {audit.slice(-8).map((item, index) => (
          <p key={`${item.time}-${index}`}>{item.step}｜{new Date(item.time).toLocaleString("zh-CN")}</p>
        ))}
      </div>
    </div>
  );
}

function DeveloperTracePanel({ panel }) {
  const trace = panel.trace || [];
  const rewards = panel.agent_rewards || {};
  const route = panel.route_decision || {};
  return (
    <div className="panel dev-trace">
      <span className="eyebrow">开发追踪</span>
      <h3>任务规格 / 路由 / 工作流 / 校验 / 奖励 / 记忆</h3>
      <div className="trace-line">
        {(panel.executed_skills || []).map((skill) => <code key={skill}>{skill}</code>)}
      </div>
      <div className="agent-grid">
        <div>
          <p><strong>任务类型：</strong>{panel.task_spec?.task_type}</p>
          <p><strong>路由：</strong>{route.route_id || "未生成"}</p>
          <p><strong>工具：</strong>{(route.selected_tools || []).join("、") || "未生成"}</p>
          <p><strong>选中工作流：</strong>{panel.selected_workflow?.method}</p>
          <p><strong>验证：</strong>{panel.validation_report?.valid ? "通过" : "未通过"}</p>
        </div>
        <div>
          <p><strong>过程奖励：</strong>{Number(panel.process_rewards?.total || panel.step_rewards?.total || 0).toFixed(2)}</p>
          <p><strong>因果表述：</strong>{panel.claim_review?.claim_level || "未检查"}</p>
          {Object.entries(rewards).map(([role, item]) => (
            <p key={role}><strong>{role}：</strong>{Number(item.normalized || 0).toFixed(2)}</p>
          ))}
        </div>
      </div>
      <div className="audit-list">
        {trace.slice(-10).map((item, index) => (
          <p key={`${item.step}-${index}`}>{index + 1}. {item.step}｜{item.role}</p>
        ))}
      </div>
    </div>
  );
}

function LoadingPage({ title }) {
  return <div className="loading"><Loader2 className="spin" /> {title}</div>;
}

function EmptyDatasetPage({ setPage }) {
  return <section className="page empty-dataset-page"><div className="catalog-empty"><Database size={30} /><h2>先连接一份数据</h2><p>上传 CSV、Excel、截图或文字，数据 Agent 才会开始计算。</p><button className="primary-btn" onClick={() => setPage("upload")}>打开数据目录</button></div></section>;
}

function App() {
  const [page, setPage] = useState("chat");
  const [collapsed, setCollapsed] = useState(() => typeof window !== "undefined" && window.innerWidth < 760);
  const [anonymousWorkspaceId] = useState(() => {
    const saved = window.localStorage.getItem("solodeck_workspace_id");
    if (saved) return saved;
    const randomPart = (window.crypto?.randomUUID?.() || "").replaceAll("-", "");
    const value = `ws_${randomPart || Date.now().toString(36)}`;
    window.localStorage.setItem("solodeck_workspace_id", value);
    return value;
  });
  const [auth, setAuth] = useState(null);
  const [authReady, setAuthReady] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [datasetId, setDatasetId] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [runs, setRuns] = useState([]);
  const [threads, setThreads] = useState([]);
  const [threadId, setThreadId] = useState(null);
  const [mapping, setMapping] = useState(null);
  const [questionId, setQuestionId] = useState("pain_point_title");
  const [, setDiag] = useState(null);
  const [, setDecision] = useState(null);
  const workspaceId = auth?.workspace_id || anonymousWorkspaceId;

  async function refreshWorkspace() {
    const [data, threadData] = await Promise.all([
      apiGet(`/api/data-agent/workspace?workspace_id=${encodeURIComponent(workspaceId)}`),
      apiGet(`/api/data-agent/threads?workspace_id=${encodeURIComponent(workspaceId)}`)
    ]);
    setDatasets(data.datasets || []);
    setRuns(data.runs || []);
    setThreads(threadData.threads || []);
    if (!datasetId && data.datasets?.length) {
      setDatasetId(data.datasets[0].dataset_id);
      setMapping(data.datasets[0].mapping || null);
    }
    return data;
  }

  function selectDataset(dataset) {
    setDatasetId(dataset.dataset_id);
    setMapping(dataset.mapping || null);
  }

  useEffect(() => {
    apiGet("/api/auth/me")
      .then(setAuth)
      .catch(() => setAuth({ authenticated: false }))
      .finally(() => setAuthReady(true));
  }, []);

  useEffect(() => {
    if (!authReady) return;
    setDatasetId(null);
    setMapping(null);
    setThreadId(null);
    setDatasets([]);
    setRuns([]);
    setThreads([]);
    refreshWorkspace().catch(() => {});
  }, [workspaceId, authReady]);

  function newThread() {
    setThreadId(null);
    setPage("chat");
  }

  function selectThread(thread) {
    setThreadId(thread.thread_id);
    if (thread.dataset_id) {
      setDatasetId(thread.dataset_id);
      const selected = datasets.find((item) => item.dataset_id === thread.dataset_id);
      if (selected) setMapping(selected.mapping || null);
    }
    setPage("chat");
  }

  async function archiveThread(id) {
    await apiDelete(`/api/data-agent/threads/${id}?workspace_id=${encodeURIComponent(workspaceId)}`);
    if (threadId === id) newThread();
    await refreshWorkspace();
  }

  async function logout() {
    await apiPost("/api/auth/logout", {});
    cache.clear();
    setAuth({ authenticated: false });
  }

  const currentDataset = datasets.find((item) => item.dataset_id === datasetId) || null;
  const needsData = !datasetId && !["upload", "runs", "chat"].includes(page);

  return (
    <div className="shell">
      <Sidebar page={page} setPage={setPage} collapsed={collapsed} setCollapsed={setCollapsed} threads={threads} threadId={threadId} onNewThread={newThread} onSelectThread={selectThread} onArchiveThread={(id) => archiveThread(id).catch(() => {})} auth={auth} onOpenAuth={() => setAuthOpen(true)} onLogout={() => logout().catch(() => {})} />
      <main className={collapsed ? "expanded" : ""}>
        {page === "upload" && <UploadPage datasetId={datasetId} mapping={mapping} setDatasetId={setDatasetId} setMapping={setMapping} setPage={setPage} workspaceId={workspaceId} datasets={datasets} refreshWorkspace={refreshWorkspace} selectDataset={selectDataset} />}
        {page === "runs" && <RunsPage runs={runs} datasets={datasets} selectDataset={selectDataset} setPage={setPage} />}
        {page === "chat" && <ChatPage key={`${workspaceId}:${threadId || "new"}:${datasetId || "empty"}`} datasetId={datasetId} dataset={currentDataset} mapping={mapping} setPage={setPage} workspaceId={workspaceId} threadId={threadId} setThreadId={setThreadId} onRunComplete={() => refreshWorkspace().catch(() => {})} />}
        {needsData && <EmptyDatasetPage setPage={setPage} />}
        {!needsData && page === "diagnose" && <DiagnosePage datasetId={datasetId} questionId={questionId} setDiag={setDiag} />}
        {!needsData && page === "decision" && <DecisionPage datasetId={datasetId} questionId={questionId} setQuestionId={setQuestionId} setDecision={setDecision} />}
        {!needsData && page === "agent" && <AgentPage datasetId={datasetId} questionId={questionId} />}
        {!needsData && page === "actions" && <ActionPage datasetId={datasetId} questionId={questionId} />}
      </main>
      <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} onAuthenticated={setAuth} />
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
