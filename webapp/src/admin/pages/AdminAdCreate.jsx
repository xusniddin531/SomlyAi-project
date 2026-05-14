import React, { useState, useEffect } from 'react';
import { Image, Video, FileText, Send, Calendar, Clock, Bold, Italic, Link2, Plus, GripVertical, Trash2, AlertTriangle, X } from 'lucide-react';

const AdminAdCreate = ({ token, navigateTo, editAdId }) => {
  const [ad, setAd] = useState({
    name: '',
    content_type: 'text',
    text: '',
    media_file_id: '',
    media_url: '',
    caption: '',
    inline_buttons: [],
    targets: ['bot'],
    segment_mode: 'all',
    segment_filters: { age_groups: [], genders: [], regions: [], languages: [] },
    schedule_type: 'now',
    scheduled_at: '',
    duration_hours: 24
  });
  const [channels, setChannels] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [estimate, setEstimate] = useState(null);
  const [showConfirm, setShowConfirm] = useState(false);

  useEffect(() => {
    fetchChannels();
    if (editAdId) {
      fetchAd(editAdId);
    }
  }, [editAdId]);

  useEffect(() => {
    // Fetch estimate whenever targeting changes
    fetchEstimate();
  }, [ad.targets, ad.segment_mode, ad.segment_filters]);

  const fetchChannels = async () => {
    try {
      const res = await fetch('/api/admin/ads/channels', { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setChannels(await res.json());
    } catch (e) { console.error(e); }
  };

  const fetchAd = async (id) => {
    try {
      const res = await fetch(`/api/admin/ads/${id}`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setAd(prev => ({ ...prev, ...data }));
      }
    } catch (e) { console.error(e); }
  };

  const fetchEstimate = async () => {
    try {
      const res = await fetch('/api/admin/ads/estimate', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ targets: ad.targets, segment_mode: ad.segment_mode, segment_filters: ad.segment_filters })
      });
      if (res.ok) setEstimate(await res.json());
    } catch (e) { console.error(e); }
  };

  const handleTextFormat = (tag) => {
    const textarea = document.getElementById('ad-text-editor');
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = ad.text;
    const selected = text.substring(start, end);
    let newText = '';
    if (tag === 'b') newText = text.substring(0, start) + `<b>${selected}</b>` + text.substring(end);
    else if (tag === 'i') newText = text.substring(0, start) + `<i>${selected}</i>` + text.substring(end);
    else if (tag === 'a') {
      const url = prompt("Link URL kiriting:", "https://");
      if (url) newText = text.substring(0, start) + `<a href="${url}">${selected || 'link'}</a>` + text.substring(end);
      else return;
    }
    setAd({ ...ad, text: newText });
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch('/api/admin/ads/upload', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      });
      const data = await res.json();
      if (data.success) {
        setAd({ ...ad, media_file_id: data.file_id, content_type: data.media_type, media_url: URL.createObjectURL(file) });
      } else {
        alert("Xatolik: " + data.error);
      }
    } catch (err) {
      alert("Xatolik: " + err.message);
    } finally {
      setUploading(false);
    }
  };

  const addInlineButton = () => {
    setAd({ ...ad, inline_buttons: [...ad.inline_buttons, [{ text: 'Tugma', url: 'https://' }]] });
  };

  const updateInlineButton = (rowIndex, colIndex, field, value) => {
    const newBtns = [...ad.inline_buttons];
    newBtns[rowIndex][colIndex] = { ...newBtns[rowIndex][colIndex], [field]: value };
    setAd({ ...ad, inline_buttons: newBtns });
  };

  const removeInlineButtonRow = (rowIndex) => {
    const newBtns = ad.inline_buttons.filter((_, i) => i !== rowIndex);
    setAd({ ...ad, inline_buttons: newBtns });
  };

  const handleSaveAndSend = async (action) => {
    if (!ad.name) return alert("Reklama nomini kiriting");
    setSaving(true);
    try {
      // Create/Update Ad
      let savedAdId = editAdId;
      if (!editAdId) {
        const res = await fetch('/api/admin/ads', {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify(ad)
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error);
        savedAdId = data.ad._id;
      }
      
      if (action === 'send') {
        const res2 = await fetch(`/api/admin/ads/${savedAdId}/send`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` }
        });
        const data2 = await res2.json();
        if (!data2.success) throw new Error(data2.error);
        alert(data2.status === 'scheduled' ? "Reklama rejalashtirildi!" : "Reklama yuborish boshlandi!");
      } else {
        alert("Saqlandi!");
      }
      navigateTo('ads');
    } catch (e) {
      alert("Xatolik: " + e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="admin-page fade-in">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h1 className="page-title" style={{ margin: 0 }}>{editAdId ? 'Reklamani tahrirlash' : 'Yangi reklama'}</h1>
        <button className="btn-secondary" onClick={() => navigateTo('ads')}>Orqaga</button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 350px', gap: '20px' }}>
        {/* Editor form */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          
          <div className="card">
            <h3>1. Asosiy ma'lumotlar</h3>
            <input type="text" className="input-field mt10" placeholder="Reklama nomi (Faqat admin uchun)" value={ad.name} onChange={e => setAd({...ad, name: e.target.value})} />
            
            <div style={{ display: 'flex', gap: '10px', marginTop: '16px', flexWrap: 'wrap' }}>
              {[
                {id: 'text', label: 'Matn', icon: FileText},
                {id: 'photo', label: 'Rasm', icon: Image},
                {id: 'video', label: 'Video', icon: Video},
              ].map(t => (
                <button key={t.id} className={`btn-secondary ${ad.content_type === t.id ? 'active' : ''}`} onClick={() => setAd({...ad, content_type: t.id})} style={{ background: ad.content_type === t.id ? 'var(--admin-primary)' : '', color: ad.content_type === t.id ? '#fff' : '' }}>
                  <t.icon size={16}/> {t.label}
                </button>
              ))}
            </div>
          </div>

          <div className="card">
            <h3>2. Kontent</h3>
            {(ad.content_type === 'photo' || ad.content_type === 'video') && (
              <div style={{ marginTop: '10px', padding: '20px', border: '2px dashed var(--admin-border-light)', borderRadius: '12px', textAlign: 'center' }}>
                <input type="file" onChange={handleFileUpload} accept={ad.content_type === 'photo' ? "image/*" : "video/*"} style={{ display: 'none' }} id="media-upload" />
                <label htmlFor="media-upload" className="btn-secondary" style={{ cursor: 'pointer' }}>
                  {uploading ? 'Yuklanmoqda...' : 'Fayl tanlash'}
                </label>
                {ad.media_url && <div style={{ marginTop: '10px', fontSize: '12px', color: 'var(--success)' }}>Fayl yuklandi: {ad.media_file_id}</div>}
              </div>
            )}
            
            <div style={{ marginTop: '16px' }}>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                <button className="btn-icon" onClick={() => handleTextFormat('b')}><Bold size={16}/></button>
                <button className="btn-icon" onClick={() => handleTextFormat('i')}><Italic size={16}/></button>
                <button className="btn-icon" onClick={() => handleTextFormat('a')}><Link2 size={16}/></button>
              </div>
              <textarea id="ad-text-editor" className="input-field" rows={8} placeholder={ad.content_type === 'text' ? "Matn kiriting..." : "Rasm/video izohi (caption)..."} value={ad.text} onChange={e => setAd({...ad, text: e.target.value})} />
            </div>
          </div>

          <div className="card">
            <h3>3. Inline tugmalar</h3>
            {ad.inline_buttons.map((row, rIdx) => (
              <div key={rIdx} style={{ display: 'flex', gap: '8px', marginTop: '10px', alignItems: 'center' }}>
                <GripVertical size={16} style={{ color: 'var(--text-muted)', cursor: 'grab' }} />
                {row.map((btn, cIdx) => (
                  <div key={cIdx} style={{ display: 'flex', gap: '4px', flex: 1 }}>
                    <input type="text" className="input-field" placeholder="Tugma matni" value={btn.text} onChange={e => updateInlineButton(rIdx, cIdx, 'text', e.target.value)} />
                    <input type="text" className="input-field" placeholder="https://" value={btn.url} onChange={e => updateInlineButton(rIdx, cIdx, 'url', e.target.value)} />
                  </div>
                ))}
                <button className="btn-icon" style={{ color: 'var(--danger)' }} onClick={() => removeInlineButtonRow(rIdx)}><Trash2 size={16}/></button>
              </div>
            ))}
            <button className="btn-secondary mt10" style={{ display: 'flex', alignItems: 'center', gap: '6px' }} onClick={addInlineButton}><Plus size={16}/> Qator qo'shish</button>
          </div>

          <div className="card">
            <h3>4. Yuborish sozlamalari</h3>
            
            <div style={{ marginTop: '12px' }}>
              <label style={{ fontWeight: '600', fontSize: '14px', display: 'block', marginBottom: '8px' }}>Qayerga?</label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <input type="checkbox" checked={ad.targets.includes('bot')} onChange={(e) => {
                  if(e.target.checked) setAd({...ad, targets: [...ad.targets, 'bot']});
                  else setAd({...ad, targets: ad.targets.filter(t => t !== 'bot')});
                }}/>
                🤖 Barcha bot foydalanuvchilariga
              </label>
              {channels.map(ch => (
                <label key={ch.username} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                  <input type="checkbox" checked={ad.targets.includes(ch.username)} onChange={(e) => {
                    if(e.target.checked) setAd({...ad, targets: [...ad.targets, ch.username]});
                    else setAd({...ad, targets: ad.targets.filter(t => t !== ch.username)});
                  }}/>
                  📢 {ch.title} ({ch.username}) - {ch.subscriber_count} obunachi
                </label>
              ))}
            </div>

            <div style={{ marginTop: '16px' }}>
              <label style={{ fontWeight: '600', fontSize: '14px', display: 'block', marginBottom: '8px' }}>Vaqti</label>
              <div style={{ display: 'flex', gap: '10px' }}>
                <label><input type="radio" checked={ad.schedule_type === 'now'} onChange={() => setAd({...ad, schedule_type: 'now'})} /> Hozir yuborish</label>
                <label><input type="radio" checked={ad.schedule_type === 'scheduled'} onChange={() => setAd({...ad, schedule_type: 'scheduled'})} /> Rejalashtirish</label>
              </div>
              {ad.schedule_type === 'scheduled' && (
                <div style={{ marginTop: '10px', display: 'flex', gap: '10px', alignItems: 'center' }}>
                  <Calendar size={18} color="var(--text-muted)" />
                  <input type="datetime-local" className="input-field" value={ad.scheduled_at} onChange={e => setAd({...ad, scheduled_at: e.target.value})} />
                </div>
              )}
            </div>

          </div>

        </div>

        {/* Preview & Actions */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          
          {/* Target Estimate Info */}
          <div className="card" style={{ background: 'var(--admin-primary)', color: '#fff' }}>
            <h4 style={{ margin: '0 0 10px 0' }}>Qamrov taxmini</h4>
            {estimate ? (
              <div>
                <div style={{ fontSize: '24px', fontWeight: 'bold' }}>~{estimate.total.toLocaleString()}</div>
                <div style={{ fontSize: '12px', opacity: 0.8 }}>foydalanuvchi va obunachilar</div>
                <div style={{ marginTop: '10px', fontSize: '12px' }}>
                  {estimate.details.map((d, i) => <div key={i}>{d.target}: {d.count}</div>)}
                </div>
              </div>
            ) : <div className="spinner" style={{ borderTopColor: '#fff' }} />}
          </div>

          <div className="card" style={{ padding: '0', overflow: 'hidden' }}>
            <div style={{ padding: '12px', background: 'var(--border)', fontWeight: '600', fontSize: '14px', display: 'flex', alignItems: 'center', gap: '6px' }}>
               Preview
            </div>
            <div style={{ padding: '16px', background: '#e5e5ea', minHeight: '300px', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
               <div style={{ background: '#fff', padding: '8px 12px', borderRadius: '14px 14px 14px 4px', maxWidth: '90%', color: '#000', fontSize: '14px', alignSelf: 'flex-start', boxShadow: '0 1px 2px rgba(0,0,0,0.1)' }}>
                  {ad.media_url && ad.content_type !== 'text' && (
                    <div style={{ marginBottom: '6px', borderRadius: '8px', overflow: 'hidden', maxHeight: '150px' }}>
                      {ad.content_type === 'photo' ? <img src={ad.media_url} style={{ width: '100%', objectFit: 'cover' }} alt="Media" /> : <div style={{ background: '#000', color: '#fff', padding: '20px', textAlign: 'center' }}>VIDEO</div>}
                    </div>
                  )}
                  <div dangerouslySetInnerHTML={{ __html: ad.text ? ad.text.replace(/\n/g, '<br/>') : '<i>Matn yo\'q</i>' }} />
                  <div style={{ fontSize: '10px', color: '#8e8e93', textAlign: 'right', marginTop: '4px' }}>12:00</div>
               </div>
               
               {/* Inline Buttons Preview */}
               {ad.inline_buttons.map((row, rIdx) => (
                 <div key={rIdx} style={{ display: 'flex', gap: '4px', marginTop: '4px', maxWidth: '90%', alignSelf: 'flex-start', width: '100%' }}>
                   {row.map((btn, cIdx) => (
                     <div key={cIdx} style={{ flex: 1, background: '#fff', padding: '10px', borderRadius: '8px', textAlign: 'center', color: '#007aff', fontSize: '14px', fontWeight: '500', cursor: 'pointer', boxShadow: '0 1px 2px rgba(0,0,0,0.1)' }}>
                       {btn.text || 'Tugma'}
                     </div>
                   ))}
                 </div>
               ))}
            </div>
          </div>

          <button className="btn-primary" style={{ padding: '16px', fontSize: '16px' }} onClick={() => setShowConfirm(true)} disabled={saving}>
             {saving ? 'Kuting...' : (ad.schedule_type === 'now' ? '📤 Hozir yuborish' : '📅 Rejalashtirish')}
          </button>
          
          <button className="btn-secondary" onClick={() => handleSaveAndSend('save')} disabled={saving}>
             Qoralama sifatida saqlash
          </button>

        </div>
      </div>

      {/* ── Confirmation Modal ── */}
      {showConfirm && (() => {
        const totalUsers = estimate?.total || 0;
        // Anti-spam calculation: 50 messages per batch, 1.5s each + 30s pause
        const batches = Math.ceil(totalUsers / 50);
        const sendTime = totalUsers * 1.5 + (batches - 1) * 30;
        const estMinutes = Math.ceil(sendTime / 60);
        const estHours = Math.floor(estMinutes / 60);
        const estMins = estMinutes % 60;
        const timeStr = estHours > 0 ? `~${estHours} soat ${estMins} daqiqa` : `~${estMins} daqiqa`;
        const targetList = ad.targets.map(t => t === 'bot' ? '🤖 Bot' : `📢 ${t}`).join(', ');

        return (
          <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999, padding: '20px' }}>
            <div className="card" style={{ maxWidth: '440px', width: '100%', padding: '28px', animation: 'fadeIn 0.2s ease' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
                <div style={{ width: '44px', height: '44px', borderRadius: '12px', background: '#f59e0b20', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <AlertTriangle size={22} color="#f59e0b" />
                </div>
                <div>
                  <h3 style={{ margin: 0, fontSize: '18px' }}>Reklamani yuborish</h3>
                  <p style={{ margin: 0, fontSize: '13px', color: 'var(--text-muted)' }}>Iltimos, tekshiring</p>
                </div>
                <button onClick={() => setShowConfirm(false)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: '4px' }}>
                  <X size={20} />
                </button>
              </div>

              <div style={{ background: 'var(--border)', borderRadius: '12px', padding: '16px', fontSize: '14px', lineHeight: '1.8' }}>
                <div>📋 <b>{ad._id || 'Yangi'}</b>: {ad.name}</div>
                <div>👥 Qamrov: <b>{totalUsers.toLocaleString()}</b> ta foydalanuvchi</div>
                <div>📍 {targetList}</div>
                <div>⏱ Taxminiy vaqt: <b>{timeStr}</b></div>
                <div>📅 Boshlanish: <b>{ad.schedule_type === 'now' ? 'Hozir' : ad.scheduled_at}</b></div>
              </div>

              <div style={{ marginTop: '12px', padding: '10px 14px', borderRadius: '10px', background: '#3b82f610', fontSize: '12px', color: 'var(--text-muted)', lineHeight: '1.6' }}>
                🛡 Anti-spam himoya: Har 1.5 soniyada 1 xabar, har 50 tadan keyin 30s pauza. Telegram spam filtriga tushmaydi.
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
                <button className="btn-secondary" style={{ flex: 1, padding: '14px' }} onClick={() => setShowConfirm(false)}>❌ Bekor</button>
                <button className="btn-primary" style={{ flex: 1, padding: '14px' }} onClick={() => { setShowConfirm(false); handleSaveAndSend('send'); }} disabled={saving}>
                  ✅ Tasdiqlash
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
};

export default AdminAdCreate;
