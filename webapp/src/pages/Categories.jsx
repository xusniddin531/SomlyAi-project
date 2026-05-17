import React, { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Search, MoreVertical, Plus, ChevronDown, ChevronRight, X, Trash2, Check, RefreshCw } from 'lucide-react';
import { fetchApi } from '../utils/api';
import PageHeader from '../components/PageHeader';

const CategoriesPage = ({ initData }) => {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  
  // Accordions
  const [showSystem, setShowSystem] = useState(false);
  
  // Modals
  const [activeModal, setActiveModal] = useState(null); // 'add', 'edit', 'delete', 'emoji'
  const [selectedCat, setSelectedCat] = useState(null);
  
  // Form State
  const [form, setForm] = useState({ name: '', emoji: '💰', type: 'chiqim', color: '#0A84FF' });
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [customColor, setCustomColor] = useState('#0A84FF');

  const [customCats, setCustomCats] = useState([]);
  const [systemCats, setSystemCats] = useState([]);

  // Extended emoji list (30 emojis)
  const allEmojis = ['💰', '🍔', '🚕', '✈️', '🎁', '🛒', '🎮', '🏠', '🏥', '🎓', '👗', '💇‍♀️', '☕', '🍿', '⛽', '📚', '🎬', '🎵', '🏋️', '💪', '🧘', '🎨', '🖼️', '⚽', '🎯', '🎪', '🎭', '🎸', '🎹', '🎤'];
  const colors = ['#FF9F0A', '#0A84FF', '#30D158', '#FFD60A', '#FF453A', '#64D2FF', '#BF5AF2', '#FF375F'];

  const loadCategories = async (isBackground = false) => {
    if (!isBackground) setLoading(true);
    try {
      const response = await fetchApi('/categories');
      if (response && !response.error) {
        setSystemCats(response.system || []);
        // Make sure to add usage dummy field if not returned by backend
        setCustomCats((response.custom || []).map(c => ({...c, usage: c.usage || 0})));
      }
    } catch (err) {
      if (err.message !== 'OFFLINE') window.dispatchEvent(new Event('api_server_error'));
    } finally {
      if (!isBackground) setLoading(false);
      setRefreshing(false);
    }
  };

  const handleWsEvent = useCallback(() => loadCategories(true), []);

  useEffect(() => {
    loadCategories();

    const events = [
      'ws_categories.updated', 'ws_transaction.created',
      'ws_connected', 'ws_sync'
    ];
    events.forEach(e => window.addEventListener(e, handleWsEvent));
    return () => events.forEach(e => window.removeEventListener(e, handleWsEvent));
  }, [handleWsEvent]);

  // AI translation helper (future integration with backend)
  const translateCategoryName = (name) => {
    // Simple example mappings (in production, call AI service)
    const translations = {
      'slap': 'shapat',
      'food': 'ovqat',
      'transport': 'transport',
      'flight': 'parvoz'
    };
    return translations[name.toLowerCase()] || name;
  };

  const filteredCustom = customCats.filter(c => c.name.toLowerCase().includes(searchQuery.toLowerCase()));
  const filteredSystem = systemCats.filter(c => c.name.toLowerCase().includes(searchQuery.toLowerCase()));

  const getTypeLabel = (type) => {
    if (type === 'kirim') return { label: 'Kirim', color: 'var(--success)' };
    if (type === 'chiqim') return { label: 'Chiqim', color: 'var(--danger)' };
    return { label: 'Ikkalasi', color: 'var(--warning)' };
  };

  const openAdd = () => {
    setForm({ name: '', emoji: '💰', type: 'chiqim', color: '#0A84FF' });
    setShowEmojiPicker(false);
    setShowColorPicker(false);
    setActiveModal('add');
  };

  const openEdit = (cat) => {
    setSelectedCat(cat);
    setForm({ name: cat.name, emoji: cat.emoji, type: cat.type, color: cat.color || '#0A84FF' });
    setShowEmojiPicker(false);
    setShowColorPicker(false);
    setActiveModal('edit');
  };

  const saveEdit = async () => {
    if (!form.name) return;
    try {
      // In a full app, we'd have a PUT endpoint. Since backend doesn't have it, we just add a new one and delete old (simplified logic)
      setActiveModal(null);
      await fetchApi(`/categories/${selectedCat.id}`, { method: 'DELETE' });
      await fetchApi('/categories', {
        method: 'POST',
        body: JSON.stringify(form)
      });
      loadCategories(false);
    } catch (e) {
      console.error(e);
      alert("Xato yuz berdi");
    }
  };

  const addCat = async () => {
    if (!form.name) return;
    try {
      setActiveModal(null);
      await fetchApi('/categories', {
        method: 'POST',
        body: JSON.stringify(form)
      });
      loadCategories(false);
    } catch (e) {
      console.error(e);
      alert("Xato yuz berdi");
    }
  };

  const confirmDelete = () => {
    setActiveModal('delete');
  };

  const deleteCat = async () => {
    try {
      setActiveModal(null);
      await fetchApi(`/categories/${selectedCat.id}`, { method: 'DELETE' });
      loadCategories(false);
    } catch (e) {
      console.error(e);
      alert("Xato yuz berdi");
    }
  };

  if (loading) {
    return (
      <div className="animate-fade-in" style={{ padding: '16px' }}>
        <div className="skeleton" style={{ height: '40px', marginBottom: '24px' }}></div>
        <div className="skeleton" style={{ height: '120px', borderRadius: '16px', marginBottom: '16px' }}></div>
        <div className="skeleton" style={{ height: '60px', borderRadius: '16px' }}></div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in" style={{ padding: '0 16px 80px' }}>
      {refreshing && (
        <div style={{ textAlign: 'center', padding: '10px', color: 'var(--text-secondary)' }}>
          <RefreshCw className="animate-spin" size={24} style={{ margin: '0 auto' }} />
        </div>
      )}
      {/* Header */}
      <div className="flex-between" style={{ padding: '16px 0', position: 'sticky', top: 0, background: 'var(--bg)', zIndex: 10 }}>
        {!isSearchOpen ? (
          <div style={{ width: '100%' }}>
            <PageHeader 
              title="Kategoriyalar" 
              showLogo={true} 
              rightElement={
                <div style={{ display: 'flex', gap: '12px' }}>
                  <button onClick={() => setIsSearchOpen(true)} style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: '50%', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-primary)' }}>
                    <Search size={20} />
                  </button>
                  <button style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: '50%', width: '40px', height: '40px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-primary)' }}>
                    <MoreVertical size={20} />
                  </button>
                </div>
              }
            />
          </div>
        ) : (
          <div style={{ display: 'flex', width: '100%', gap: '12px', alignItems: 'center' }}>
            <div style={{ flex: 1, position: 'relative' }}>
              <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)' }} />
              <input 
                type="text" 
                autoFocus
                placeholder="Kategoriya qidiring..." 
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                style={{ width: '100%', background: 'var(--card)', border: '1px solid var(--border)', color: '#FFF', padding: '10px 10px 10px 36px', borderRadius: '12px', outline: 'none' }}
              />
            </div>
            <button onClick={() => { setIsSearchOpen(false); setSearchQuery(''); }} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)' }}>
              Bekor
            </button>
          </div>
        )}
      </div>

      {/* Shaxsiy Kategoriyalar */}
      <div style={{ marginBottom: '32px' }}>
        <div style={{ borderBottom: '1px solid var(--border)', paddingBottom: '8px', marginBottom: '16px' }}>
          <span style={{ fontSize: '14px', color: 'var(--text-secondary)', fontWeight: '600' }}>Shaxsiy kategoriyalar ({filteredCustom.length} ta)</span>
        </div>

        {filteredCustom.length === 0 ? (
          <div onClick={openAdd} style={{ padding: '24px', textAlign: 'center', background: 'var(--card)', borderRadius: '16px', border: '1px dashed var(--border)', cursor: 'pointer' }}>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '12px' }}>Hali shaxsiy kategoriya yo'q</p>
            <span style={{ color: 'var(--primary)', fontWeight: '600', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}><Plus size={18} /> Birinchisini yarating</span>
          </div>
        ) : (
          filteredCustom.map(c => (
            <div 
              key={c.id} 
              onClick={() => openEdit(c)}
              className="card flex-between" 
              style={{ padding: '16px', borderRadius: '16px', marginBottom: '8px', cursor: 'pointer' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <span style={{ fontSize: '28px' }}>{c.emoji}</span>
                <span style={{ fontSize: '16px', fontWeight: '600' }}>{c.name}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '12px', padding: '4px 8px', borderRadius: '8px', background: `${getTypeLabel(c.type).color}22`, color: getTypeLabel(c.type).color, fontWeight: '600' }}>
                  {getTypeLabel(c.type).label}
                </span>
                <ChevronRight size={18} color="var(--text-secondary)" />
              </div>
            </div>
          ))
        )}
      </div>

      {/* Qo'shimcha Kategoriyalar */}
      <div>
        <div 
          onClick={() => setShowSystem(!showSystem)}
          style={{ borderBottom: '1px solid var(--border)', paddingBottom: '8px', marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
        >
          <span style={{ fontSize: '14px', color: 'var(--text-secondary)', fontWeight: '600' }}>Qo'shimcha kategoriyalar ({filteredSystem.length} ta)</span>
          {showSystem ? <ChevronDown size={18} color="var(--text-secondary)" /> : <ChevronRight size={18} color="var(--text-secondary)" />}
        </div>

        {showSystem && filteredSystem.map(c => (
          <div 
            key={c.id} 
            className="flex-between" 
            style={{ padding: '16px', borderRadius: '16px', marginBottom: '8px', background: 'var(--card)' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <span style={{ fontSize: '28px' }}>{c.emoji}</span>
              <span style={{ fontSize: '16px', fontWeight: '500' }}>{c.name}</span>
            </div>
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              {getTypeLabel(c.type).label}
            </span>
          </div>
        ))}
      </div>

      {/* Action Button */}
      <div style={{ marginTop: '24px', paddingBottom: '16px' }}>
        <button 
          onClick={openAdd}
          style={{ width: '100%', padding: '16px', background: 'var(--primary)', color: '#FFF', border: 'none', borderRadius: '16px', fontSize: '16px', fontWeight: 'bold', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', boxShadow: '0 4px 16px var(--primary-glow)', cursor: 'pointer' }}
        >
          <Plus size={20} /> Yangi kategoriya qo'shish
        </button>
      </div>

      {/* Add / Edit Modal - Professional Bottom Sheet */}
      {(activeModal === 'add' || activeModal === 'edit') && createPortal(
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.6)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'flex-end',
          zIndex: 9999
        }}
        onClick={() => { setActiveModal(null); setShowEmojiPicker(false); setShowColorPicker(false); }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--card)',
              width: '100%',
              borderRadius: '24px 24px 0 0',
              padding: '24px 20px',
              maxHeight: '92vh',
              overflowY: 'auto'
            }}
          >
            {/* Header */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '24px'
            }}>
              <h2 style={{
                margin: 0,
                fontSize: '22px',
                fontWeight: '700'
              }}>
                {activeModal === 'add' ? 'Yangi kategoriya qo\'shish' : 'Kategoriyani tahrirlash'}
              </h2>
              <button
                onClick={() => { setActiveModal(null); setShowEmojiPicker(false); setShowColorPicker(false); }}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'var(--text-secondary)',
                  fontSize: '24px',
                  padding: '4px'
                }}
              >
                ✕
              </button>
            </div>

            {/* Emoji Picker Button + Name Input */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{
                fontSize: '12px',
                color: 'var(--text-secondary)',
                fontWeight: '600',
                display: 'block',
                marginBottom: '8px'
              }}>
                Kategoriya nomi
              </label>
              <div style={{
                display: 'flex',
                gap: '8px'
              }}>
                <button
                  onClick={() => setShowEmojiPicker(!showEmojiPicker)}
                  style={{
                    width: '52px',
                    height: '52px',
                    minWidth: '52px',
                    borderRadius: '12px',
                    background: 'var(--bg)',
                    border: '2px solid var(--border)',
                    fontSize: '28px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                  onMouseOver={(e) => e.target.style.borderColor = 'var(--primary)'}
                  onMouseOut={(e) => e.target.style.borderColor = 'var(--border)'}
                >
                  {form.emoji}
                </button>
                <input
                  type="text"
                  placeholder="Kategoriya nomini kiriting..."
                  value={form.name}
                  onChange={(e) => setForm({...form, name: e.target.value})}
                  style={{
                    flex: 1,
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    padding: '12px 16px',
                    borderRadius: '12px',
                    color: 'var(--text-primary)',
                    fontSize: '15px',
                    outline: 'none'
                  }}
                />
              </div>

              {/* Emoji Picker Grid */}
              {showEmojiPicker && (
                <div style={{
                  marginTop: '12px',
                  background: 'var(--bg)',
                  border: '1px solid var(--border)',
                  borderRadius: '12px',
                  padding: '12px',
                  display: 'grid',
                  gridTemplateColumns: 'repeat(6, 1fr)',
                  gap: '6px',
                  maxHeight: '200px',
                  overflowY: 'auto'
                }}>
                  {allEmojis.map((emoji) => (
                    <button
                      key={emoji}
                      onClick={() => {
                        setForm({...form, emoji});
                        setShowEmojiPicker(false);
                      }}
                      style={{
                        background: form.emoji === emoji ? 'rgba(10, 132, 255, 0.2)' : 'transparent',
                        border: form.emoji === emoji ? '2px solid var(--primary)' : '1px solid var(--border)',
                        borderRadius: '8px',
                        fontSize: '22px',
                        padding: '8px',
                        cursor: 'pointer',
                        transition: 'all 0.1s'
                      }}
                      onMouseOver={(e) => e.target.style.background = 'rgba(10, 132, 255, 0.1)'}
                      onMouseOut={(e) => e.target.style.background = form.emoji === emoji ? 'rgba(10, 132, 255, 0.2)' : 'transparent'}
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              )}

              {/* AI Translation Info */}
              <p style={{
                marginTop: '8px',
                fontSize: '11px',
                color: 'var(--text-secondary)',
                lineHeight: '1.4'
              }}>
                💡 Masalan: "slap" → Somly AI avtomatik "shapat" tarjima qiladi
              </p>
            </div>

            {/* Color Picker Section */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{
                fontSize: '12px',
                color: 'var(--text-secondary)',
                fontWeight: '600',
                display: 'block',
                marginBottom: '8px'
              }}>
                Rangi
              </label>
              <div style={{
                display: 'flex',
                gap: '8px',
                alignItems: 'center'
              }}>
                {colors.map((c) => (
                  <button
                    key={c}
                    onClick={() => setForm({...form, color: c})}
                    style={{
                      width: '44px',
                      height: '44px',
                      borderRadius: '12px',
                      backgroundColor: c,
                      border: form.color === c ? '3px solid #FFF' : '2px solid rgba(255,255,255,0.2)',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      boxShadow: form.color === c ? `0 0 16px ${c}99` : `0 2px 8px ${c}33`,
                      transition: 'all 0.2s'
                    }}
                  >
                    {form.color === c && <Check size={18} color="#000" strokeWidth={3} />}
                  </button>
                ))}
                <button
                  onClick={() => setShowColorPicker(!showColorPicker)}
                  style={{
                    width: '44px',
                    height: '44px',
                    borderRadius: '12px',
                    background: 'var(--bg)',
                    border: '2px dashed var(--border)',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'var(--text-secondary)',
                    fontSize: '20px',
                    transition: 'all 0.2s'
                  }}
                  onMouseOver={(e) => e.target.style.borderColor = 'var(--primary)'}
                  onMouseOut={(e) => e.target.style.borderColor = 'var(--border)'}
                >
                  ＋
                </button>
              </div>

              {/* Custom Color Picker */}
              {showColorPicker && (
                <div style={{
                  marginTop: '12px',
                  padding: '12px',
                  background: 'var(--bg)',
                  borderRadius: '12px',
                  border: '1px solid var(--border)'
                }}>
                  <input
                    type="color"
                    value={form.color}
                    onChange={(e) => setForm({...form, color: e.target.value})}
                    style={{
                      width: '100%',
                      height: '50px',
                      border: 'none',
                      borderRadius: '8px',
                      cursor: 'pointer'
                    }}
                  />
                </div>
              )}
            </div>

            {/* Category Type Selection */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{
                fontSize: '12px',
                color: 'var(--text-secondary)',
                fontWeight: '600',
                display: 'block',
                marginBottom: '8px'
              }}>
                Turi
              </label>
              <div style={{
                display: 'flex',
                gap: '8px',
                background: 'var(--bg)',
                padding: '4px',
                borderRadius: '12px'
              }}>
                {[
                  { id: 'kirim', label: 'Kirim' },
                  { id: 'chiqim', label: 'Chiqim' },
                  { id: 'ikkalasi', label: 'Ikkalasi' }
                ].map(t => (
                  <button
                    key={t.id}
                    onClick={() => setForm({...form, type: t.id})}
                    style={{
                      flex: 1,
                      padding: '10px',
                      border: 'none',
                      borderRadius: '10px',
                      fontSize: '13px',
                      fontWeight: '600',
                      transition: 'all 0.2s',
                      background: form.type === t.id ? 'var(--card)' : 'transparent',
                      color: form.type === t.id ? '#FFF' : 'var(--text-secondary)',
                      boxShadow: form.type === t.id ? '0 2px 8px rgba(0,0,0,0.2)' : 'none'
                    }}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Help Text */}
            <div style={{
              background: 'rgba(10, 132, 255, 0.08)',
              border: '1px solid rgba(10, 132, 255, 0.2)',
              borderRadius: '12px',
              padding: '12px 14px',
              marginBottom: '20px',
              fontSize: '12px',
              color: 'var(--text-secondary)',
              lineHeight: '1.5',
              textAlign: 'center'
            }}>
              🤖 Emoji va Rang tanlamasangiz,<br/>
              Somly AI avtomatik o'zi yaratadi!
            </div>

            {/* Action Buttons */}
            {activeModal === 'add' ? (
              <button
                onClick={addCat}
                disabled={!form.name}
                style={{
                  width: '100%',
                  background: form.name ? '#1E3A8A' : 'var(--border)',
                  border: 'none',
                  padding: '16px 20px',
                  borderRadius: '12px',
                  color: '#fff',
                  fontWeight: '700',
                  fontSize: '15px',
                  cursor: form.name ? 'pointer' : 'not-allowed',
                  opacity: form.name ? 1 : 0.6,
                  boxShadow: form.name ? '0 4px 12px rgba(30, 58, 138, 0.3)' : 'none',
                  transition: 'all 0.2s'
                }}
                onMouseOver={(e) => { if (form.name) e.target.style.background = '#163066'; }}
                onMouseOut={(e) => { if (form.name) e.target.style.background = '#1E3A8A'; }}
              >
                Saqlash
              </button>
            ) : (
              <div style={{ display: 'flex', gap: '12px' }}>
                <button
                  onClick={confirmDelete}
                  style={{
                    width: '60px',
                    padding: '16px 0',
                    background: 'rgba(255, 69, 58, 0.1)',
                    color: 'var(--danger)',
                    border: 'none',
                    borderRadius: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    fontWeight: '600'
                  }}
                >
                  🗑
                </button>
                <button
                  onClick={saveEdit}
                  style={{
                    flex: 1,
                    background: '#1E3A8A',
                    border: 'none',
                    padding: '16px 20px',
                    borderRadius: '12px',
                    color: '#fff',
                    fontWeight: '700',
                    fontSize: '15px',
                    cursor: 'pointer',
                    boxShadow: '0 4px 12px rgba(30, 58, 138, 0.3)',
                    transition: 'all 0.2s'
                  }}
                  onMouseOver={(e) => e.target.style.background = '#163066'}
                  onMouseOut={(e) => e.target.style.background = '#1E3A8A'}
                >
                  Saqlash
                </button>
              </div>
            )}
          </div>
        </div>,
        document.body
      )}

      {/* Delete Confirmation Modal */}
      {activeModal === 'delete' && selectedCat && createPortal(
        <div className="modal-overlay" onClick={() => setActiveModal('edit')} style={{ zIndex: 9999 }}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ textAlign: 'center' }}>
            <div style={{ width: '64px', height: '64px', background: 'rgba(255, 69, 58, 0.1)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px', color: 'var(--danger)' }}>
              <Trash2 size={32} />
            </div>
            <h3 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '12px' }}>O'chirish</h3>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '32px', lineHeight: '1.5' }}>
              Bu kategoriya <b>{selectedCat.usage}</b> ta tranzaksiyada ishlatilgan.<br/>
              O'chirilsa 'Boshqa xarajatlar' ga o'tkaziladi.
            </p>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <button onClick={deleteCat} style={{ width: '100%', padding: '16px', background: 'var(--danger)', border: 'none', borderRadius: '16px', color: 'white', fontWeight: 'bold', fontSize: '16px' }}>
                Ha, o'chir 🗑
              </button>
              <button onClick={() => setActiveModal('edit')} style={{ width: '100%', padding: '16px', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: '16px', color: 'var(--text-primary)', fontWeight: 'bold', fontSize: '16px' }}>
                Bekor ❌
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
};

export default CategoriesPage;
