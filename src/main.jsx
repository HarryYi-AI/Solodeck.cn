import React, { useEffect, useMemo, useRef, useState, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { ArrowRight, CheckCircle2, FileUp, Loader2, MessageSquare, PauseCircle, Rocket, ShieldCheck, UploadCloud } from "lucide-react";
import "./styles.css";

const pages = [
  { id: "upload", label: "上传数据", icon: FileUp },
  { id: "chat", label: "对话分析", icon: MessageSquare },
  { id: "diagnose", label: "经营诊断", icon: ShieldCheck },
  { id: "decision", label: "决策检查", icon: CheckCircle2 },
  { id: "agent", label: "图谱与因果", icon: ArrowRight },
  { id: "actions", label: "行动计划", icon: ArrowRight }
];

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

async function apiPost(path, body) {
  const key = `${path}:${JSON.stringify(body || {})}`;
  const noCache = path.includes("/api/v4/chat");
  if (!noCache && cache.has(key)) return cache.get(key);
  const promise = fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {})
  }).then(async (res) => {
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "请求失败");
    return data;
  });
  cache.set(key, promise);
  return promise;
}

function Trace({ trace }) {
  useEffect(() => {
    if (trace?.length) {
      window.__SOLODECK_TRACE__ = trace;
    }
  }, [trace]);
  return null;
}

function prefetchAnalysis(datasetId, questionId) {
  if (!datasetId) return;
  apiPost("/api/diagnose", { dataset_id: datasetId, question_id: questionId }).catch(() => {});
  apiPost("/api/decision", { dataset_id: datasetId, question_id: questionId }).catch(() => {});
  apiPost("/api/full-agent", { dataset_id: datasetId, question_id: questionId }).catch(() => {});
  apiPost("/api/v3-agent", { dataset_id: datasetId, task: "评估内容策略增量，生成可验证的下一步行动。" }).catch(() => {});
  apiPost("/api/action-plan", { dataset_id: datasetId, question_id: questionId }).catch(() => {});
}

