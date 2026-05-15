import React, { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { Plus, MoreVertical, CreditCard, ChevronDown, X, Check, Edit2, Trash2, PieChart, Wallet, Search, RefreshCw, ShieldCheck, Smartphone, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { fetchApi, getExchangeRates } from '../utils/api';
import PageHeader from '../components/PageHeader';

const BalancesPage = ({ initData }) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [balances, setBalances] = useState([]);
  const [sharedWallets, setSharedWallets] = useState([]);
  const [invites, setInvites] = useState([]);
  
  // Modals
  const [activeModal, setActiveModal] = useState(null); // 'add', 'action', 'transfer', 'currency', 'card', 'otp'
  const [selectedBal, setSelectedBal] = useState(null);
  const [transferForm, setTransferForm] = useState({ toBalanceId: '', amount: '' });
  const [inviteForm, setInviteForm] = useState({ contact: '', role: 'member' });
  
  // Add Balance Form
  const [addForm, setAddForm] = useState({ title: '', emoji: '💰', amount: '', currency: 'UZS', color: '#0A84FF', hasLimit: false, limitAmount: '', type: 'personal', members: [] });
  const [newMemberPhone, setNewMemberPhone] = useState('');
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [showColorPicker, setShowColorPicker] = useState(false);
  const [customColor, setCustomColor] = useState('#0A84FF');
  const [exchangeRates, setExchangeRates] = useState({});
  
  const [cardForm, setCardForm] = useState({ number: '', otp: '' });
  const [isCardModalOpen, setIsCardModalOpen] = useState(false);
  const [isOtpModalOpen, setIsOtpModalOpen] = useState(false);
  const [useLimit, setUseLimit] = useState(false);
  const [limitAmount, setLimitAmount] = useState('');

  // Currencies
  const topCurrencies = [
    { code: 'UZS', flag: '🇺🇿', name: "O'zbek so'mi" },
    { code: 'USD', flag: '🇺🇸', name: "AQSh dollari" },
    { code: 'RUB', flag: '🇷🇺', name: "Rossiya rubli" },
    { code: 'KZT', flag: '🇰🇿', name: "Qozoq tengesi" }
  ];
  const otherCurrencies = [
    { code: 'EUR', flag: '🇪🇺', name: 'Yevro' },
    { code: 'GBP', flag: '🇬🇧', name: 'Britaniya funti' },
    { code: 'JPY', flag: '🇯🇵', name: 'Yapon iyenasi' },
    { code: 'CNY', flag: '🇨🇳', name: 'Xitoy yuani' },
    { code: 'AED', flag: '🇦🇪', name: 'BAA dirhami' },
    { code: 'TRY', flag: '🇹🇷', name: 'Turk lirasi' },
  ];
  const [currencySearch, setCurrencySearch] = useState('');

  const colors = ['#FF9F0A', '#0A84FF', '#30D158', '#FFD60A', '#FF453A', '#64D2FF', '#BF5AF2', '#FF375F'];
  const emojis = ['💰', '💳', '🏦', '💵', '💴', '💶', '💷', '🪙', '🏧', '💸', '📊', '📈', '📉', '🤑', '💎', '⭐', '🎯', '🎁', '🛍️', '🎪', '🎨', '🎭', '🎬', '🎮', '🎲', '🎯', '⚡', '🔥', '❄️', '🌟'];
  // Load exchange rates on mount
  useEffect(() => {
    const loadExchangeRates = async () => {
      try {
        const rates = await getExchangeRates();
        if (rates) {
          setExchangeRates(rates);
        }
      } catch (err) {
        console.error('Failed to load exchange rates:', err);
      }
    };
    loadExchangeRates();
  }, []);

  const loadBalances = async (isBackground = false) => {
    if (!isBackground) setLoading(true);
    try {
      const response = await fetchApi('/dashboard');
      if (response && response.balances) {
        const enhancedBalances = response.balances.map((b) => ({
          id: b.currency,
          currency: b.currency,
          flag: b.emoji || (b.currency === 'UZS' ? '🇺🇿' : '🇺🇸'),
          emoji: b.emoji,
          title: b.title || (b.currency === 'UZS' ? "So'm" : "Dollar"),
          amount: b.amount,
          income: response.stats?.[b.currency]?.Hammasi?.find(s => s.name === 'Kirim')?.value || 0,
          expense: response.stats?.[b.currency]?.Hammasi?.find(s => s.name === 'Chiqim')?.value || 0,
          limit: b.limit || null,
          limitUsed: 0,
          color: b.color || (b.currency === 'UZS' ? '#0A84FF' : '#30D158')
        }));
        setBalances(enhancedBalances);
      }
      
      const sharedRes = await fetchApi('/shared_wallets');
      if (sharedRes) setSharedWallets(sharedRes);
      
      const inviteRes = await fetchApi('/shared_wallets/invites');
      if (inviteRes) setInvites(inviteRes);
    } catch (err) {
      if (err.message !== 'OFFLINE') window.dispatchEvent(new Event('api_server_error'));
    } finally {
      if (!isBackground) setLoading(false);
      setRefreshing(false);
    }
  };

  const handleWsEvent = useCallback(() => loadBalances(true), []);

  useEffect(() => {
    loadBalances();

    const events = [
      'ws_balance.updated', 'ws_transaction.created',
      'ws_transaction.updated', 'ws_transaction.deleted',
      'ws_connected', 'ws_sync'
    ];
    events.forEach(e => window.addEventListener(e, handleWsEvent));
    return () => events.forEach(e => window.removeEventListener(e, handleWsEvent));
  }, [handleWsEvent]);

  const getProgressClass = (percent) => {
    if (percent < 50) return 'safe';
    if (percent < 80) return 'warning';
    return 'danger';
  };

  const formatMoney = (amount) => amount.toLocaleString();

  const handleActionClick = (b) => {
    setSelectedBal(b);
    setActiveModal('action');
  };

  const handleAddBalance = async () => {
    if (!addForm.amount || !addForm.title) return;
    
    const payload = {
      currency: addForm.currency,
      title: addForm.title,
      emoji: addForm.emoji,
      amount: addForm.amount,
      color: addForm.color,
      limit: addForm.hasLimit ? addForm.limitAmount : null
    };

    try {
      setActiveModal(null);
      setShowEmojiPicker(false);
      setShowColorPicker(false);
      setAddForm({ title: '', emoji: '💰', amount: '', currency: 'UZS', color: '#0A84FF', hasLimit: false, limitAmount: '' });
      await fetchApi('/balances', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      loadBalances(false); // reload immediately
    } catch (e) {
      console.error(e);
      alert("Xato yuz berdi");
    }
  };

  return (
    <div className="animate-fade-in" style={{ padding: '0 16px 40px' }}>
      <PageHeader title={t('balances.title')} showLogo={true} />

      {/* Invites Banner */}
      {invites.length > 0 && (
        <div style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', borderRadius: '16px', padding: '16px', marginBottom: '20px' }}>
          <p style={{ margin: '0 0 12px 0', fontSize: '14px', fontWeight: 600, color: '#8B5CF6' }}>👥 Umumiy hamyon takliflari ({invites.length})</p>
          {invites.map(inv => (
            <div key={inv.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.05)', padding: '10px', borderRadius: '12px', marginBottom: '8px' }}>
              <span style={{ fontSize: '13px' }}>{inv.wallet_name}</span>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button 
                  onClick={async () => {
                    await fetchApi(`/shared_wallets/invites/${inv.id}/action`, { method: 'POST', body: JSON.stringify({ action: 'accept' }) });
                    loadBalances();
                  }}
                  style={{ background: '#10B981', border: 'none', borderRadius: '8px', color: '#fff', padding: '6px 12px', fontSize: '12px', fontWeight: 600 }}
                >
                  Qabul
                </button>
                <button 
                  onClick={async () => {
                    await fetchApi(`/shared_wallets/invites/${inv.id}/action`, { method: 'POST', body: JSON.stringify({ action: 'reject' }) });
                    loadBalances();
                  }}
                  style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: '8px', color: '#fff', padding: '6px 12px', fontSize: '12px', fontWeight: 600 }}
                >
                  Rad
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Action Buttons */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '24px', marginTop: '8px' }}>
        <button 
          onClick={() => setActiveModal('add')}
          style={{ flex: 1, padding: '14px', background: 'var(--primary)', border: 'none', borderRadius: '16px', color: '#FFF', fontWeight: 'bold', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', boxShadow: '0 4px 12px var(--primary-glow)' }}
        >
          <Plus size={20} /> {t('balances.new_balance')}
        </button>
        <button 
          onClick={() => setActiveModal('add_shared')}
          style={{ flex: 1, padding: '14px', background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', borderRadius: '16px', color: '#8B5CF6', fontWeight: 'bold', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
        >
          <Users size={20} /> Umumiy
        </button>
      </div>

      {loading ? (
        <div>
          <div className="skeleton" style={{ height: '180px', borderRadius: '24px', marginBottom: '16px' }}></div>
          <div className="skeleton" style={{ height: '180px', borderRadius: '24px' }}></div>
        </div>
      ) : (
        balances.map(b => {
          const limitPercent = b.limit ? Math.min(100, Math.round((b.limitUsed / b.limit) * 100)) : 0;
          return (
            <div key={b.id} style={{ 
              background: `linear-gradient(135deg, ${b.color} 0%, #1A1A1C 120%)`,
              borderRadius: '24px', padding: '24px', marginBottom: '16px', position: 'relative', overflow: 'hidden',
              boxShadow: `0 8px 24px ${b.color}33`
            }}>
              <div className="flex-between" style={{ marginBottom: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '20px' }}>{b.flag}</span>
                  <span style={{ fontSize: '18px', fontWeight: '600', color: '#FFF' }}>{b.title}</span>
                </div>
                <button onClick={() => handleActionClick(b)} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', width: '32px', height: '32px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#FFF' }}>
                  <MoreVertical size={18} />
                </button>
              </div>

              <h2 style={{ fontSize: '32px', fontWeight: '800', margin: '0 0 16px', color: '#FFF' }}>
                {formatMoney(b.amount)} <span style={{ fontSize: '18px', fontWeight: '600', opacity: 0.8 }}>{b.currency}</span>
              </h2>

              <div className="flex-between" style={{ background: 'rgba(0,0,0,0.2)', padding: '12px 16px', borderRadius: '16px' }}>
                <div>
                  <p style={{ fontSize: '12px', color: 'rgba(255,255,255,0.7)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ color: '#30D158' }}>↑</span> {t('dashboard.income')}
                  </p>
                  <p style={{ fontWeight: '700', fontSize: '15px', color: '#FFF', marginTop: '2px' }}>{formatMoney(b.income)}</p>
                </div>
                <div style={{ width: '1px', height: '24px', background: 'rgba(255,255,255,0.2)' }}></div>
                <div style={{ textAlign: 'right' }}>
                  <p style={{ fontSize: '12px', color: 'rgba(255,255,255,0.7)', display: 'flex', alignItems: 'center', gap: '4px', justifyContent: 'flex-end' }}>
                    <span style={{ color: '#FF453A' }}>↓</span> {t('dashboard.expense')}
                  </p>
                  <p style={{ fontWeight: '700', fontSize: '15px', color: '#FFF', marginTop: '2px' }}>{formatMoney(b.expense)}</p>
                </div>
              </div>

              {b.limit && (
                <div style={{ marginTop: '20px', background: 'rgba(0,0,0,0.2)', padding: '12px', borderRadius: '16px' }}>
                  <div className="flex-between" style={{ marginBottom: '8px', fontSize: '13px' }}>
                    <span style={{ color: 'rgba(255,255,255,0.8)' }}>Limitdan {limitPercent}% foydalanildi</span>
                    <span style={{ color: '#FFF', fontWeight: 600 }}>Qoldi: {formatMoney(b.limit - b.limitUsed)}</span>
                  </div>
                  <div className="progress-bg" style={{ height: '8px', backgroundColor: 'rgba(255,255,255,0.1)' }}>
                    <div 
                      className={`progress-fill ${getProgressClass(limitPercent)}`}
                      style={{ width: `${limitPercent}%` }}
                    ></div>
                  </div>
                </div>
              )}
            </div>
          );
        })
      )}

      {/* Shared Wallets Section */}
      {sharedWallets.length > 0 && (
        <div style={{ marginTop: '24px' }}>
          <h2 style={{ fontSize: '18px', fontWeight: '700', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Users size={20} className="text-primary" />
            Umumiy hamyonlar
          </h2>
          {sharedWallets.map(w => (
            <div key={w.id} style={{ 
              background: `linear-gradient(135deg, ${w.color} 0%, #1A1A1C 120%)`,
              borderRadius: '24px', padding: '24px', marginBottom: '16px', position: 'relative', overflow: 'hidden',
              boxShadow: `0 8px 24px ${w.color}33`
            }}>
              <div className="flex-between" style={{ marginBottom: '16px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '20px' }}>👥</span>
                  <span style={{ fontSize: '18px', fontWeight: '600', color: '#FFF' }}>{w.name}</span>
                </div>
                <button onClick={() => { setSelectedBal(w); setActiveModal('shared_action'); }} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', width: '32px', height: '32px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#FFF' }}>
                  <MoreVertical size={18} />
                </button>
              </div>

              <h2 style={{ fontSize: '32px', fontWeight: '800', margin: '0 0 16px', color: '#FFF' }}>
                {formatMoney(w.amount)} <span style={{ fontSize: '18px', fontWeight: '600', opacity: 0.8 }}>{w.currency}</span>
              </h2>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div style={{ display: 'flex', marginLeft: '4px' }}>
                  {w.members.slice(0, 3).map((m, idx) => (
                    <div key={idx} style={{ 
                      width: '24px', height: '24px', borderRadius: '50%', background: 'var(--primary)', 
                      border: '2px solid #1A1A1C', marginLeft: idx === 0 ? 0 : '-8px',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', color: '#fff', fontWeight: 'bold'
                    }}>
                      {m.name.charAt(0)}
                    </div>
                  ))}
                  {w.members.length > 3 && (
                    <div style={{ 
                      width: '24px', height: '24px', borderRadius: '50%', background: 'rgba(255,255,255,0.2)', 
                      border: '2px solid #1A1A1C', marginLeft: '-8px',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '10px', color: '#fff'
                    }}>
                      +{w.members.length - 3}
                    </div>
                  )}
                </div>
                <span style={{ fontSize: '12px', color: 'rgba(255,255,255,0.7)' }}>{w.members.length} a'zo</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Action Modal - Bottom Sheet */}
      {activeModal === 'action' && selectedBal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'flex-end',
          zIndex: 1000
        }}
        onClick={() => setActiveModal(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--card)',
              width: '100%',
              borderRadius: '20px 20px 0 0',
              padding: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '0'
            }}
          >
            {/* Transfer Option */}
            <button
              onClick={() => setActiveModal('transfer')}
              style={{
                background: 'none',
                border: 'none',
                padding: '16px 0',
                fontSize: '16px',
                fontWeight: '500',
                color: 'var(--text-primary)',
                cursor: 'pointer',
                textAlign: 'left',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                borderBottom: '1px solid var(--border)'
              }}
            >
              💼 Balansdan balansga o'tkazish
              <span style={{ marginLeft: 'auto', color: 'var(--text-secondary)' }}>›</span>
            </button>

            {/* Reports Option */}
            <button
              onClick={() => {
                setActiveModal(null);
                // Navigate to reports filtered by this balance
                window.location.href = '/reports';
              }}
              style={{
                background: 'none',
                border: 'none',
                padding: '16px 0',
                fontSize: '16px',
                fontWeight: '500',
                color: 'var(--text-primary)',
                cursor: 'pointer',
                textAlign: 'left',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                borderBottom: '1px solid var(--border)'
              }}
            >
              📊 Balansi hisobotlarini ko'rish
              <span style={{ marginLeft: 'auto', color: 'var(--text-secondary)' }}>›</span>
            </button>

            {/* Edit Option */}
            <button
              onClick={() => {
                setAddForm({
                  title: selectedBal.title,
                  emoji: selectedBal.emoji || '💰',
                  color: selectedBal.color || '#0A84FF',
                  currency: selectedBal.currency,
                  amount: selectedBal.amount, // Just for display if needed
                  hasLimit: selectedBal.limit ? true : false,
                  limitAmount: selectedBal.limit || ''
                });
                setActiveModal('edit_balance');
              }}
              style={{
                background: 'none',
                border: 'none',
                padding: '16px 0',
                fontSize: '16px',
                fontWeight: '500',
                color: 'var(--text-primary)',
                cursor: 'pointer',
                textAlign: 'left',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                borderBottom: '1px solid var(--border)'
              }}
            >
              ✏️ Balansni tahrirlash
              <span style={{ marginLeft: 'auto', color: 'var(--text-secondary)' }}>›</span>
            </button>

            {/* Delete Option */}
            {selectedBal && selectedBal.currency !== 'UZS' && (
            <button
              onClick={async () => {
                try {
                  const checkRes = await fetchApi(`/balances/${selectedBal.currency}/check_delete`);
                  let msg = `${selectedBal.title} o'chirilsinmi?`;
                  if (checkRes && checkRes.count > 0) {
                    msg = `⚠️ Bu balansda ${checkRes.count} ta tranzaksiya bor.\nO'chirilsa barcha tranzaksiyalar 'So'm' balansiga o'tkaziladi.\nDavom etasizmi?`;
                  }
                  
                  if (window.confirm(msg)) {
                    await fetchApi(`/balances/${selectedBal.currency}`, { method: 'DELETE' });
                    setActiveModal(null);
                    loadBalances();
                  }
                } catch(e) {
                  console.error(e);
                  alert("Xatolik yuz berdi");
                }
              }}
              style={{
                background: 'none',
                border: 'none',
                padding: '16px 0',
                fontSize: '16px',
                fontWeight: '500',
                color: 'var(--danger)',
                cursor: 'pointer',
                textAlign: 'left',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                borderBottom: '1px solid var(--border)'
              }}
            >
              🗑 Balansni o'chirish
              <span style={{ marginLeft: 'auto', color: 'var(--text-secondary)' }}>›</span>
            </button>
            )}

            {/* Back Button */}
            <button
              onClick={() => setActiveModal(null)}
              style={{
                background: 'var(--bg)',
                border: 'none',
                padding: '14px 16px',
                borderRadius: '12px',
                fontSize: '16px',
                fontWeight: '600',
                color: 'var(--text-primary)',
                cursor: 'pointer',
                marginTop: '12px'
              }}
            >
              Ortga qaytish
            </button>
          </div>
        </div>
      )}

      {/* Add Balance Modal - Professional Design */}
      {activeModal === 'add' && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.6)',
          display: 'flex',
          alignItems: 'flex-end',
          zIndex: 1000
        }}
        onClick={() => setActiveModal(null)}
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
                Balans qo'shish
              </h2>
              <button
                onClick={() => setActiveModal(null)}
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

            {/* Type Switcher */}
            <div style={{ marginBottom: '20px', display: 'flex', gap: '8px', background: 'var(--bg)', padding: '4px', borderRadius: '14px' }}>
              <button
                onClick={() => setAddForm({...addForm, type: 'personal'})}
                style={{
                  flex: 1,
                  padding: '10px',
                  borderRadius: '10px',
                  border: 'none',
                  background: addForm.type === 'personal' ? 'var(--card)' : 'transparent',
                  color: addForm.type === 'personal' ? 'var(--text-primary)' : 'var(--text-secondary)',
                  fontWeight: addForm.type === 'personal' ? '600' : '500',
                  boxShadow: addForm.type === 'personal' ? '0 2px 8px rgba(0,0,0,0.05)' : 'none',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
              >
                👤 Shaxsiy
              </button>
              <button
                onClick={() => setAddForm({...addForm, type: 'shared'})}
                style={{
                  flex: 1,
                  padding: '10px',
                  borderRadius: '10px',
                  border: 'none',
                  background: addForm.type === 'shared' ? 'var(--card)' : 'transparent',
                  color: addForm.type === 'shared' ? 'var(--text-primary)' : 'var(--text-secondary)',
                  fontWeight: addForm.type === 'shared' ? '600' : '500',
                  boxShadow: addForm.type === 'shared' ? '0 2px 8px rgba(0,0,0,0.05)' : 'none',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
              >
                👥 Umumiy
              </button>
            </div>

            {/* Title Field with Emoji Picker */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{
                fontSize: '12px',
                color: 'var(--text-secondary)',
                fontWeight: '600',
                display: 'block',
                marginBottom: '8px'
              }}>
                Sarlavha
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
                  {addForm.emoji}
                </button>
                <input
                  type="text"
                  placeholder="Balans nomini kiriting..."
                  value={addForm.title}
                  onChange={(e) => setAddForm({...addForm, title: e.target.value})}
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

              {/* Emoji Picker */}
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
                  {emojis.map((emoji) => (
                    <button
                      key={emoji}
                      onClick={() => {
                        setAddForm({...addForm, emoji});
                        setShowEmojiPicker(false);
                      }}
                      style={{
                        background: addForm.emoji === emoji ? 'rgba(10, 132, 255, 0.2)' : 'transparent',
                        border: addForm.emoji === emoji ? '2px solid var(--primary)' : '1px solid var(--border)',
                        borderRadius: '8px',
                        fontSize: '22px',
                        padding: '8px',
                        cursor: 'pointer',
                        transition: 'all 0.1s'
                      }}
                      onMouseOver={(e) => e.target.style.background = 'rgba(10, 132, 255, 0.1)'}
                      onMouseOut={(e) => e.target.style.background = addForm.emoji === emoji ? 'rgba(10, 132, 255, 0.2)' : 'transparent'}
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Amount and Currency */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{
                fontSize: '12px',
                color: 'var(--text-secondary)',
                fontWeight: '600',
                display: 'block',
                marginBottom: '8px'
              }}>
                Miqdor
              </label>
              <div style={{
                display: 'flex',
                gap: '8px'
              }}>
                <input
                  type="number"
                  placeholder="0"
                  value={addForm.amount}
                  onChange={(e) => setAddForm({...addForm, amount: e.target.value})}
                  style={{
                    flex: 1,
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    padding: '12px 16px',
                    borderRadius: '12px',
                    color: 'var(--text-primary)',
                    fontSize: '16px',
                    fontWeight: '600',
                    outline: 'none'
                  }}
                />
                <select
                  value={addForm.currency}
                  onChange={(e) => setAddForm({...addForm, currency: e.target.value})}
                  style={{
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    padding: '12px 12px',
                    borderRadius: '12px',
                    color: 'var(--text-primary)',
                    fontSize: '14px',
                    fontWeight: '600',
                    cursor: 'pointer',
                    outline: 'none',
                    minWidth: '140px'
                  }}
                >
                  <optgroup label="Ommabop">
                    <option value="UZS">🇺🇿 UZS</option>
                    <option value="USD">🇺🇸 USD</option>
                    <option value="RUB">🇷🇺 RUB</option>
                    <option value="KZT">🇰🇿 KZT</option>
                  </optgroup>
                  <optgroup label="Boshqa">
                    <option value="EUR">🇪🇺 EUR</option>
                    <option value="GBP">🇬🇧 GBP</option>
                    <option value="JPY">🇯🇵 JPY</option>
                    <option value="CNY">🇨🇳 CNY</option>
                    <option value="AED">🇦🇪 AED</option>
                    <option value="TRY">🇹🇷 TRY</option>
                  </optgroup>
                </select>
              </div>

              {/* Exchange Rate Info (if not UZS) */}
              {addForm.currency !== 'UZS' && exchangeRates[addForm.currency] && (
                <div style={{
                  marginTop: '10px',
                  padding: '10px 12px',
                  background: 'rgba(10, 132, 255, 0.08)',
                  border: '1px solid rgba(10, 132, 255, 0.2)',
                  borderRadius: '8px',
                  fontSize: '12px',
                  color: 'var(--primary)',
                  fontWeight: '500'
                }}>
                  💱 1 {addForm.currency} = {exchangeRates[addForm.currency].toLocaleString('uz-UZ')} UZS
                  <br/>
                  <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: '400' }}>
                    Markaziy Bank kursi bo'yicha (bugungi kurs)
                  </span>
                </div>
              )}
            </div>

            {/* Color Picker */}
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
                    onClick={() => setAddForm({...addForm, color: c})}
                    style={{
                      width: '44px',
                      height: '44px',
                      borderRadius: '12px',
                      backgroundColor: c,
                      border: addForm.color === c ? '3px solid #FFF' : '2px solid rgba(255,255,255,0.2)',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      boxShadow: addForm.color === c ? `0 0 16px ${c}99` : `0 2px 8px ${c}33`,
                      transition: 'all 0.2s'
                    }}
                  >
                    {addForm.color === c && <Check size={18} color="#000" strokeWidth={3} />}
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
                    value={customColor}
                    onChange={(e) => {
                      setCustomColor(e.target.value);
                      setAddForm({...addForm, color: e.target.value});
                    }}
                    style={{
                      width: '100%',
                      height: '50px',
                      border: 'none',
                      borderRadius: '8px',
                      cursor: 'pointer'
                    }}
                  />
                  <p style={{
                    fontSize: '11px',
                    color: 'var(--text-secondary)',
                    margin: '8px 0 0 0'
                  }}>
                    Rengni tanlang yoki kodni kiriting
                  </p>
                </div>
              )}
            </div>

            {/* Limit Toggle */}
            <div style={{
              background: 'var(--bg)',
              border: '1px solid var(--border)',
              borderRadius: '12px',
              padding: '14px 16px',
              marginBottom: addForm.hasLimit ? '16px' : '16px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <div>
                <p style={{
                  margin: '0 0 4px 0',
                  fontSize: '14px',
                  fontWeight: '600'
                }}>
                  ☑️ Limit o'rnatish
                </p>
                <p style={{
                  margin: 0,
                  fontSize: '11px',
                  color: 'var(--text-secondary)'
                }}>
                  Oylik xarajat limitini belgilang
                </p>
              </div>
              <div
                onClick={() => setAddForm({...addForm, hasLimit: !addForm.hasLimit})}
                style={{
                  width: '54px',
                  height: '32px',
                  borderRadius: '16px',
                  background: addForm.hasLimit ? 'var(--primary)' : 'var(--border)',
                  position: 'relative',
                  cursor: 'pointer',
                  transition: 'all 0.3s'
                }}
              >
                <div style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '50%',
                  background: '#FFF',
                  position: 'absolute',
                  top: '2px',
                  left: addForm.hasLimit ? '24px' : '2px',
                  transition: 'all 0.3s',
                  boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
                }} />
              </div>
            </div>

            {/* Limit Amount Input */}
            {addForm.hasLimit && (
              <div style={{
                display: 'flex',
                gap: '8px',
                marginBottom: '16px'
              }}>
                <input
                  type="number"
                  placeholder="Limit miqdori"
                  value={addForm.limitAmount}
                  onChange={(e) => setAddForm({...addForm, limitAmount: e.target.value})}
                  style={{
                    flex: 1,
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    padding: '12px 16px',
                    borderRadius: '12px',
                    color: 'var(--text-primary)',
                    fontSize: '14px',
                    outline: 'none'
                  }}
                />
                <div style={{
                  padding: '12px 16px',
                  background: 'var(--border)',
                  borderRadius: '12px',
                  color: 'var(--text-secondary)',
                  fontSize: '13px',
                  fontWeight: '600',
                  whiteSpace: 'nowrap'
                }}>
                  {addForm.currency}
                </div>
              </div>
            )}

            {/* Shared Wallet Members */}
            {addForm.type === 'shared' && (
              <div style={{ marginBottom: '16px' }}>
                <label style={{
                  fontSize: '12px',
                  color: 'var(--text-secondary)',
                  fontWeight: '600',
                  display: 'block',
                  marginBottom: '8px'
                }}>
                  A'zolar (Telefon raqami bilan qo'shish)
                </label>
                <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                  <input
                    type="tel"
                    placeholder="+998901234567"
                    value={newMemberPhone}
                    onChange={(e) => setNewMemberPhone(e.target.value)}
                    style={{
                      flex: 1,
                      background: 'var(--bg)',
                      border: '1px solid var(--border)',
                      padding: '12px 16px',
                      borderRadius: '12px',
                      color: 'var(--text-primary)',
                      fontSize: '14px',
                      outline: 'none'
                    }}
                  />
                  <button
                    onClick={() => {
                      if (newMemberPhone && !addForm.members.includes(newMemberPhone)) {
                        setAddForm({ ...addForm, members: [...addForm.members, newMemberPhone] });
                        setNewMemberPhone('');
                      }
                    }}
                    style={{
                      background: 'var(--primary)',
                      color: '#FFF',
                      border: 'none',
                      borderRadius: '12px',
                      padding: '0 16px',
                      fontWeight: '600',
                      cursor: 'pointer'
                    }}
                  >
                    Qo'shish
                  </button>
                </div>
                {addForm.members.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    {addForm.members.map((m, idx) => (
                      <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg)', padding: '8px 12px', borderRadius: '8px' }}>
                        <span style={{ fontSize: '13px' }}>{m}</span>
                        <X size={16} color="var(--danger)" style={{ cursor: 'pointer' }} onClick={() => {
                          setAddForm({...addForm, members: addForm.members.filter(x => x !== m)});
                        }} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

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

            {/* Close Button - Full Width Dark Blue */}
            <button
              onClick={async () => {
                if (!addForm.amount || !addForm.title) {
                  alert('Iltimos, nomi va miqdorni kiriting');
                  return;
                }
                await handleAddBalance();
              }}
              style={{
                width: '100%',
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
              Yopish
            </button>
          </div>
        </div>
      )}

      {/* Add Card Modal */}
      {activeModal === 'card' && (
        <div className="modal-overlay" onClick={() => setActiveModal(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="flex-between" style={{ marginBottom: '24px' }}>
              <h3 style={{ fontSize: '20px', fontWeight: 'bold' }}>Karta qo'shish</h3>
              <button onClick={() => setActiveModal(null)} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)' }}><X size={20} /></button>
            </div>
            
            <div style={{ background: 'linear-gradient(135deg, #1C1C1E, #2C2C2E)', borderRadius: '16px', padding: '24px', marginBottom: '24px', position: 'relative', overflow: 'hidden' }}>
              <CreditCard size={32} color="#FFF" style={{ opacity: 0.5, marginBottom: '24px' }} />
              <p style={{ fontSize: '20px', letterSpacing: '2px', fontFamily: 'monospace', color: '#FFF' }}>
                {cardForm.number || '•••• •••• •••• ••••'}
              </p>
            </div>

            <label style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '8px', display: 'block' }}>Karta raqami</label>
            <input 
              type="text" 
              placeholder="0000 0000 0000 0000" 
              maxLength="19"
              className="input-field"
              value={cardForm.number}
              onChange={e => setCardForm({...cardForm, number: e.target.value})}
              style={{ fontSize: '18px', letterSpacing: '2px', fontFamily: 'monospace', width: '100%', marginBottom: '24px' }}
            />

            <div className="flex-between" style={{ marginBottom: '16px' }}>
              <div>
                <p style={{ fontWeight: '600', fontSize: '15px' }}>Limit o'rnatish</p>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>Oylik xarajatlar uchun chegara</p>
              </div>
              <label className="toggle-switch">
                <input type="checkbox" checked={useLimit} onChange={() => setUseLimit(!useLimit)} />
                <span className="slider"></span>
              </label>
            </div>

            {useLimit && (
              <div style={{ marginBottom: '24px', animation: 'slideDown 0.3s ease' }}>
                <input 
                  type="number" 
                  placeholder="Limit miqdorini kiriting"
                  className="input-field"
                  value={limitAmount}
                  onChange={e => setLimitAmount(e.target.value)}
                  style={{ fontSize: '16px' }}
                />
              </div>
            )}

            <button 
              onClick={handleAddBalance}
              style={{ width: '100%', background: 'var(--primary)', color: '#FFF', border: 'none', padding: '16px', borderRadius: '16px', fontSize: '16px', fontWeight: 'bold', boxShadow: '0 8px 24px var(--primary-glow)' }}
            >
              Yaratish
            </button>
          </div>
        </div>
      )}

      {/* KARTA QO'SHISH MODAL */}
      {isCardModalOpen && (
        <div className="modal-overlay" onClick={() => setIsCardModalOpen(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ paddingBottom: '40px', textAlign: 'center' }}>
            <div style={{ width: '64px', height: '64px', background: 'rgba(48,209,88,0.1)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px auto' }}>
              <ShieldCheck size={32} color="var(--success)" />
            </div>
            <h3 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '12px' }}>Karta ulash</h3>
            <p style={{ fontSize: '15px', color: 'var(--text-secondary)', marginBottom: '24px', lineHeight: '1.5' }}>
              Haqiqiy banking kartangizni ulash orqali SMS xabarlar avtomatik tarzda Somly AI tomonidan tranzaksiya sifatida kiritiladi.
            </p>

            <div style={{ textAlign: 'left', marginBottom: '24px' }}>
              <label style={{ display: 'block', fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '8px', fontWeight: '500' }}>Karta raqami</label>
              <input 
                type="text" 
                placeholder="0000 0000 0000 0000"
                className="input-field"
                style={{ fontSize: '18px', letterSpacing: '2px', fontFamily: 'monospace' }}
              />
            </div>

            <button 
              onClick={() => { setIsCardModalOpen(false); setIsOtpModalOpen(true); }}
              style={{ width: '100%', background: 'var(--primary)', color: '#FFF', border: 'none', padding: '16px', borderRadius: '16px', fontSize: '16px', fontWeight: 'bold', boxShadow: '0 8px 24px var(--primary-glow)' }}
            >
              Davom etish
            </button>
          </div>
        </div>
      )}

      {/* OTP MODAL */}
      {isOtpModalOpen && (
        <div className="modal-overlay" onClick={() => setIsOtpModalOpen(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ paddingBottom: '40px', textAlign: 'center' }}>
            <div style={{ width: '64px', height: '64px', background: 'rgba(10,132,255,0.1)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px auto' }}>
              <Smartphone size={32} color="var(--primary)" />
            </div>
            <h3 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '12px' }}>SMS Kod</h3>
            <p style={{ fontSize: '15px', color: 'var(--text-secondary)', marginBottom: '24px', lineHeight: '1.5' }}>
              Telefon raqamingizga yuborilgan 6 xonali tasdiqlash kodini kiriting.
            </p>

            <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', marginBottom: '32px' }}>
              {[1, 2, 3, 4, 5, 6].map(i => (
                <input 
                  key={i}
                  type="text" 
                  maxLength={1}
                  className="input-field"
                  style={{ width: '45px', height: '55px', textAlign: 'center', fontSize: '24px', fontWeight: 'bold', padding: 0 }}
                />
              ))}
            </div>

            <button 
              onClick={() => { setIsOtpModalOpen(false); alert("Karta muvaffaqiyatli ulandi!"); }}
              style={{ width: '100%', background: 'var(--success)', color: '#FFF', border: 'none', padding: '16px', borderRadius: '16px', fontSize: '16px', fontWeight: 'bold', boxShadow: '0 8px 24px rgba(48,209,88,0.3)' }}
            >
              Tasdiqlash
            </button>
          </div>
        </div>
      )}
      
      {/* Edit Balance Modal */}
      {activeModal === 'edit_balance' && selectedBal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.6)',
          display: 'flex',
          alignItems: 'flex-end',
          zIndex: 1000
        }}
        onClick={() => setActiveModal(null)}
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
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '24px'
            }}>
              <h2 style={{ margin: 0, fontSize: '22px', fontWeight: '700' }}>
                Balansni tahrirlash
              </h2>
              <button
                onClick={() => setActiveModal(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '24px', padding: '4px' }}
              >✕</button>
            </div>

            {/* Title Field with Emoji Picker */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: '600', display: 'block', marginBottom: '8px' }}>
                Sarlavha
              </label>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button
                  onClick={() => setShowEmojiPicker(!showEmojiPicker)}
                  style={{
                    width: '52px', height: '52px', minWidth: '52px', borderRadius: '12px',
                    background: 'var(--bg)', border: '2px solid var(--border)', fontSize: '28px',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer'
                  }}
                >
                  {addForm.emoji}
                </button>
                <input
                  type="text"
                  placeholder="Balans nomini kiriting..."
                  value={addForm.title}
                  onChange={(e) => setAddForm({...addForm, title: e.target.value})}
                  style={{
                    flex: 1, background: 'var(--bg)', border: '1px solid var(--border)',
                    padding: '12px 16px', borderRadius: '12px', color: 'var(--text-primary)', fontSize: '15px', outline: 'none'
                  }}
                />
              </div>
              {showEmojiPicker && (
                <div style={{
                  marginTop: '12px', background: 'var(--bg)', border: '1px solid var(--border)',
                  borderRadius: '12px', padding: '12px', display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)',
                  gap: '6px', maxHeight: '200px', overflowY: 'auto'
                }}>
                  {emojis.map((emoji) => (
                    <button
                      key={emoji}
                      onClick={() => { setAddForm({...addForm, emoji}); setShowEmojiPicker(false); }}
                      style={{
                        background: addForm.emoji === emoji ? 'rgba(10, 132, 255, 0.2)' : 'transparent',
                        border: addForm.emoji === emoji ? '2px solid var(--primary)' : '1px solid var(--border)',
                        borderRadius: '8px', fontSize: '22px', padding: '8px', cursor: 'pointer'
                      }}
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Amount and Currency (Disabled for Edit) */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{
                fontSize: '12px',
                color: 'var(--text-secondary)',
                fontWeight: '600',
                display: 'block',
                marginBottom: '8px'
              }}>
                Miqdor (tahrirlanmaydi)
              </label>
              <div style={{
                display: 'flex',
                gap: '8px'
              }}>
                <input
                  type="number"
                  disabled
                  value={addForm.amount}
                  style={{
                    flex: 1,
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    padding: '12px 16px',
                    borderRadius: '12px',
                    color: 'var(--text-secondary)',
                    fontSize: '16px',
                    fontWeight: '600',
                    outline: 'none',
                    opacity: 0.7
                  }}
                />
                <input
                  type="text"
                  disabled
                  value={addForm.currency}
                  style={{
                    width: '80px',
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    padding: '12px 16px',
                    borderRadius: '12px',
                    color: 'var(--text-secondary)',
                    fontSize: '16px',
                    fontWeight: '600',
                    outline: 'none',
                    opacity: 0.7,
                    textAlign: 'center'
                  }}
                />
              </div>
            </div>

            {/* Color Picker */}
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
                    onClick={() => setAddForm({...addForm, color: c})}
                    style={{
                      width: '44px',
                      height: '44px',
                      borderRadius: '12px',
                      backgroundColor: c,
                      border: addForm.color === c ? '3px solid #FFF' : '2px solid rgba(255,255,255,0.2)',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      boxShadow: addForm.color === c ? `0 0 16px ${c}99` : `0 2px 8px ${c}33`,
                      transition: 'all 0.2s'
                    }}
                  >
                    {addForm.color === c && <Check size={18} color="#000" strokeWidth={3} />}
                  </button>
                ))}
              </div>
            </div>

            {/* Limit Switch */}
            <div style={{ marginBottom: '24px' }}>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '12px 16px',
                background: 'var(--bg)',
                borderRadius: '12px',
                border: '1px solid var(--border)'
              }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '15px', fontWeight: '600' }}>Oylik limit</h4>
                  <p style={{ margin: '4px 0 0', fontSize: '12px', color: 'var(--text-secondary)' }}>
                    Xarajatlarni nazorat qilish uchun
                  </p>
                </div>
                <label className="switch" style={{ position: 'relative', display: 'inline-block', width: '44px', height: '24px' }}>
                  <input 
                    type="checkbox" 
                    checked={addForm.hasLimit}
                    onChange={(e) => setAddForm({...addForm, hasLimit: e.target.checked})}
                    style={{ opacity: 0, width: 0, height: 0 }} 
                  />
                  <span className="slider round" style={{
                    position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0,
                    backgroundColor: addForm.hasLimit ? 'var(--primary)' : 'var(--border)',
                    transition: '.4s', borderRadius: '34px'
                  }}>
                    <span style={{
                      position: 'absolute', content: '""', height: '18px', width: '18px',
                      left: addForm.hasLimit ? '22px' : '3px', bottom: '3px',
                      backgroundColor: 'white', transition: '.4s', borderRadius: '50%'
                    }}></span>
                  </span>
                </label>
              </div>

              {addForm.hasLimit && (
                <div style={{ marginTop: '12px' }}>
                  <input
                    type="number"
                    placeholder="Limit miqdorini kiriting"
                    value={addForm.limitAmount}
                    onChange={(e) => setAddForm({...addForm, limitAmount: e.target.value})}
                    style={{
                      width: '100%',
                      background: 'var(--bg)',
                      border: '1px solid var(--border)',
                      padding: '12px 16px',
                      borderRadius: '12px',
                      color: 'var(--text-primary)',
                      fontSize: '15px',
                      outline: 'none',
                      boxSizing: 'border-box'
                    }}
                  />
                </div>
              )}
            </div>

            {/* Save Button */}
            <button
              onClick={async () => {
                if (!addForm.title) return;
                try {
                  const payload = {
                    title: addForm.title,
                    emoji: addForm.emoji,
                    color: addForm.color,
                    limit: addForm.hasLimit ? parseInt(addForm.limitAmount) : null
                  };
                  
                  await fetchApi(`/balances/${selectedBal.currency}`, {
                    method: 'PUT',
                    body: JSON.stringify(payload)
                  });
                  
                  setActiveModal(null);
                  loadBalances(true);
                } catch(e) {
                  console.error(e);
                  alert("Xatolik yuz berdi");
                }
              }}
              style={{
                width: '100%',
                background: 'var(--primary)',
                border: 'none',
                padding: '16px',
                borderRadius: '16px',
                color: '#fff',
                fontWeight: '700',
                fontSize: '16px',
                cursor: 'pointer',
                boxShadow: '0 4px 12px rgba(10, 132, 255, 0.3)',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                gap: '8px'
              }}
            >
              <Check size={20} />
              Saqlash
            </button>
          </div>
        </div>
      )}


      {/* Transfer Modal */}
      {activeModal === 'transfer' && selectedBal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.6)',
          display: 'flex',
          alignItems: 'flex-end',
          zIndex: 1000
        }}
        onClick={() => setActiveModal('action')}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--card)',
              width: '100%',
              borderRadius: '20px 20px 0 0',
              padding: '20px',
              maxHeight: '85vh',
              overflowY: 'auto'
            }}
          >
            <h2 style={{
              fontSize: '20px',
              fontWeight: '700',
              marginBottom: '24px',
              textAlign: 'center'
            }}>
              Balansdan balansga o'tkazish
            </h2>

            {/* From Balance */}
            <div style={{
              background: 'linear-gradient(135deg, ' + selectedBal.color + ' 0%, #1A1A1C 120%)',
              borderRadius: '16px',
              padding: '16px',
              marginBottom: '20px',
              boxShadow: `0 4px 12px ${selectedBal.color}33`
            }}>
              <p style={{
                fontSize: '12px',
                color: 'rgba(255,255,255,0.7)',
                marginBottom: '8px'
              }}>
                Qayerdan
              </p>
              <p style={{
                fontSize: '18px',
                fontWeight: '700',
                color: '#FFF'
              }}>
                {selectedBal.flag} {selectedBal.title}
              </p>
              <p style={{
                fontSize: '24px',
                fontWeight: '800',
                color: '#FFF',
                marginTop: '8px'
              }}>
                {formatMoney(selectedBal.amount)} {selectedBal.currency}
              </p>
            </div>

            {/* Arrow Down */}
            <div style={{
              textAlign: 'center',
              margin: '16px 0',
              fontSize: '24px',
              color: 'var(--primary)'
            }}>
              ↓
            </div>

            {/* To Balance Selector */}
            <div style={{ marginBottom: '20px' }}>
              <label style={{
                fontSize: '12px',
                color: 'var(--text-secondary)',
                fontWeight: '600',
                display: 'block',
                marginBottom: '8px'
              }}>
                Qayerga
              </label>
              <select
                value={transferForm.toBalanceId}
                onChange={(e) => setTransferForm({ ...transferForm, toBalanceId: e.target.value })}
                style={{
                  width: '100%',
                  background: 'var(--bg)',
                  border: '1px solid var(--border)',
                  padding: '12px 16px',
                  borderRadius: '12px',
                  color: 'var(--text-primary)',
                  fontSize: '14px',
                  boxSizing: 'border-box'
                }}
              >
                <option value="">Balansni tanlang...</option>
                {balances
                  .filter(b => b.id !== selectedBal.id)
                  .map(b => (
                    <option key={b.id} value={b.id}>
                      {b.flag} {b.title} - {formatMoney(b.amount)} {b.currency}
                    </option>
                  ))}
              </select>
            </div>

            {/* Amount Input */}
            <div style={{
              display: 'flex',
              gap: '8px',
              marginBottom: '16px'
            }}>
              <div style={{ flex: 1 }}>
                <label style={{
                  fontSize: '12px',
                  color: 'var(--text-secondary)',
                  fontWeight: '600',
                  display: 'block',
                  marginBottom: '8px'
                }}>
                  Summa
                </label>
                <input
                  type="number"
                  value={transferForm.amount}
                  onChange={(e) => setTransferForm({ ...transferForm, amount: e.target.value })}
                  placeholder="0"
                  style={{
                    width: '100%',
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    padding: '12px 16px',
                    borderRadius: '12px',
                    color: 'var(--text-primary)',
                    fontSize: '14px',
                    boxSizing: 'border-box'
                  }}
                />
              </div>
              <div style={{
                display: 'flex',
                alignItems: 'flex-end',
                paddingBottom: '12px'
              }}>
                <span style={{
                  fontSize: '12px',
                  fontWeight: '600',
                  color: 'var(--text-secondary)',
                  background: 'var(--bg)',
                  padding: '10px 12px',
                  borderRadius: '8px'
                }}>
                  {selectedBal.currency}
                </span>
              </div>
            </div>

            {/* Exchange Rate (if different currencies) */}
            {transferForm.toBalanceId && balances.find(b => b.id === transferForm.toBalanceId)?.currency !== selectedBal.currency && (() => {
              const toCurrency = balances.find(b => b.id === transferForm.toBalanceId)?.currency;
              const rateFrom = selectedBal.currency === 'UZS' ? 1 : (exchangeRates[selectedBal.currency] || 0);
              const rateTo = toCurrency === 'UZS' ? 1 : (exchangeRates[toCurrency] || 0);
              const convertedRate = rateFrom && rateTo ? (rateFrom / rateTo) : 0;
              
              if (!convertedRate) return null; // Hide if no rate

              return (
                <div style={{
                  background: 'rgba(10, 132, 255, 0.1)',
                  border: '1px solid rgba(10, 132, 255, 0.2)',
                  borderRadius: '12px',
                  padding: '12px 16px',
                  marginBottom: '16px'
                }}>
                  <p style={{
                    fontSize: '12px',
                    color: 'var(--primary)',
                    margin: '0 0 4px 0'
                  }}>
                    💱 Valyuta kursi
                  </p>
                  <p style={{
                    fontSize: '13px',
                    color: 'var(--text-primary)',
                    fontWeight: '600',
                    margin: '0'
                  }}>
                    1 {selectedBal.currency} = {convertedRate.toLocaleString('uz-UZ', {maximumFractionDigits: 2})} {toCurrency}
                  </p>
                  <p style={{
                    fontSize: '11px',
                    color: 'var(--text-secondary)',
                    margin: '4px 0 0 0'
                  }}>
                    Markaziy Bank kursi bo'yicha
                  </p>
                </div>
              );
            })()}

            {/* Transfer Button */}
            <button
              onClick={async () => {
                if (!transferForm.toBalanceId || !transferForm.amount) {
                  alert('Iltimos, balans va summani tanlang');
                  return;
                }
                try {
                  const payload = {
                    from_balance_id: selectedBal.id,
                    to_balance_id: transferForm.toBalanceId,
                    amount: parseFloat(transferForm.amount),
                    user_id: window.Telegram?.WebApp?.initDataUnsafe?.user?.id
                  };
                  const response = await fetchApi('/balances/transfer', {
                    method: 'POST',
                    body: JSON.stringify(payload)
                  });
                  if (response && response.success) {
                    alert('✅ O\'tkazish muvaffaqiyatli yakunlandi');
                    setActiveModal(null);
                    loadBalances(true);
                  }
                } catch (err) {
                  alert('❌ O\'tkazishda xato: ' + err.message);
                }
              }}
              style={{
                width: '100%',
                background: 'var(--primary)',
                border: 'none',
                padding: '16px',
                borderRadius: '12px',
                color: '#fff',
                fontWeight: '700',
                fontSize: '16px',
                cursor: 'pointer',
                boxShadow: '0 4px 12px rgba(10, 132, 255, 0.3)'
              }}
            >
              O'tkazish
            </button>
          </div>
        </div>
      )}
      {/* Add Shared Wallet Modal */}
      {activeModal === 'add_shared' && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)', display: 'flex', alignItems: 'flex-end', justifyContent: 'center', zIndex: 1000 }} onClick={() => setActiveModal(null)}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: 'var(--card)', width: '100%', maxWidth: '500px', borderRadius: '24px 24px 0 0', padding: '24px 20px', paddingBottom: 'max(24px, calc(24px + env(safe-area-inset-bottom)))', maxHeight: '85vh', overflowY: 'auto', boxSizing: 'border-box', animation: 'slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)' }}>
            <div style={{ width: '36px', height: '5px', borderRadius: '3px', background: 'var(--border)', margin: '0 auto 16px' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <h2 style={{ margin: 0, fontSize: '20px', fontWeight: '700' }}>Umumiy hamyon yaratish</h2>
              <div onClick={() => setActiveModal(null)} style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'var(--bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
                <X size={18} color="var(--text-secondary)" />
              </div>
            </div>
            <div style={{ marginBottom: '16px' }}>
              <label style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: '600', display: 'block', marginBottom: '8px' }}>Hamyon nomi</label>
              <input 
                className="apple-input"
                type="text" 
                placeholder="Masalan: Oila balansi" 
                value={addForm.title} 
                onChange={(e) => setAddForm({...addForm, title: e.target.value})}
                style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', padding: '12px 16px', borderRadius: '12px', color: 'var(--text-primary)', fontSize: '15px', boxSizing: 'border-box', outline: 'none' }}
              />
            </div>
            <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <label style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: '600', display: 'block', marginBottom: '8px' }}>Boshlang'ich summa</label>
                <input 
                  className="apple-input"
                  type="number" 
                  placeholder="0" 
                  value={addForm.amount} 
                  onChange={(e) => setAddForm({...addForm, amount: e.target.value})}
                  style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', padding: '12px 16px', borderRadius: '12px', color: 'var(--text-primary)', fontSize: '15px', boxSizing: 'border-box', outline: 'none' }}
                />
              </div>
              <div style={{ width: '100px', flexShrink: 0 }}>
                <label style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: '600', display: 'block', marginBottom: '8px' }}>Valyuta</label>
                <select 
                  className="apple-input"
                  value={addForm.currency} 
                  onChange={(e) => setAddForm({...addForm, currency: e.target.value})}
                  style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', padding: '12px 8px', borderRadius: '12px', color: 'var(--text-primary)', fontSize: '14px', boxSizing: 'border-box', outline: 'none' }}
                >
                  <option value="UZS">UZS</option>
                  <option value="USD">USD</option>
                </select>
              </div>
            </div>
            <div style={{ marginBottom: '24px' }}>
              <label style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: '600', display: 'block', marginBottom: '8px' }}>A'zolar (Telefon raqami)</label>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                <input 
                  className="apple-input"
                  type="tel" 
                  placeholder="+998901234567" 
                  value={newMemberPhone} 
                  onChange={(e) => setNewMemberPhone(e.target.value)}
                  style={{ flex: 1, minWidth: 0, background: 'var(--bg)', border: '1px solid var(--border)', padding: '12px 16px', borderRadius: '12px', color: 'var(--text-primary)', fontSize: '14px', boxSizing: 'border-box', outline: 'none' }}
                />
                <button 
                  className="quick-action-btn"
                  onClick={() => {
                    if (newMemberPhone && !addForm.members.includes(newMemberPhone)) {
                      setAddForm({...addForm, members: [...addForm.members, newMemberPhone]});
                      setNewMemberPhone('');
                    }
                  }}
                  style={{ background: '#8B5CF6', color: '#FFF', border: 'none', borderRadius: '12px', padding: '0 16px', fontWeight: 'bold', cursor: 'pointer', flexShrink: 0 }}
                >
                  +
                </button>
              </div>
              {addForm.members.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {addForm.members.map((m, idx) => (
                    <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--bg)', padding: '8px 12px', borderRadius: '8px' }}>
                      <span style={{ fontSize: '13px' }}>{m}</span>
                      <X size={16} color="var(--danger)" style={{ cursor: 'pointer', flexShrink: 0 }} onClick={() => setAddForm({...addForm, members: addForm.members.filter(x => x !== m)})} />
                    </div>
                  ))}
                </div>
              )}
            </div>
            <button 
              className="apple-submit-btn"
              onClick={async () => {
                try {
                  const res = await fetchApi('/shared_wallets', { 
                    method: 'POST', 
                    body: JSON.stringify({ 
                      name: addForm.title, 
                      amount: addForm.amount, 
                      currency: addForm.currency, 
                      color: '#8B5CF6',
                      user_id: window.Telegram?.WebApp?.initDataUnsafe?.user?.id
                    }) 
                  });
                  if (res && res.success && res.id) {
                    for (const m of addForm.members) {
                      await fetchApi(`/shared_wallets/${res.id}/invite`, {
                        method: 'POST',
                        body: JSON.stringify({
                          contact: m,
                          role: 'can_edit',
                          user_id: window.Telegram?.WebApp?.initDataUnsafe?.user?.id
                        })
                      });
                    }
                  }
                  setActiveModal(null);
                  loadBalances();
                } catch(e) {
                  alert(e.message);
                }
              }}
            >
              Yaratish
            </button>
          </div>
        </div>
      )}

      {/* Shared Wallet Action Modal */}
      {activeModal === 'shared_action' && selectedBal && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'flex-end', zIndex: 1000 }} onClick={() => setActiveModal(null)}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: 'var(--card)', width: '100%', borderRadius: '24px 24px 0 0', padding: '24px 20px', maxHeight: '80vh', overflowY: 'auto' }}>
            <h2 style={{ margin: '0 0 4px 0', fontSize: '18px', fontWeight: '700' }}>{selectedBal.name}</h2>
            <p style={{ margin: '0 0 20px 0', fontSize: '13px', color: 'var(--text-secondary)' }}>Umumiy hamyonni boshqarish</p>
            
            <div style={{ background: 'var(--bg)', borderRadius: '16px', padding: '16px', marginBottom: '20px' }}>
              <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>A'zo qo'shish</p>
              <div style={{ display: 'flex', gap: '8px' }}>
                <input 
                  type="text" 
                  placeholder="+998... yoki @username" 
                  value={inviteForm.contact}
                  onChange={(e) => setInviteForm({...inviteForm, contact: e.target.value})}
                  style={{ flex: 1, background: 'var(--card)', border: '1px solid var(--border)', padding: '10px 12px', borderRadius: '10px', color: 'var(--text-primary)', fontSize: '14px' }}
                />
                <button 
                  onClick={async () => {
                    if (!inviteForm.contact) return;
                    try {
                      await fetchApi(`/shared_wallets/${selectedBal.id}/invite`, { method: 'POST', body: JSON.stringify({ contact: inviteForm.contact, role: 'member' }) });
                      alert("Taklif yuborildi!");
                      setInviteForm({ contact: '', role: 'member' });
                    } catch (e) { alert(e.message); }
                  }}
                  style={{ background: 'var(--primary)', border: 'none', borderRadius: '10px', color: '#fff', padding: '0 16px', fontWeight: 600 }}
                >
                  Qo'shish
                </button>
              </div>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '12px' }}>A'zolar ro'yxati</p>
              {selectedBal.members.map(m => (
                <div key={m.user_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '14px' }}>👤</div>
                    <div>
                      <p style={{ margin: 0, fontSize: '14px', fontWeight: 600 }}>{m.name}</p>
                      <p style={{ margin: 0, fontSize: '11px', color: 'var(--text-secondary)' }}>{m.role === 'owner' ? 'Ega' : 'A\'zo'}</p>
                    </div>
                  </div>
                  {selectedBal.owner_id === window.Telegram?.WebApp?.initDataUnsafe?.user?.id && m.role !== 'owner' && (
                    <button 
                      onClick={async () => {
                        await fetchApi(`/shared_wallets/${selectedBal.id}/members/${m.user_id}`, { method: 'DELETE' });
                        setActiveModal(null);
                        loadBalances();
                      }}
                      style={{ background: 'none', border: 'none', color: 'var(--danger)', fontSize: '12px' }}
                    >
                      O'chirish
                    </button>
                  )}
                </div>
              ))}
            </div>

            {selectedBal.owner_id === window.Telegram?.WebApp?.initDataUnsafe?.user?.id && (
              <button 
                onClick={async () => {
                  if (confirm("Rostdan ham bu umumiy hamyonni o'chirmoqchimisiz?")) {
                    try {
                      await fetchApi(`/shared_wallets/${selectedBal.id}`, { method: 'DELETE' });
                      setActiveModal(null);
                      loadBalances();
                    } catch (e) {
                      alert(e.message);
                    }
                  }
                }}
                style={{ width: '100%', padding: '14px', background: 'rgba(255, 69, 58, 0.1)', border: '1px solid rgba(255, 69, 58, 0.3)', borderRadius: '12px', color: 'var(--danger)', fontWeight: '600', marginBottom: '12px' }}
              >
                Hamyonni o'chirish
              </button>
            )}
            <button onClick={() => setActiveModal(null)} style={{ width: '100%', padding: '14px', background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: '12px', color: 'var(--text-primary)', fontWeight: '600' }}>Yopish</button>
          </div>
        </div>
      )}
    </div>
  );
};

export default BalancesPage;
