import React, { useState, useEffect } from 'react';
import { Send, AlertCircle, CheckCircle, Filter, Users, User, Clock, FileText, Target, Sparkles } from 'lucide-react';
import BroadcastAIWizard from '../components/BroadcastAIWizard';

const AdminBroadcast = ({ token, initialFilters = null }) => {
  const [text, setText] = useState('');
  const [mode, setMode] = useState(initialFilters ? 'segment' : 'all');
  const [singleUserId, setSingleUserId] = useState('');
  const [aiWizardOpen, setAiWizardOpen] = useState(false);
  
  // Job state
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null); // { status, sent, failed, total }
  
  // History state
  const [history, setHistory] = useState([]);

  useEffect(() => {
    fetchHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let interval;
    if (jobId && jobStatus?.status !== 'completed') {
      interval = setInterval(fetchJobStatus, 1000);
    }
    return () => clearInterval(interval);
  }, [jobId, jobStatus]);

  const fetchHistory = async () => {
    try {
      const res = await fetch('/api/admin/broadcast/history', {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) setHistory(await res.json());
    } catch (e) {
      console.error(e);
    }
  };

  const fetchJobStatus = async () => {
    if (!jobId) return;
    try {
      const res = await fetch(`/api/admin/broadcast/status/${jobId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setJobStatus(data);
        if (data.status === 'completed') {
          setJobId(null);
          fetchHistory();
          setText('');
        }
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleSend = async () => {
    if (!text.trim()) return;
    
    let confirmMsg = `Haqiqatan ham xabar yuborilsinmi?\n\n"${text.slice(0, 50)}..."`;
    if (mode === 'all') confirmMsg = `BARCHA foydalanuvchilarga xabar yuborilsinmi?\n\n"${text.slice(0, 50)}..."`;
    
    if (!confirm(confirmMsg)) return;
    
    const payload = { 
      text: text.trim(),
      mode: mode,
      filters: mode === 'segment' ? initialFilters : null,
      single_user_id: mode === 'user' ? singleUserId : null
    };
    
    try {
      const res = await fetch('/api/admin/broadcast', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.success && data.job_id) {
        setJobId(data.job_id);
        setJobStatus({ status: 'running', sent: 0, failed: 0, total: data.total });
      } else {
        alert("Xatolik: " + data.error);
      }
    } catch (e) {
      alert("Xatolik: " + e.message);
    }
  };

  const isSending = jobId !== null || jobStatus?.status === 'running';
  const progressPercent = jobStatus && jobStatus.total > 0 
    ? Math.min(100, Math.round(((jobStatus.sent + jobStatus.failed) / jobStatus.total) * 100)) 
    : 0;

  return (
    <div className="admin-page fade-in">
      <h1 className="page-title">📣 Broadcast (Xabar tarqatish)</h1>

      <div className="broadcast-grid">
        {/* COMPOSER */}
        <div className="card broadcast-composer">
          <h3>Yangi xabar</h3>
          
          <div className="target-selector">
            <label className={`target-option ${mode === 'all' ? 'active' : ''}`}>
              <input type="radio" name="mode" checked={mode === 'all'} onChange={() => setMode('all')} disabled={isSending}/>
              <Users size={16} /> Barcha foydalanuvchilar
            </label>
            <label className={`target-option ${mode === 'segment' ? 'active' : ''}`}>
              <input type="radio" name="mode" checked={mode === 'segment'} onChange={() => setMode('segment')} disabled={isSending || !initialFilters}/>
              <Filter size={16} /> Segment bo'yicha
            </label>
            <label className={`target-option ${mode === 'user' ? 'active' : ''}`}>
              <input type="radio" name="mode" checked={mode === 'user'} onChange={() => setMode('user')} disabled={isSending}/>
              <User size={16} /> Alohida user
            </label>
          </div>

          {mode === 'segment' && initialFilters && (
            <div className="segment-alert">
              <Filter size={16} color="var(--admin-primary)"/>
              <span>Segment qo'llanilgan (Segmentatsiya sahifasidan keldingiz)</span>
            </div>
          )}

          {mode === 'user' && (
            <input 
              type="number" 
              className="user-id-input mt10" 
              placeholder="Foydalanuvchi Telegram ID si..." 
              value={singleUserId}
              onChange={e => setSingleUserId(e.target.value)}
              disabled={isSending}
            />
          )}

          {/* AI Wizard CTA — textarea ustida */}
          <div style={{
            marginTop: '20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '10px',
            flexWrap: 'wrap',
          }}>
            <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--admin-text-secondary)' }}>
              Xabar matni
            </label>
            <button
              type="button"
              onClick={() => setAiWizardOpen(true)}
              disabled={isSending}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '7px 12px',
                borderRadius: '9px',
                background: 'linear-gradient(135deg, #8B5CF6, #6366F1)',
                color: '#fff',
                border: 'none',
                fontSize: '12px',
                fontWeight: 600,
                cursor: isSending ? 'not-allowed' : 'pointer',
                opacity: isSending ? 0.6 : 1,
                boxShadow: '0 2px 8px rgba(139,92,246,0.35)',
              }}
            >
              <Sparkles size={14} /> AI yordamida yozish
            </button>
          </div>

          <textarea
            className="broadcast-input mt10"
            placeholder="Xabar matnini yozing yoki yuqoridagi 'AI yordamida yozish' tugmasini bosing..."
            value={text}
            onChange={e => setText(e.target.value)}
            rows={6}
            disabled={isSending}
          />

          {/* AI Wizard modal */}
          {aiWizardOpen && (
            <BroadcastAIWizard
              token={token}
              onClose={() => setAiWizardOpen(false)}
              onSelect={(generatedText) => setText(generatedText)}
              language="uz"
            />
          )}

          <div className="broadcast-footer mt20">
            <span className="char-count">{text.length} belgi</span>
            <button className="btn-primary" onClick={handleSend} disabled={isSending || !text.trim() || (mode === 'user' && !singleUserId)}>
              <Send size={16} /> Xabarni yuborish
            </button>
          </div>

          {/* PROGRESS BAR */}
          {jobStatus && (
            <div className="broadcast-progress mt20">
              <div className="bp-header">
                <span className="bp-title">
                  {jobStatus.status === 'running' ? 'Yuborilmoqda...' : 'Yakunlandi!'}
                </span>
                <span className="bp-stats">{jobStatus.sent + jobStatus.failed} / {jobStatus.total}</span>
              </div>
              <div className="bp-track">
                <div className="bp-fill" style={{width: `${progressPercent}%`}}></div>
              </div>
              <div className="bp-details">
                <span className="text-success"><CheckCircle size={12}/> Yuborildi: {jobStatus.sent}</span>
                <span className="text-danger"><AlertCircle size={12}/> Xato: {jobStatus.failed}</span>
              </div>
            </div>
          )}
        </div>

        {/* PREVIEW */}
        <div className="card broadcast-preview">
          <h3><FileText size={16}/> Preview</h3>
          <div className="telegram-message-preview">
            <div className="tm-avatar"></div>
            <div className="tm-bubble">
              <div className="tm-name">Somly AI</div>
              <div className="tm-text">{text || "Xabar shunday ko'rinadi..."}</div>
              <div className="tm-time">12:00</div>
            </div>
          </div>
        </div>
      </div>

      {/* HISTORY */}
      <div className="card mt20">
        <h3><Clock size={16} style={{display: 'inline', marginRight: '5px', verticalAlign: '-3px'}}/> Oxirgi yuborilgan xabarlar</h3>
        {history.length === 0 ? (
          <p className="cell-muted">Hali xabar yuborilmagan.</p>
        ) : (
          <div className="history-table-wrapper mt10">
            <table className="history-table">
              <thead>
                <tr>
                  <th>Sana</th>
                  <th>Kimga</th>
                  <th>Matn</th>
                  <th>Yuborildi</th>
                  <th>Xato</th>
                  <th>Holat</th>
                </tr>
              </thead>
              <tbody>
                {history.map(h => (
                  <tr key={h._id}>
                    <td className="cell-muted">{h.created_at}</td>
                    <td><span className="badge">{h.target}</span></td>
                    <td className="cell-truncate" title={h.text}>{h.text.substring(0, 30)}...</td>
                    <td className="text-success">{h.sent}</td>
                    <td className="text-danger">{h.failed}</td>
                    <td>
                      {h.status === 'completed' ? (
                        <span className="badge success">Tugadi</span>
                      ) : (
                        <span className="badge primary">Jarayonda</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminBroadcast;