function ChatPage({ datasetId }) {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [meta, setMeta] = useState(null);
  const [voiceStack, setVoiceStack] = useState("pipecat");
  const [stacks, setStacks] = useState([]);
  const bottomRef = useRef(null);

  useEffect(() => {
    fetch("/api/v4/voice/stacks").then((r) => r.json()).then((d) => {
      setStacks(d.stacks || []);
      if (d.default) setVoiceStack(d.default);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send(preset) {
    const text = (preset || input).trim();
    if (!text || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);
    try {
      const data = await apiPost("/api/v4/chat", {
        session_id: sessionId,
        dataset_id: datasetId,
        message: text
      });
      setSessionId(data.session_id);
      setMeta({
        cost: data.session_cost_total,
        risk: data.risk_profile,
        tools: data.tool_calls,
        plan: data.plan_steps,
        traceId: data.trace_id
      });
      setMessages((prev) => [...prev, {
        role: "assistant",
        content: data.reply,
        artifact: data.user_artifact,
        validation: data.validation_report,
        postWriter: data.post_writer_validation
      }]);
    } catch (error) {
      setMessages((prev) => [...prev, { role: "assistant", content: error.message, error: true }]);
    } finally {
      setLoading(false);
    }
  }

  const starters = [
    "小红书痛点标题是不是比教程标题更能带来咨询？",
    "那个平台转化更好？",
    "继续算一下上周的收入趋势"
  ];

  const activeStack = stacks.find((s) => s.id === voiceStack);

  return (
    <section className="page chat-page">
      <header className="page-head">
        <div>
          <span className="eyebrow">SoloDeck v4</span>
          <h1>多轮对话分析</h1>
          <p>支持追问、工具编排与上下文压缩。语音接入可选三档栈（LiveKit / Pipecat / 边缘离线）。</p>
        </div>
        {meta && (
          <div className="chat-meta">
            <span>会话 {sessionId?.slice(0, 10)}…</span>
            <span>累计成本 {Number(meta.cost || 0).toFixed(2)}</span>
            {meta.risk?.high_risk && <span className="risk-badge">深度校验</span>}
            {meta.risk?.reuse_cache && <span className="cache-badge">缓存复用</span>}
          </div>
        )}
      </header>

      {stacks.length ? (
        <div className="panel voice-stack-panel">
          <span className="eyebrow">语音栈（接入参考）</span>
          <div className="voice-stack-tabs">
            {stacks.map((s) => (
              <button
                key={s.id}
                type="button"
                className={voiceStack === s.id ? "active" : ""}
                onClick={() => setVoiceStack(s.id)}
              >
                {s.name}
              </button>
            ))}
          </div>
          {activeStack ? (
            <p className="voice-stack-detail">
              {activeStack.transport} · {activeStack.stt} · {activeStack.llm} · {activeStack.tts}
              <br />
              延迟目标 <strong>{activeStack.latency?.e2e_label}</strong> · {activeStack.license}
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="chat-starters">
        {starters.map((item) => (
          <button key={item} className="chip-btn" type="button" onClick={() => send(item)}>{item}</button>
        ))}
      </div>

      <div className="chat-panel">
        {messages.length === 0 && (
          <div className="chat-empty">
            <MessageSquare size={28} />
            <p>用口语提问即可。系统会自动编译任务、调用工具、验证结论并生成行动建议。</p>
          </div>
        )}
        {messages.map((msg, index) => (
          <article key={index} className={`chat-bubble ${msg.role}${msg.error ? " error" : ""}`}>
            <span className="chat-role">{msg.role === "user" ? "你" : "SoloDeck"}</span>
            <p>{msg.content}</p>
            {msg.artifact?.action_cards?.length ? (
              <div className="chat-cards">
                {msg.artifact.action_cards.slice(0, 2).map((card, i) => (
                  <div key={i} className="mini-card">
                    <strong>{cn(card.title || card.action)}</strong>
                    <small>{card.next_step || card.explanation}</small>
                  </div>
                ))}
              </div>
            ) : null}
          </article>
        ))}
        {loading && <div className="chat-loading"><Loader2 className="spin" size={18} /> 正在编排工具链…</div>}
        <div ref={bottomRef} />
      </div>

      {meta?.plan?.length ? (
        <div className="panel chat-plan">
          <span className="eyebrow">任务编排</span>
          <div className="plan-steps">
            {meta.plan.map((step) => (
              <span key={step.id}>{step.goal}</span>
            ))}
          </div>
        </div>
      ) : null}

      <div className="chat-input-row">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="继续追问，例如：那个平台呢？换成成交数再看一遍。"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button className="primary-btn" type="button" disabled={loading} onClick={() => send()}>发送</button>
      </div>
    </section>
  );
}

function Sidebar({ page, setPage, collapsed, setCollapsed }) {
  return (
    <>
      <button className="sidebar-toggle" onClick={() => setCollapsed(!collapsed)} aria-label="切换侧栏">
        {collapsed ? "☰" : "×"}
      </button>
      <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
        <div className="brand">
          <span className="logo" />
          <div>
            <strong>SoloDeck</strong>
            <small>v4 · Northstar Labs</small>
          </div>
        </div>
        <p className="side-copy">把数据变成下一步可执行计划。</p>
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
      </aside>
    </>
  );
}

function UploadPage({ datasetId, setDatasetId, setMapping, setPage }) {
  const inputRef = useRef(null);
  const [files, setFiles] = useState([]);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");

  async function upload(selected) {
    if (!selected.length && !text.trim()) return;
    setLoading(true);
    setNotice("正在映射字段，不会在前台暴露原始数据。");
    const form = new FormData();
    selected.forEach((file) => form.append("files", file));
    form.append("text", text);
    try {
      const res = await fetch("/api/upload", { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "上传失败");
      setDatasetId(data.dataset_id);
      setMapping(data.mapping);
      cache.clear();
      setNotice("已完成字段映射，可以进入对话分析或经营诊断。");
      setTimeout(() => setPage("chat"), 450);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page">
      <header className="page-head">
        <div>
          <span className="eyebrow">上传</span>
          <h1>上传创作者经营数据</h1>
          <p>支持 CSV / Excel / ZIP。系统只展示映射摘要和经营结论，不展示原始明细。</p>
        </div>
      </header>

      <div className="upload-card" onClick={() => inputRef.current?.click()}>
        {loading ? <Loader2 className="spin" size={34} /> : <UploadCloud size={38} />}
        <strong>{loading ? "正在处理" : "点击上传 CSV / Excel / ZIP"}</strong>
        <span>内容表现、收入、用户反馈、对照实验都可以上传；ZIP 会自动拆包识别。</span>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".csv,.xlsx,.xls,.zip"
          onChange={(event) => {
            const selected = [...event.target.files];
            setFiles(selected);
            upload(selected);
          }}
        />
      </div>

      <div className="file-row">
        {files.length ? files.map((file) => <span key={file.name}>{file.name}</span>) : <span>未上传时使用内置演示数据。</span>}
      </div>

      <div className="panel text-panel">
        <h3>也可以直接粘贴文字</h3>
        <p>适合后台摘要、用户反馈、商单记录、复盘笔记。系统会抽取关键词并进入知识图谱。</p>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="例如：小红书咨询很多但成交慢，用户反馈价格不清楚；B站长视频收藏高，适合做课程入口。"
        />
        <button className="primary-btn" onClick={() => upload(files)}>读取文字并分析</button>
      </div>

      {notice && <div className="notice">{notice}</div>}
      <MappingSummary mapping={datasetId ? null : undefined} />
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
          <h3>{data?.kg?.summary?.node_count || 0} 个实体，{data?.kg?.summary?.edge_count || 0} 条关系</h3>
          <p>{data?.kg?.summary?.explanation}</p>
          <GraphSvg nodes={data?.kg?.nodes || []} edges={data?.kg?.edges || []} />
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

function GraphSvg({ nodes, edges }) {
  const picked = nodes.slice(0, 18);
  const center = { x: 210, y: 130 };
  const points = picked.map((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(1, picked.length);
    const radius = node.type === "内容" ? 104 : 78;
    return { ...node, x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius };
  });
  const map = new Map(points.map((node) => [node.id, node]));
  return (
    <svg className="graph-svg" viewBox="0 0 420 260" role="img" aria-label="知识图谱可视化">
      {edges.slice(0, 36).map((edge, index) => {
        const source = map.get(edge.source);
        const target = map.get(edge.target);
        if (!source || !target) return null;
        return <line key={index} x1={source.x} y1={source.y} x2={target.x} y2={target.y} />;
      })}
      {points.map((node) => (
        <g key={node.id}>
          <circle cx={node.x} cy={node.y} r={node.type === "内容" ? 12 : 9} />
          <text x={node.x + 12} y={node.y + 4}>{node.label.slice(0, 10)}</text>
        </g>
      ))}
    </svg>
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

function App() {
  const [page, setPage] = useState("upload");
  const [collapsed, setCollapsed] = useState(false);
  const [datasetId, setDatasetId] = useState(null);
  const [mapping, setMapping] = useState(null);
  const [questionId, setQuestionId] = useState("pain_point_title");
  const [, setDiag] = useState(null);
  const [, setDecision] = useState(null);

  useEffect(() => {
    fetch("/api/demo").then((r) => r.json()).then((data) => {
      setDatasetId(data.dataset_id);
      setMapping(data.mapping);
      prefetchAnalysis(data.dataset_id, questionId);
    });
  }, []);

  useEffect(() => {
    prefetchAnalysis(datasetId, questionId);
  }, [datasetId, questionId]);

  return (
    <div className="shell">
      <Sidebar page={page} setPage={setPage} collapsed={collapsed} setCollapsed={setCollapsed} />
      <main className={collapsed ? "expanded" : ""}>
        {page === "upload" && <UploadPage datasetId={datasetId} setDatasetId={setDatasetId} setMapping={setMapping} setPage={setPage} />}
        {page === "chat" && <ChatPage datasetId={datasetId} />}
        {page === "diagnose" && <DiagnosePage datasetId={datasetId} questionId={questionId} setDiag={setDiag} />}
        {page === "decision" && <DecisionPage datasetId={datasetId} questionId={questionId} setQuestionId={setQuestionId} setDecision={setDecision} />}
        {page === "agent" && <AgentPage datasetId={datasetId} questionId={questionId} />}
        {page === "actions" && <ActionPage datasetId={datasetId} questionId={questionId} />}
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
