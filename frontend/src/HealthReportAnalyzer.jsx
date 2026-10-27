import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, FileText, LoaderCircle, MessageCircle, Plus, ShieldCheck, Trash2, UploadCloud } from 'lucide-react';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
const MAX_BYTES = 10 * 1024 * 1024;

async function request(path, token, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), Authorization: `Bearer ${token}`, ...options.headers },
  });
  let data;
  try { data = await response.json(); } catch { data = { detail: 'Unexpected server response' }; }
  if (!response.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

export default function HealthReportAnalyzer({ user, token, notify }) {
  const [reports, setReports] = useState([]);
  const [selected, setSelected] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [mode, setMode] = useState('Local rules and retrieval');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);
  const chatEnd = useRef(null);
  const busyRef = useRef(false);

  const loadReports = useCallback(async () => {
    if (!token || user?.role !== 'patient') return;
    try {
      const list = await request('/reports', token);
      setReports(list);
      return list;
    } catch (e) { setError(e.message); }
  }, [token, user?.role]);

  useEffect(() => { loadReports(); request('/reports/provider', token).then(x => setMode(x.processing_mode)).catch(() => {}); }, [loadReports, token]);
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [messages]);

  const chooseReport = async (report) => {
    setSelected(report); setError(''); setAnalysis(null); setMessages([]);
    try {
      const [details, history] = await Promise.all([
        request(`/reports/${report.id}`, token), request(`/reports/${report.id}/chat`, token),
      ]);
      setAnalysis(details.analysis); setMode(details.processing_mode || mode); setMessages(history);
    } catch (e) { setError(e.message); }
  };

  const upload = async (file) => {
    if (!file || busy || busyRef.current) return;
    setError('');
    if (!file.name.toLowerCase().endsWith('.pdf') || file.type !== 'application/pdf') { setError('Choose a PDF file.'); return; }
    if (file.size > MAX_BYTES) { setError('The PDF must be 10 MB or smaller.'); return; }
    busyRef.current = true; setBusy(true);
    try {
      const body = new FormData(); body.append('file', file);
      const created = await request('/reports/upload', token, { method: 'POST', body });
      const next = await loadReports();
      const report = next?.find(x => x.id === created.id) || created;
      await chooseReport(report); notify('Report uploaded and analyzed locally');
    } catch (e) { setError(e.message); }
    finally { busyRef.current = false; setBusy(false); if (inputRef.current) inputRef.current.value = ''; }
  };

  const sendQuestion = async (event) => {
    event.preventDefault();
    const value = question.trim();
    if (!selected || !value || busy || busyRef.current) return;
    busyRef.current = true; setBusy(true); setQuestion(''); setError('');
    setMessages(items => [...items, { role: 'user', content: value }]);
    try {
      const answer = await request(`/reports/${selected.id}/chat`, token, { method: 'POST', body: JSON.stringify({ question: value }) });
      setMessages(items => [...items, { role: 'assistant', content: answer.answer, evidence: answer.evidence, processing_mode: answer.processing_mode }]);
      setMode(answer.processing_mode || mode);
    } catch (e) { setMessages(items => { const index = items.map(x => x.role).lastIndexOf('user'); return index < 0 ? items : items.filter((_, i) => i !== index); }); setError(e.message); setQuestion(value); }
    finally { busyRef.current = false; setBusy(false); }
  };

  const clearChat = async () => {
    if (!selected || busy || busyRef.current) return;
    busyRef.current = true; setBusy(true);
    try { await request(`/reports/${selected.id}/chat`, token, { method: 'DELETE' }); setMessages([]); notify('Conversation cleared'); }
    catch (e) { setError(e.message); }
    finally { busyRef.current = false; setBusy(false); }
  };

  const removeReport = async (report) => {
    if (busy || busyRef.current) return;
    busyRef.current = true; setBusy(true);
    try {
      await request(`/reports/${report.id}`, token, { method: 'DELETE' });
      if (selected?.id === report.id) { setSelected(null); setAnalysis(null); setMessages([]); }
      await loadReports(); notify('Report and its conversation deleted');
    } catch (e) { setError(e.message); }
    finally { busyRef.current = false; setBusy(false); }
  };

  if (!user) return <><main className="page wrap"><div className="contentCard"><h1>AI Health Report Analyzer</h1><p>Sign in as a patient to upload and privately review a health report.</p><Link className="button" to="/login">Sign in</Link></div></main></>;
  if (user.role !== 'patient') return <main className="page wrap"><div className="contentCard"><h1>Patient reports are private</h1><p>Only the patient who uploaded a report can access its analysis and conversation.</p></div></main>;

  return <main className="page wrap reportPage">
    <div className="crumb"><Link to="/dashboard">Dashboard</Link> <span aria-hidden="true">›</span> AI Health Report Analyzer</div>
    <div className="pageTitle"><div><div className="eyebrow">YOUR PRIVATE HEALTH LIBRARY</div><h1>AI Health Report Analyzer</h1><p>Understand the text in a lab report with local rules and evidence from your document.</p></div><span className="demoPill"><ShieldCheck size={14}/> {mode}</span></div>
    <div className="infoBanner"><ShieldCheck/><span>For understanding a document only. This feature does not diagnose, recommend treatment, or replace a healthcare professional. Out-of-range values alone do not establish disease. Reports stay in this local app and are not sent to a cloud AI service.</span></div>
    {error && <div className="errorBox" role="alert"><AlertCircle size={17}/>{error}</div>}

    <div className="reportGrid">
      <aside className="reportSidebar">
        <section className="contentCard reportUpload">
          <div className="eyebrow">ADD A REPORT</div><h2>Upload a laboratory PDF</h2>
          <div className={`dropZone ${dragging ? 'dragging' : ''}`} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); upload(e.dataTransfer.files?.[0]); }}>
            {busy ? <LoaderCircle className="spin"/> : <UploadCloud/>}
            <b>{busy ? 'Processing report…' : 'Drop your PDF here'}</b><small>or choose a file · PDF · up to 10 MB</small>
            <button className="button small" disabled={busy} type="button" onClick={() => inputRef.current?.click()}>Choose PDF</button>
            <input ref={inputRef} hidden type="file" accept="application/pdf,.pdf" aria-label="Choose a laboratory report PDF" onChange={e => upload(e.target.files?.[0])}/>
          </div>
          <small className="muted">Text based PDFs only. Scanned image PDFs need OCR, which is not included. Delete a report to remove its stored file, extracted text, analysis and chat.</small>
        </section>
        <section className="contentCard reportList"><div className="cardTitle"><div><div className="eyebrow">YOUR REPORTS</div><h2>Uploaded reports</h2></div></div>
          {reports.length ? reports.map(report => <div className={`reportListItem ${selected?.id === report.id ? 'active' : ''}`} key={report.id}><button className="reportSelect" onClick={() => chooseReport(report)}><FileText/><span><b>{report.filename}</b><small>Added {new Date(report.created_at).toLocaleDateString()} · {report.status}</small></span></button><button className="cancelBtn" aria-label={`Delete ${report.filename}`} title="Delete report" disabled={busy} onClick={() => removeReport(report)}><Trash2 size={16}/></button></div>) : <div className="empty compact"><span><FileText/></span><h3>No reports yet</h3><p>Your uploaded reports will appear here.</p></div>}
        </section>
      </aside>

      <div className="reportMain">
        {!selected || !analysis ? <section className="contentCard reportPlaceholder"><span><FileText/></span><h2>Select or upload a report</h2><p>We’ll extract readable text and show what the document itself says. Missing ranges and unclear results stay marked as unknown.</p></section> : <>
          <section className="contentCard analysisCard">
            <div className="eyebrow">REPORT OVERVIEW</div><h2>{selected.filename}</h2><p>{analysis.overview?.summary}</p>
            <div className="reportMeta"><span>Report type: <b>{analysis.overview?.report_type}</b></span><span>Report dates: <b>{analysis.overview?.dates?.join(', ') || 'Not identified'}</b></span><span>Uploaded: <b>{new Date(selected.created_at).toLocaleString()}</b></span></div>
          </section>
          <section className="contentCard analysisCard"><div className="eyebrow">TESTS AND VALUES</div><h2>Extracted result lines</h2>
            {analysis.results?.length ? <div className="resultTableWrap"><table className="resultTable"><thead><tr><th>Test</th><th>Value</th><th>Lab range</th><th>Status in report</th><th>Evidence</th></tr></thead><tbody>{analysis.results.map((r,i)=><tr key={`${r.name}-${i}`}><td>{r.name}</td><td>{r.value} {r.unit}</td><td>{r.reference_range || 'Not stated'}</td><td><span className={`resultStatus ${r.status}`}>{({within:'Within stated range',outside_high:'Above stated range',outside_low:'Below stated range',unknown:'Cannot determine'})[r.status] || 'Cannot determine'}</span></td><td><details><summary>Source line</summary><small>{r.evidence}</small></details></td></tr>)}</tbody></table></div> : <p>No structured laboratory result lines were confidently identified in the extracted text. Review the source document directly.</p>}
            <p className="muted">A value is compared only with a range extracted from the same line. Lab flags and extraction can be imperfect; verify every result against the original PDF.</p>
          </section>
          <section className="contentCard analysisCard"><div className="eyebrow">VALUES OUTSIDE A STATED RANGE</div><h2>Values marked outside range</h2>{analysis.outside_range?.length ? <ul>{analysis.outside_range.map((r,i)=><li key={i}><b>{r.name}: {r.value} {r.unit}</b> — {r.status === 'outside_high' ? 'above' : 'below'} the range stated on this line ({r.reference_range}).</li>)}</ul> : <p>No values were confidently identified as outside a stated range. This does not mean results are clinically normal or that the report is complete.</p>}</section>
          <section className="contentCard analysisCard"><div className="eyebrow">PLAIN LANGUAGE</div><h2>What some terms mean</h2>{analysis.term_explanations?.length ? <ul>{analysis.term_explanations.map(x=><li key={x.term}><b>{x.term}</b> — {x.meaning}</li>)}</ul> : <p>No glossary terms were confidently identified. Ask your healthcare professional to explain unfamiliar terms in context.</p>}<h3>Questions to discuss with a healthcare professional</h3><ul>{analysis.questions_for_clinician?.map(q=><li key={q}>{q}</li>)}</ul><h3>Missing or unclear information</h3><ul>{analysis.missing_or_unclear?.map(q=><li key={q}>{q}</li>)}</ul></section>
          <section className="contentCard reportChat"><div className="cardTitle"><div><div className="eyebrow">REPORT-BASED FOLLOW-UP</div><h2><MessageCircle size={17}/> Ask about this report</h2></div><button className="textbtn" onClick={clearChat} disabled={busy}>New conversation</button></div><p className="muted">Answers retrieve matching excerpts from this report only. Local retrieval is keyword based and does not interpret clinical meaning.</p>
            <div className="chatMessages" aria-live="polite">{messages.length ? messages.map((m,i)=><article className={`chatMessage ${m.role}`} key={m.id || `${m.role}-${i}`}><b>{m.role === 'user' ? 'You' : 'Report assistant'}</b><p>{m.content}</p>{m.evidence?.length > 0 && <details><summary>Report evidence</summary><ul>{m.evidence.map((s,j)=><li key={j}>{s}</li>)}</ul></details>}</article>) : <div className="chatEmpty">Try: “Which values are marked high or low by the lab?”</div>}<div ref={chatEnd}/></div>
            <form className="reportChatForm" onSubmit={sendQuestion}><label className="srOnly" htmlFor="report-question">Ask a question about this report</label><input id="report-question" value={question} onChange={e=>setQuestion(e.target.value)} placeholder="Ask a question about this report…" maxLength={1000} disabled={busy}/><button className="button small" disabled={busy || !question.trim()}>{busy ? 'Working…' : 'Ask'}</button></form>
            <small className="medicalDisclaimer">{analysis.disclaimer}</small>
          </section>
        </>}
      </div>
    </div>
    <p className="medicalDisclaimer reportDisclaimer">Demo feature for document understanding. No clinical validation is claimed. Contact a qualified professional for medical advice; seek urgent care if you are experiencing severe or emergency symptoms.</p>
  </main>;
}
