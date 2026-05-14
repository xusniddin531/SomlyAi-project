import React, { useState, useEffect } from 'react';
import { BarChart3, Send, CheckCircle, Clock, XCircle, Eye, Trash2, Download, RefreshCw, ArrowLeft, Users, AlertTriangle } from 'lucide-react';

const STATUS = {
  draft: { label: 'Qoralama', color: '#6b7280', dot: '⚪' },
  scheduled: { label: 'Rejalashtirilgan', color: '#3b82f6', dot: '🔵' },
  sending: { label: 'Aktiv', color: '#10b981', dot: '🟢' },
  completed: { label: 'Tugagan', color: '#6b7280', dot: '⚪' },
  stopped: { label: "To'xtatilgan", color: '#ef4444', dot: '🔴' },
};

const AdminAdStats = ({ token, navigateTo }) => {
  const [ads, setAds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedAd, setSelectedAd] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [tab, setTab] = useState('active'); // active | archive
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => { fetchAds(); }, []);

  const fetchAds = async () => {
    try {
      const res = await fetch('/api/admin/ads', { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setAds(await res.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const fetchDetail = async (adId) => {
    setDetailLoading(true);
    try {
      const res = await fetch(`/api/admin/ads/${adId}/stats`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setDetailData(await res.json());
    } catch (e) { console.error(e); }
    finally { setDetailLoading(false); }
  };

  const handleStop = async (adId) => {
    if (!confirm("Reklamani to'xtatmoqchimisiz?")) return;
    await fetch(`/api/admin/ads/${adId}/stop`, { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
    fetchAds();
    if (selectedAd === adId) fetchDetail(adId);
  };

  const handleDelete = async (adId) => {
    if (!confirm("Reklamani o'chirmoqchimisiz?")) return;
    await fetch(`/api/admin/ads/${adId}`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
    setAds(prev => prev.filter(a => a._id !== adId));
    if (selectedAd === adId) { setSelectedAd(null); setDetailData(null); }
  };

  const handleExportCSV = () => {
    let url = `/api/admin/ads/export/csv?token=${token}`;
    if (dateFrom) url += `&from=${dateFrom}`;
    if (dateTo) url += `&to=${dateTo}`;
    window.open(url, '_blank');
  };

  const handleExportSingleCSV = (adId) => {
    window.open(`/api/admin/ads/${adId}/export/csv?token=${token}`, '_blank');
  };

  const openDetail = (adId) => {
    setSelectedAd(adId);
    fetchDetail(adId);
  };

  const activeAds = ads.filter(a => ['sending', 'scheduled', 'draft'].includes(a.status));
  const archiveAds = ads.filter(a => ['completed', 'stopped'].includes(a.status));
  const displayAds = tab === 'active' ? activeAds : archiveAds;

  // Progress bar component
  const ProgressBar = ({ value, max, color }) => (
    <div style={{ height: '6px', background: 'var(--border)', borderRadius: '3px', overflow: 'hidden', marginTop: '4px' }}>
      <div style={{ height: '100%', width: `${max > 0 ? (value / max) * 100 : 0}%`, background: color, borderRadius: '3px', transition: 'width 0.5s ease' }} />
    </div>
  );

  // ── Detail View ──
  if (selectedAd && detailData) {
    const d = detailData;
    const st = STATUS[d.status] || STATUS.draft;
    const eng = d.engagement || {};

    return (
      <div className="admin-page fade-in">
        <button className="btn-secondary" onClick={() => { setSelectedAd(null); setDetailData(null); }} style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '20px' }}>
          <ArrowLeft size={16} /> Orqaga
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '24px' }}>
          <h1 className="page-title" style={{ margin: 0 }}>{st.dot} {d.name}</h1>
          <code style={{ fontSize: '12px', background: 'var(--border)', padding: '4px 10px', borderRadius: '6px' }}>{d._id}</code>
          <span style={{ padding: '4px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: '600', background: st.color + '20', color: st.color }}>{st.label}</span>
        </div>

        {/* Stats Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '14px', marginBottom: '20px' }}>
          {[
            { label: 'Yuborildi', value: eng.sent || 0, icon: Send, color: '#10b981' },
            { label: 'Xato', value: eng.failed || 0, icon: XCircle, color: '#ef4444' },
            { label: 'Bloklangan', value: eng.blocked || 0, icon: AlertTriangle, color: '#f59e0b' },
            { label: 'Jami', value: eng.total || 0, icon: Users, color: '#3b82f6' },
          ].map((item, i) => (
            <div key={i} className="card" style={{ padding: '16px', textAlign: 'center' }}>
              <item.icon size={20} style={{ color: item.color, marginBottom: '6px' }} />
              <div style={{ fontSize: '24px', fontWeight: '700', color: item.color }}>{item.value.toLocaleString()}</div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{item.label}</div>
            </div>
          ))}
        </div>

        {/* Progress */}
        <div className="card" style={{ marginBottom: '16px' }}>
          <h3 style={{ marginBottom: '12px' }}>Yuborish jarayoni</h3>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px', marginBottom: '4px' }}>
            <span>Yuborildi: {eng.sent}/{eng.total}</span>
            <span style={{ fontWeight: '600', color: '#10b981' }}>{eng.sent_pct}%</span>
          </div>
          <ProgressBar value={eng.sent} max={eng.total} color="#10b981" />
          {eng.failed > 0 && (
            <div style={{ marginTop: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: '#ef4444' }}>
                <span>Xatolar: {eng.failed}</span>
                <span>{eng.total > 0 ? ((eng.failed / eng.total) * 100).toFixed(1) : 0}%</span>
              </div>
              <ProgressBar value={eng.failed} max={eng.total} color="#ef4444" />
            </div>
          )}
        </div>

        {/* Remaining Time */}
        {d.remaining && (
          <div className="card" style={{ marginBottom: '16px', background: '#10b98115' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Clock size={20} color="#10b981" />
              <div>
                <div style={{ fontWeight: '600', fontSize: '16px' }}>⏱ Qolgan: {d.remaining.hours} soat {d.remaining.minutes} daqiqa</div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Reklama muddati tugagandan so'ng avtomatik to'xtatiladi</div>
              </div>
            </div>
          </div>
        )}

        {/* Info */}
        <div className="card" style={{ marginBottom: '16px' }}>
          <h3 style={{ marginBottom: '12px' }}>Umumiy ma'lumot</h3>
          <table style={{ width: '100%', fontSize: '14px' }}>
            <tbody>
              {[
                ['Reklama ID', d._id],
                ['Nomi', d.name],
                ['Turi', d.content_type],
                ['Yaratildi', d.created_at],
                ['Davomiyligi', d.duration || '—'],
                ['Holat', `${st.dot} ${st.label}`],
                ['Manzil', (d.targets || []).join(', ')],
                ['Segment', d.segment_mode === 'all' ? 'Barcha' : JSON.stringify(d.segment_filters || {})],
              ].map(([k, v], i) => (
                <tr key={i}>
                  <td style={{ padding: '6px 0', color: 'var(--text-muted)', width: '140px' }}>{k}</td>
                  <td style={{ padding: '6px 0', fontWeight: '500' }}>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Channel Results */}
        {d.channel_results && Object.keys(d.channel_results).length > 0 && (
          <div className="card" style={{ marginBottom: '16px' }}>
            <h3 style={{ marginBottom: '12px' }}>📢 Kanal natijalari</h3>
            {Object.entries(d.channel_results).map(([ch, result]) => (
              <div key={ch} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                <span>{ch}</span>
                <span style={{ color: result === 'success' ? '#10b981' : '#ef4444', fontWeight: '600' }}>
                  {result === 'success' ? '✅ Yuborildi' : '❌ Xato'}
                </span>
              </div>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <button className="btn-secondary" onClick={() => fetchDetail(selectedAd)} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <RefreshCw size={16} /> Yangilash
          </button>
          <button className="btn-secondary" onClick={() => handleExportSingleCSV(d._id)} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Download size={16} /> CSV yuklab olish
          </button>
          {(d.status === 'sending' || d.status === 'scheduled') && (
            <button onClick={() => handleStop(d._id)} style={{ padding: '10px 20px', borderRadius: '10px', background: '#ef444420', color: '#ef4444', border: 'none', cursor: 'pointer', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <XCircle size={16} /> To'xtatish
            </button>
          )}
        </div>
      </div>
    );
  }

  // ── List View ──
  if (loading) {
    return (
      <div className="admin-page fade-in">
        <h1 className="page-title">📊 Reklama statistikasi</h1>
        <div className="card" style={{ padding: '40px', textAlign: 'center' }}><div className="spinner" /></div>
      </div>
    );
  }

  return (
    <div className="admin-page fade-in">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '10px' }}>
        <h1 className="page-title" style={{ margin: 0 }}>📊 Reklama statistikasi</h1>
        <button className="btn-secondary" onClick={handleExportCSV} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Download size={16} /> CSV yuklab olish
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '20px', background: 'var(--border)', borderRadius: '12px', padding: '4px' }}>
        {[
          { id: 'active', label: `Aktiv (${activeAds.length})` },
          { id: 'archive', label: `Arxiv (${archiveAds.length})` },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            flex: 1, padding: '10px', borderRadius: '10px', border: 'none', cursor: 'pointer', fontWeight: '600', fontSize: '14px',
            background: tab === t.id ? 'var(--card)' : 'transparent', color: tab === t.id ? 'var(--text)' : 'var(--text-muted)',
            boxShadow: tab === t.id ? '0 1px 3px rgba(0,0,0,0.1)' : 'none', transition: 'all 0.2s'
          }}>{t.label}</button>
        ))}
      </div>

      {/* Date filter for archive */}
      {tab === 'archive' && (
        <div className="card" style={{ padding: '14px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '13px', fontWeight: '600', color: 'var(--text-muted)' }}>Davr:</span>
          <input type="date" className="input-field" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={{ padding: '8px 12px', fontSize: '13px', maxWidth: '160px' }} />
          <span style={{ color: 'var(--text-muted)' }}>—</span>
          <input type="date" className="input-field" value={dateTo} onChange={e => setDateTo(e.target.value)} style={{ padding: '8px 12px', fontSize: '13px', maxWidth: '160px' }} />
          <button className="btn-primary" onClick={handleExportCSV} style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px', fontSize: '13px' }}>
            <Download size={14} /> Barchasini CSV da yuklab olish
          </button>
        </div>
      )}

      {displayAds.length === 0 ? (
        <div className="card" style={{ padding: '50px', textAlign: 'center' }}>
          <BarChart3 size={40} style={{ color: 'var(--text-muted)', opacity: 0.3, marginBottom: '12px' }} />
          <p style={{ color: 'var(--text-muted)' }}>{tab === 'active' ? 'Aktiv reklamalar yo\'q' : 'Arxiv bo\'sh'}</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '14px' }}>
          {displayAds.map(ad => {
            const st = STATUS[ad.status] || STATUS.draft;
            const stats = ad.stats || {};
            const pct = stats.total > 0 ? Math.round(stats.sent / stats.total * 100) : 0;

            return (
              <div key={ad._id} className="card" style={{ padding: '20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '14px' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                      <code style={{ fontSize: '11px', background: 'var(--border)', padding: '2px 8px', borderRadius: '4px' }}>{ad._id}</code>
                      <span style={{ fontWeight: '600', fontSize: '15px' }}>{ad.name}</span>
                    </div>
                    <span style={{ padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: '600', background: st.color + '20', color: st.color }}>
                      {st.dot} {st.label}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    <button onClick={() => openDetail(ad._id)} style={{ padding: '8px 14px', borderRadius: '8px', background: 'var(--admin-primary)', color: '#fff', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <BarChart3 size={14} /> Batafsil
                    </button>
                    {(ad.status === 'sending' || ad.status === 'scheduled') && (
                      <button onClick={() => handleStop(ad._id)} style={{ padding: '8px', borderRadius: '8px', background: '#ef444420', color: '#ef4444', border: 'none', cursor: 'pointer' }}>
                        <XCircle size={14} />
                      </button>
                    )}
                    {tab === 'archive' && (
                      <button onClick={() => handleDelete(ad._id)} style={{ padding: '8px', borderRadius: '8px', background: '#ef444420', color: '#ef4444', border: 'none', cursor: 'pointer' }}>
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', fontSize: '13px' }}>
                  <div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '11px' }}>📤 Yuborildi</div>
                    <div style={{ fontWeight: '600' }}>{(stats.sent || 0).toLocaleString()} / {(stats.total || 0).toLocaleString()}</div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '11px' }}>❌ Xato</div>
                    <div style={{ fontWeight: '600', color: stats.failed > 0 ? '#ef4444' : 'inherit' }}>{stats.failed || 0}</div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '11px' }}>📅 Sana</div>
                    <div style={{ fontWeight: '500', fontSize: '12px' }}>{ad.created_at}</div>
                  </div>
                </div>

                {ad.status === 'sending' && (
                  <div style={{ marginTop: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                      <span>{pct}% yakunlandi</span>
                      <span>{stats.sent}/{stats.total}</span>
                    </div>
                    <ProgressBar value={stats.sent} max={stats.total} color="#10b981" />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <button className="btn-secondary" onClick={fetchAds} style={{ marginTop: '16px', display: 'flex', alignItems: 'center', gap: '6px', margin: '16px auto 0' }}>
        <RefreshCw size={16} /> Yangilash
      </button>
    </div>
  );
};

export default AdminAdStats;
