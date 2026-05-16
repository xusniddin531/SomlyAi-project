import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Plus, Minus, Handshake, ArrowRightLeft, X, ScanLine } from 'lucide-react';
import { fetchApi } from '../utils/api';
import QrScanner from '../pages/QrScanner';

const QuickActions = ({ balances, onSuccess }) => {
  const [activeModal, setActiveModal] = useState(null); // 'kirim', 'chiqim', 'qarz', 'transfer'
  const [showQrScanner, setShowQrScanner] = useState(false);
  const [form, setForm] = useState({ amount: '', category: '', balanceId: '', note: '', person: '', dueDate: '', toBalanceId: '', currency: 'UZS', direction: 'berdim' });
  const [amountError, setAmountError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (activeModal && balances?.length > 0) {
      setForm(prev => ({
        ...prev,
        balanceId: balances[0].currency,
        toBalanceId: balances.length > 1 ? balances[1].currency : balances[0].currency,
        currency: balances[0].currency
      }));
    }
  }, [activeModal, balances]);

  const handleAmountChange = (e) => {
    let rawVal = e.target.value.replace(/\s+/g, '');
    if (rawVal === '') {
      setForm({ ...form, amount: '' });
      setAmountError('');
      return;
    }
    if (!/^\d*$/.test(rawVal)) return;
    
    if (rawVal.length > 1 && rawVal.startsWith('0')) {
      rawVal = rawVal.replace(/^0+/, '');
    }

    const formattedVal = rawVal.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    setForm({ ...form, amount: formattedVal });

    const num = parseFloat(rawVal);
    if (num < 0) setAmountError("Manfiy son mumkin emas");
    else if (num === 0) setAmountError("0 dan katta bo'lishi kerak");
    else setAmountError('');
  };

  const getUserId = () => window.Telegram?.WebApp?.initDataUnsafe?.user?.id || 0;

  const handleSubmit = async () => {
    if (!form.amount || amountError) return;
    setLoading(true);
    try {
      const rawAmount = parseFloat(form.amount.replace(/\s+/g, ''));
      let payload = { user_id: getUserId(), amount: rawAmount, description: form.note || '' };
      let endpoint = '';
      
      const bal = balances.find(b => b.currency === form.balanceId);
      if (bal) {
        payload.currency = bal.currency;
      }

      if (activeModal === 'kirim' || activeModal === 'chiqim') {
        endpoint = '/transactions';
        payload.type = activeModal;
        payload.category = form.category || (activeModal === 'kirim' ? 'Daromad' : 'Boshqa xarajatlar');
        payload.date = new Date().toISOString().split('T')[0];
        payload.affects_balance = true;
      } else if (activeModal === 'qarz') {
        endpoint = '/debts';
        if (!form.person) { alert('Shaxs ismini kiriting'); setLoading(false); return; }
        payload = {
            user_id: getUserId(),
            direction: form.direction,
            amount: rawAmount,
            currency: form.currency,
            person: form.person,
            due_date: form.dueDate || null,
            description: form.note || '',
            wallet_id: payload.wallet_id
        };
      } else if (activeModal === 'transfer') {
        if (form.balanceId === form.toBalanceId) {
          alert('Bir xil balansga o\'tkazish mumkin emas!');
          setLoading(false);
          return;
        }
        endpoint = '/balances/transfer';
        payload = {
            user_id: getUserId(),
            from_balance_id: form.balanceId,
            to_balance_id: form.toBalanceId,
            amount: rawAmount
        };
      }

      await fetchApi(endpoint, { method: 'POST', body: JSON.stringify(payload) });
      setActiveModal(null);
      setForm({ amount: '', category: '', balanceId: '', note: '', person: '', dueDate: '', toBalanceId: '', currency: 'UZS', direction: 'berdim' });
      if (onSuccess) onSuccess();
    } catch (e) {
      alert(e.message);
    } finally {
      setLoading(false);
    }
  };

  /* ══ Shared input style ══ */
  const inputStyle = {
    width: '100%',
    background: 'var(--bg)',
    border: '1px solid var(--border)',
    padding: '14px',
    borderRadius: '12px',
    color: 'var(--text-primary)',
    fontSize: '16px',
    boxSizing: 'border-box',
  };

  const selectStyle = {
    ...inputStyle,
    appearance: 'none',
    WebkitAppearance: 'none',
    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238E8E93' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
    backgroundRepeat: 'no-repeat',
    backgroundPosition: 'right 12px center',
    paddingRight: '36px',
  };

  const labelStyle = {
    fontSize: '13px',
    color: 'var(--text-secondary)',
    marginBottom: '8px',
    display: 'block',
    fontWeight: '500',
  };

  const fieldGroup = {
    marginBottom: '16px',
  };

  return (
    <div style={{ marginTop: '24px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px' }}>
        <button className="quick-action-btn" onClick={() => setActiveModal('kirim')} style={{ background: 'var(--card)', border: '1px solid rgba(48, 209, 88, 0.3)', padding: '12px 4px', borderRadius: 'var(--radius-lg)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#32D74B', boxShadow: '0 4px 12px rgba(48, 209, 88, 0.1)' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '20px', background: 'var(--gradient-success)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 12px rgba(48, 209, 88, 0.3)' }}><Plus size={22} /></div>
          <span style={{ fontSize: '11px', fontWeight: '700' }}>Kirim</span>
        </button>
        <button className="quick-action-btn" onClick={() => setActiveModal('chiqim')} style={{ background: 'var(--card)', border: '1px solid rgba(255, 69, 58, 0.3)', padding: '12px 4px', borderRadius: 'var(--radius-lg)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#FF453A', boxShadow: '0 4px 12px rgba(255, 69, 58, 0.1)' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '20px', background: 'var(--gradient-danger)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 12px rgba(255, 69, 58, 0.3)' }}><Minus size={22} /></div>
          <span style={{ fontSize: '11px', fontWeight: '700' }}>Chiqim</span>
        </button>
        <button className="quick-action-btn" onClick={() => setActiveModal('qarz')} style={{ background: 'var(--card)', border: '1px solid rgba(255, 159, 10, 0.3)', padding: '12px 4px', borderRadius: 'var(--radius-lg)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#FF9F0A', boxShadow: '0 4px 12px rgba(255, 159, 10, 0.1)' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '20px', background: 'var(--gradient-orange)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 12px rgba(255, 159, 10, 0.3)' }}><Handshake size={20} /></div>
          <span style={{ fontSize: '11px', fontWeight: '700' }}>Qarz</span>
        </button>
        <button className="quick-action-btn" onClick={() => setActiveModal('transfer')} style={{ background: 'var(--card)', border: '1px solid rgba(10, 132, 255, 0.3)', padding: '12px 4px', borderRadius: 'var(--radius-lg)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#0A84FF', boxShadow: '0 4px 12px rgba(10, 132, 255, 0.1)' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '20px', background: 'var(--gradient-primary)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 12px rgba(10, 132, 255, 0.3)' }}><ArrowRightLeft size={20} /></div>
          <span style={{ fontSize: '11px', fontWeight: '700' }}>O'tkazma</span>
        </button>
        <button className="quick-action-btn" onClick={() => setShowQrScanner(true)} style={{ background: 'var(--card)', border: '1px solid rgba(191, 90, 242, 0.3)', padding: '12px 4px', borderRadius: 'var(--radius-lg)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#BF5AF2', boxShadow: '0 4px 12px rgba(191, 90, 242, 0.1)' }}>
          <div style={{ width: '40px', height: '40px', borderRadius: '20px', background: 'var(--gradient-purple)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 12px rgba(191, 90, 242, 0.3)' }}><ScanLine size={20} /></div>
          <span style={{ fontSize: '11px', fontWeight: '700' }}>Chek</span>
        </button>
      </div>

      {showQrScanner && (
        <QrScanner
          onClose={() => setShowQrScanner(false)}
          onSuccess={() => { setShowQrScanner(false); if (onSuccess) onSuccess(); }}
        />
      )}

      {activeModal && createPortal(
        <div
          onClick={() => setActiveModal(null)}
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.5)',
            backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
            zIndex: 9999,
            display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              background: 'var(--card-solid)',
              borderRadius: '24px 24px 0 0',
              padding: '24px 20px',
              paddingBottom: 'max(24px, calc(24px + env(safe-area-inset-bottom)))',
              width: '100%',
              maxWidth: '500px',
              maxHeight: '85vh',
              overflowY: 'auto',
              boxSizing: 'border-box',
              animation: 'slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
            }}
          >
            {/* Handle bar */}
            <div style={{ width: '36px', height: '5px', borderRadius: '3px', background: 'var(--border-solid)', margin: '0 auto 16px' }} />

            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: '700', margin: 0, color: 'var(--text-primary)' }}>
                {activeModal === 'kirim' ? '📥 Yangi kirim' : activeModal === 'chiqim' ? '📤 Yangi chiqim' : activeModal === 'qarz' ? '🤝 Qarz kiritish' : '🔄 O\'tkazma'}
              </h2>
              <div
                onClick={() => setActiveModal(null)}
                style={{
                  width: '32px', height: '32px', borderRadius: '50%',
                  background: 'var(--bg)', display: 'flex', alignItems: 'center',
                  justifyContent: 'center', cursor: 'pointer',
                }}
              >
                <X size={18} color="var(--text-secondary)" />
              </div>
            </div>

            {/* ═══ Qarz direction toggle ═══ */}
            {activeModal === 'qarz' && (
              <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', background: 'var(--bg)', padding: '4px', borderRadius: '12px' }}>
                <button className="quick-action-btn" onClick={() => setForm({...form, direction: 'berdim'})} style={{
                  flex: 1, padding: '10px', borderRadius: '8px', border: 'none', cursor: 'pointer',
                  background: form.direction === 'berdim' ? 'var(--card-solid)' : 'transparent',
                  color: form.direction === 'berdim' ? 'var(--text-primary)' : 'var(--text-secondary)',
                  fontWeight: form.direction === 'berdim' ? '600' : '500',
                  boxShadow: form.direction === 'berdim' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                }}>📤 Berdim</button>
                <button className="quick-action-btn" onClick={() => setForm({...form, direction: 'oldim'})} style={{
                  flex: 1, padding: '10px', borderRadius: '8px', border: 'none', cursor: 'pointer',
                  background: form.direction === 'oldim' ? 'var(--card-solid)' : 'transparent',
                  color: form.direction === 'oldim' ? 'var(--text-primary)' : 'var(--text-secondary)',
                  fontWeight: form.direction === 'oldim' ? '600' : '500',
                  boxShadow: form.direction === 'oldim' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                }}>📥 Oldim</button>
              </div>
            )}

            {/* ═══ Person (qarz only) ═══ */}
            {activeModal === 'qarz' && (
              <div style={fieldGroup}>
                <label style={labelStyle}>Shaxs</label>
                <input type="text" placeholder="Ism kiriting" value={form.person}
                  className="apple-input"
                  onChange={e => setForm({...form, person: e.target.value})}
                  style={inputStyle}
                />
              </div>
            )}

            {/* ═══ Amount ═══ */}
            <div style={fieldGroup}>
              <label style={labelStyle}>Summa</label>
              <div style={{ display: 'flex', gap: '8px' }}>
                <input type="tel" placeholder="0" value={form.amount}
                  className="apple-input"
                  onChange={handleAmountChange}
                  style={{
                    ...inputStyle,
                    flex: 1,
                    fontWeight: 'bold',
                    borderColor: amountError ? 'var(--danger)' : 'var(--border)',
                  }}
                />
                {activeModal === 'qarz' && (
                  <select value={form.currency} onChange={e => setForm({...form, currency: e.target.value})}
                    className="apple-input"
                    style={{ ...selectStyle, flex: '0 0 90px', width: '90px' }}>
                    <option value="UZS">UZS</option>
                    <option value="USD">USD</option>
                  </select>
                )}
              </div>
              {amountError && <p style={{ color: 'var(--danger)', fontSize: '12px', marginTop: '6px', margin: '6px 0 0 0' }}>{amountError}</p>}
            </div>

            {/* ═══ Balance selector (kirim/chiqim/transfer) ═══ */}
            {activeModal !== 'qarz' && (
              <div style={fieldGroup}>
                <div style={{ display: 'flex', flexDirection: activeModal === 'transfer' ? 'column' : 'row', gap: '12px' }}>
                  <div style={{ flex: 1 }}>
                    <label style={labelStyle}>{activeModal === 'transfer' ? 'Dan (Balans)' : 'Balans'}</label>
                    <select value={form.balanceId} onChange={e => setForm({...form, balanceId: e.target.value})}
                      className="apple-input"
                      style={selectStyle}>
                      {balances?.map(b => <option key={b.currency} value={b.currency}>{b.title} ({b.currency})</option>)}
                    </select>
                  </div>
                  {activeModal === 'transfer' && (
                    <div style={{ flex: 1 }}>
                      <label style={labelStyle}>Ga (Balans)</label>
                      <select value={form.toBalanceId} onChange={e => setForm({...form, toBalanceId: e.target.value})}
                        className="apple-input"
                        style={selectStyle}>
                        {balances?.map(b => <option key={b.currency} value={b.currency}>{b.title} ({b.currency})</option>)}
                      </select>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ═══ Category (kirim/chiqim only) ═══ */}
            {(activeModal === 'kirim' || activeModal === 'chiqim') && (
              <div style={fieldGroup}>
                <label style={labelStyle}>Kategoriya</label>
                <input type="text" placeholder="Masalan: Oziq-ovqat" value={form.category}
                  className="apple-input"
                  onChange={e => setForm({...form, category: e.target.value})}
                  style={inputStyle}
                />
              </div>
            )}

            {/* ═══ Due date (qarz only) ═══ */}
            {activeModal === 'qarz' && (
              <div style={fieldGroup}>
                <label style={labelStyle}>Muddat (ixtiyoriy)</label>
                <input type="date" value={form.dueDate}
                  className="apple-input"
                  onChange={e => setForm({...form, dueDate: e.target.value})}
                  style={inputStyle}
                />
              </div>
            )}

            {/* ═══ Note ═══ */}
            {activeModal !== 'transfer' && (
              <div style={{ marginBottom: '24px' }}>
                <label style={labelStyle}>Izoh (ixtiyoriy)</label>
                <input type="text" placeholder="Qo'shimcha ma'lumot" value={form.note}
                  className="apple-input"
                  onChange={e => setForm({...form, note: e.target.value})}
                  style={inputStyle}
                />
              </div>
            )}

            {/* ═══ Submit ═══ */}
            <button className="apple-submit-btn" onClick={handleSubmit} disabled={loading || !form.amount || !!amountError}>
              {loading ? 'Saqlanmoqda...' : 'Saqlash'}
            </button>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
};

export default QuickActions;
