import React, { useState, useEffect } from 'react';
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
      setForm(prev => ({ ...prev, balanceId: balances[0].id, toBalanceId: balances.length > 1 ? balances[1].id : balances[0].id, currency: balances[0].currency }));
    }
  }, [activeModal, balances]);

  const handleAmountChange = (e) => {
    const val = e.target.value;
    setForm({ ...form, amount: val });
    if (val === '') {
      setAmountError('');
      return;
    }
    const num = parseFloat(val);
    if (num < 0) setAmountError("Manfiy son mumkin emas");
    else if (num === 0) setAmountError("0 dan katta bo'lishi kerak");
    else setAmountError('');
  };

  const getUserId = () => window.Telegram?.WebApp?.initDataUnsafe?.user?.id || 0;

  const handleSubmit = async () => {
    if (!form.amount || amountError) return;
    setLoading(true);
    try {
      let payload = { user_id: getUserId(), amount: parseFloat(form.amount), description: form.note || '' };
      let endpoint = '';
      
      const bal = balances.find(b => b.id === form.balanceId);
      if (bal) {
        payload.currency = bal.currency;
        if (bal.owner_id) {
            payload.wallet_id = bal.id;
        }
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
            amount: parseFloat(form.amount),
            currency: form.currency,
            person: form.person,
            due_date: form.dueDate || null,
            description: form.note || '',
            wallet_id: payload.wallet_id
        };
      } else if (activeModal === 'transfer') {
        endpoint = '/balances/transfer';
        payload = {
            user_id: getUserId(),
            from_balance_id: form.balanceId,
            to_balance_id: form.toBalanceId,
            amount: parseFloat(form.amount)
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

  return (
    <div style={{ marginTop: '24px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px' }}>
        <button onClick={() => setActiveModal('kirim')} style={{ background: 'rgba(48, 209, 88, 0.1)', border: '1px solid rgba(48, 209, 88, 0.2)', padding: '12px 4px', borderRadius: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#30D158' }}>
          <div style={{ width: '36px', height: '36px', borderRadius: '18px', background: '#30D158', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Plus size={20} /></div>
          <span style={{ fontSize: '11px', fontWeight: '600' }}>Kirim</span>
        </button>
        <button onClick={() => setActiveModal('chiqim')} style={{ background: 'rgba(255, 69, 58, 0.1)', border: '1px solid rgba(255, 69, 58, 0.2)', padding: '12px 4px', borderRadius: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#FF453A' }}>
          <div style={{ width: '36px', height: '36px', borderRadius: '18px', background: '#FF453A', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Minus size={20} /></div>
          <span style={{ fontSize: '11px', fontWeight: '600' }}>Chiqim</span>
        </button>
        <button onClick={() => setActiveModal('qarz')} style={{ background: 'rgba(255, 159, 10, 0.1)', border: '1px solid rgba(255, 159, 10, 0.2)', padding: '12px 4px', borderRadius: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#FF9F0A' }}>
          <div style={{ width: '36px', height: '36px', borderRadius: '18px', background: '#FF9F0A', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Handshake size={20} /></div>
          <span style={{ fontSize: '11px', fontWeight: '600' }}>Qarz</span>
        </button>
        <button onClick={() => setActiveModal('transfer')} style={{ background: 'rgba(10, 132, 255, 0.1)', border: '1px solid rgba(10, 132, 255, 0.2)', padding: '12px 4px', borderRadius: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#0A84FF' }}>
          <div style={{ width: '36px', height: '36px', borderRadius: '18px', background: '#0A84FF', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><ArrowRightLeft size={20} /></div>
          <span style={{ fontSize: '11px', fontWeight: '600' }}>O'tkazma</span>
        </button>
        <button onClick={() => setShowQrScanner(true)} style={{ background: 'rgba(175, 82, 222, 0.1)', border: '1px solid rgba(175, 82, 222, 0.2)', padding: '12px 4px', borderRadius: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', cursor: 'pointer', color: '#AF52DE' }}>
          <div style={{ width: '36px', height: '36px', borderRadius: '18px', background: '#AF52DE', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><ScanLine size={20} /></div>
          <span style={{ fontSize: '11px', fontWeight: '600' }}>Chek</span>
        </button>
      </div>

      {showQrScanner && (
        <QrScanner
          onClose={() => setShowQrScanner(false)}
          onSuccess={() => { setShowQrScanner(false); if (onSuccess) onSuccess(); }}
        />
      )}

      {activeModal && (
        <div className="modal-overlay" onClick={() => setActiveModal(null)} style={{ zIndex: 1000, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ background: 'var(--card)', borderRadius: '24px 24px 0 0', padding: '24px 20px', position: 'absolute', bottom: 0, width: '100%', left: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <h2 style={{ fontSize: '20px', fontWeight: '700', margin: 0 }}>
                {activeModal === 'kirim' ? 'Yangi kirim' : activeModal === 'chiqim' ? 'Yangi chiqim' : activeModal === 'qarz' ? 'Qarz kiritish' : 'O\'tkazma'}
              </h2>
              <X size={24} color="var(--text-secondary)" onClick={() => setActiveModal(null)} style={{ cursor: 'pointer' }} />
            </div>

            {activeModal === 'qarz' && (
              <div style={{ display: 'flex', gap: '8px', marginBottom: '16px', background: 'var(--bg)', padding: '4px', borderRadius: '12px' }}>
                <button onClick={() => setForm({...form, direction: 'berdim'})} style={{ flex: 1, padding: '10px', borderRadius: '8px', border: 'none', background: form.direction === 'berdim' ? 'var(--card)' : 'transparent', color: form.direction === 'berdim' ? '#fff' : 'var(--text-secondary)', fontWeight: form.direction === 'berdim' ? '600' : '500' }}>📤 Berdim</button>
                <button onClick={() => setForm({...form, direction: 'oldim'})} style={{ flex: 1, padding: '10px', borderRadius: '8px', border: 'none', background: form.direction === 'oldim' ? 'var(--card)' : 'transparent', color: form.direction === 'oldim' ? '#fff' : 'var(--text-secondary)', fontWeight: form.direction === 'oldim' ? '600' : '500' }}>📥 Oldim</button>
              </div>
            )}

            {activeModal === 'qarz' && (
              <div style={{ marginBottom: '16px' }}>
                <label style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', display: 'block' }}>Shaxs</label>
                <input type="text" placeholder="Ism kiriting" value={form.person} onChange={e => setForm({...form, person: e.target.value})} style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', padding: '14px', borderRadius: '12px', color: '#fff' }} />
              </div>
            )}

            <div style={{ marginBottom: '16px' }}>
              <label style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', display: 'block' }}>Summa</label>
              <div style={{ display: 'flex', gap: '8px' }}>
                <input type="number" placeholder="0" value={form.amount} onChange={handleAmountChange} style={{ flex: 1, background: 'var(--bg)', border: `1px solid ${amountError ? 'var(--danger)' : 'var(--border)'}`, padding: '14px', borderRadius: '12px', color: '#fff', fontSize: '16px', fontWeight: 'bold' }} />
                {activeModal === 'qarz' ? (
                  <select value={form.currency} onChange={e => setForm({...form, currency: e.target.value})} style={{ background: 'var(--bg)', border: '1px solid var(--border)', padding: '14px', borderRadius: '12px', color: '#fff' }}>
                    <option value="UZS">UZS</option>
                    <option value="USD">USD</option>
                  </select>
                ) : null}
              </div>
              {amountError && <p style={{ color: 'var(--danger)', fontSize: '12px', marginTop: '4px', margin: 0 }}>{amountError}</p>}
            </div>

            {activeModal !== 'qarz' && (
              <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', display: 'block' }}>Dan (Balans)</label>
                  <select value={form.balanceId} onChange={e => setForm({...form, balanceId: e.target.value})} style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', padding: '14px', borderRadius: '12px', color: '#fff' }}>
                    {balances?.map(b => <option key={b.id} value={b.id}>{b.title} ({b.currency})</option>)}
                  </select>
                </div>
                {activeModal === 'transfer' && (
                  <div style={{ flex: 1 }}>
                    <label style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', display: 'block' }}>Ga (Balans)</label>
                    <select value={form.toBalanceId} onChange={e => setForm({...form, toBalanceId: e.target.value})} style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', padding: '14px', borderRadius: '12px', color: '#fff' }}>
                      {balances?.map(b => <option key={b.id} value={b.id}>{b.title} ({b.currency})</option>)}
                    </select>
                  </div>
                )}
              </div>
            )}

            {(activeModal === 'kirim' || activeModal === 'chiqim') && (
              <div style={{ marginBottom: '16px' }}>
                <label style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', display: 'block' }}>Kategoriya</label>
                <input type="text" placeholder="Masalan: Oziq-ovqat" value={form.category} onChange={e => setForm({...form, category: e.target.value})} style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', padding: '14px', borderRadius: '12px', color: '#fff' }} />
              </div>
            )}

            {activeModal === 'qarz' && (
              <div style={{ marginBottom: '16px' }}>
                <label style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', display: 'block' }}>Muddat (ixtiyoriy)</label>
                <input type="date" value={form.dueDate} onChange={e => setForm({...form, dueDate: e.target.value})} style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', padding: '14px', borderRadius: '12px', color: '#fff' }} />
              </div>
            )}

            {activeModal !== 'transfer' && (
              <div style={{ marginBottom: '24px' }}>
                <label style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', display: 'block' }}>Izoh (ixtiyoriy)</label>
                <input type="text" placeholder="Qo'shimcha ma'lumot" value={form.note} onChange={e => setForm({...form, note: e.target.value})} style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border)', padding: '14px', borderRadius: '12px', color: '#fff' }} />
              </div>
            )}

            <button onClick={handleSubmit} disabled={loading || !form.amount || !!amountError} style={{ width: '100%', padding: '16px', background: 'var(--primary)', color: '#fff', border: 'none', borderRadius: '16px', fontSize: '16px', fontWeight: 'bold', cursor: 'pointer', opacity: (loading || !form.amount || !!amountError) ? 0.5 : 1 }}>
              {loading ? 'Saqlanmoqda...' : 'Saqlash'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default QuickActions;
