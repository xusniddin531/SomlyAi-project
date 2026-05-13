import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Plus, ArrowUpRight, ArrowDownRight, Handshake, ChevronRight, Calendar, X, RefreshCw, User, Eye, EyeOff } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { fetchApi } from '../utils/api';
import { EmptyState, ErrorState, SkeletonPage } from '../components/StateViews';
import QuickActions from '../components/QuickActions';
import SmartWidgets from '../components/SmartWidgets';
import TransactionModal from '../components/TransactionModal';

/* ─── AnimatedNumber: fade-out old → fade-in new with green dot ─── */
const AnimatedNumber = ({ value, suffix = '', style = {} }) => {
  const [display, setDisplay] = useState(value);
  const [animClass, setAnimClass] = useState('');
  const [showDot, setShowDot] = useState(false);
  const prevRef = useRef(value);
  const dotTimer = useRef(null);

  useEffect(() => {
    if (prevRef.current === value) return;
    prevRef.current = value;

    // Phase 1: exit old value
    setAnimClass('number-exit');
    const t1 = setTimeout(() => {
      setDisplay(value);
      setAnimClass('number-enter');
      setShowDot(true);
    }, 200);

    // Phase 2: clear animation class
    const t2 = setTimeout(() => setAnimClass(''), 450);

    // Phase 3: hide dot after 0.5s
    dotTimer.current = setTimeout(() => setShowDot(false), 700);

    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(dotTimer.current); };
  }, [value]);

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', ...style }}>
      <span className={animClass}>{display.toLocaleString()}</span>
      {suffix && <span>{suffix}</span>}
      {showDot && <span className="update-dot" key={Date.now()} />}
    </span>
  );
};

const DashboardPage = ({ initData }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeCurrency, setActiveCurrency] = useState('UZS');
  const [activeStatTab, setActiveStatTab] = useState('Hammasi');
  const [activeStatCurrency, setActiveStatCurrency] = useState('UZS');
  const [isActionModalOpen, setIsActionModalOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [balanceHidden, setBalanceHidden] = useState(false);
  const [error, setError] = useState(false);
  const navigate = useNavigate();
  const { t } = useTranslation();

  // Extract user info
  const userName = window.Telegram?.WebApp?.initDataUnsafe?.user?.first_name || 'Foydalanuvchi';
  const initials = userName.substring(0, 2).toUpperCase();

  const loadData = async (isBackground = false) => {
    if (!isBackground) setLoading(true);
    try {
      const response = await fetchApi('/dashboard');
      if (response && !response.error) {
        setData(response);
        setError(false);
      }
    } catch (err) {
      if (err.message !== 'OFFLINE') {
        setError(true);
      }
    } finally {
      if (!isBackground) setLoading(false);
      setRefreshing(false);
    }
  };

  // Track previous transaction IDs to detect new ones for animation
  const prevTxIdsRef = useRef(new Set());
  const [newTxIds, setNewTxIds] = useState(new Set());

  const handleWsEvent = useCallback(() => loadData(true), []);

  useEffect(() => {
    loadData();

    const events = [
      'ws_transaction.created', 'ws_transaction.updated', 'ws_transaction.deleted',
      'ws_balance.updated', 'ws_debt.created', 'ws_debt.paid', 'ws_debt.updated',
      'ws_connected', 'ws_sync'
    ];
    events.forEach(e => window.addEventListener(e, handleWsEvent));
    return () => events.forEach(e => window.removeEventListener(e, handleWsEvent));
  }, [handleWsEvent]);

  // Detect new transactions and mark them for slide-down animation
  useEffect(() => {
    if (!data?.transactions) return;
    const currentIds = new Set(data.transactions.map(t => t.id));
    const added = new Set();
    currentIds.forEach(id => {
      if (!prevTxIdsRef.current.has(id)) added.add(id);
    });
    if (added.size > 0 && prevTxIdsRef.current.size > 0) {
      setNewTxIds(added);
      setTimeout(() => setNewTxIds(new Set()), 500);
    }
    prevTxIdsRef.current = currentIds;
  }, [data?.transactions]);

  // Pull to refresh logic
  const [startY, setStartY] = useState(0);
  const [pulling, setPulling] = useState(false);

  const handleTouchStart = (e) => {
    if (window.scrollY === 0) {
      setStartY(e.touches[0].clientY);
      setPulling(true);
    }
  };

  const handleTouchMove = (e) => {
    if (!pulling) return;
    const y = e.touches[0].clientY;
    if (y - startY > 100 && !refreshing) {
      setRefreshing(true);
      setPulling(false);
      loadData(false);
    }
  };

  const handleTouchEnd = () => {
    setPulling(false);
  };

  if (loading && !refreshing) {
    return <SkeletonPage cards={3} />;
  }

  if (error && !data) {
    return <ErrorState onRetry={() => loadData()} />;
  }

  // Safely extract from response structure
  const currentBalData = data?.balances?.find(b => b.currency === activeCurrency) || { amount: 0 };
  
  // Calculate kirim/chiqim safely from transactions or stats
  const currentStatData = data?.stats?.[activeStatCurrency]?.[activeStatTab] || [];
  const kirimStat = currentStatData.find(s => s.name === 'Kirim')?.value || 0;
  const chiqimStat = currentStatData.find(s => s.name === 'Chiqim')?.value || 0;

  const currentBal = {
    total: currentBalData.amount,
    kirim: kirimStat,
    chiqim: chiqimStat
  };

  const statData = currentStatData;
  const chartData = statData.reduce((acc, curr) => acc + curr.value, 0) === 0 
      ? [{ name: 'Bo\'sh', value: 1, color: '#38383A' }] 
      : statData;

  const debts = data?.debts || { berishimKerak: 0, olishimKerak: 0 };
  const transactions = data?.transactions || [];

  return (
    <div 
      className="animate-fade-in" 
      style={{ paddingBottom: '100px', paddingLeft: '16px', paddingRight: '16px', maxWidth: '800px', margin: '0 auto', paddingTop: '16px' }}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {refreshing && (
        <div style={{ textAlign: 'center', padding: '10px', color: 'var(--text-secondary)' }}>
          <RefreshCw className="animate-spin" size={24} style={{ margin: '0 auto' }} />
        </div>
      )}

      {/* MOBILE PROFILE HEADER (Hidden on desktop since sidebar has it) */}
      <div className="mobile-header flex-between" style={{ marginBottom: '24px' }}>
        <div 
          onClick={() => navigate('/profile')} 
          className="clickable" 
          style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer', padding: '4px', borderRadius: '12px', background: 'rgba(255,255,255,0.02)' }}
        >
          <div style={{ width: 44, height: 44, borderRadius: '12px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)' }}>
            <img src="/somly.jpg" alt="Somly AI" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          </div>
          <div>
            <h1 style={{ fontSize: '16px', fontWeight: '600', margin: 0, lineHeight: '1.2' }}>Salom, {userName} 👋</h1>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '2px 0 0 0' }}>Somly AI</p>
          </div>
        </div>
        <button
          onClick={() => setBalanceHidden(!balanceHidden)}
          className="clickable"
          style={{ padding: '8px', background: 'var(--card)', borderRadius: '12px', border: 'none', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
        >
          {balanceHidden ? <EyeOff size={20} /> : <Eye size={20} />}
        </button>
      </div>

      {/* UMUMIY BALANS KARTASI */}
      <div className="card-balance">
        <div className="flex-between" style={{ marginBottom: '8px', position: 'relative', zIndex: 1 }}>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px', fontWeight: '500' }}>Umumiy balans</p>
          <button
            onClick={() => setBalanceHidden(!balanceHidden)}
            className="clickable"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '4px' }}
          >
            {balanceHidden ? <EyeOff size={20} /> : <Eye size={20} />}
          </button>
        </div>
        <h2 style={{ fontSize: '32px', fontWeight: '700', margin: '0', display: 'flex', alignItems: 'baseline', gap: '8px', minHeight: '42px', position: 'relative', zIndex: 1 }}>
          {balanceHidden ? (
            <span style={{ letterSpacing: '8px', fontSize: '28px' }}>••••••</span>
          ) : (
            <>
              <AnimatedNumber value={currentBal.total} /> 
              <span style={{ fontSize: '18px', fontWeight: '600', color: 'var(--text-secondary)' }}>{activeCurrency}</span>
            </>
          )}
        </h2>
        <h3 style={{ fontSize: '20px', fontWeight: '700', margin: '4px 0 24px 0', display: 'flex', alignItems: 'baseline', gap: '8px', minHeight: '28px', position: 'relative', zIndex: 1 }}>
          {balanceHidden ? (
            <span style={{ letterSpacing: '6px', fontSize: '16px' }}>••••</span>
          ) : (
            <>
              0 <span style={{ fontSize: '14px', fontWeight: '600', color: 'var(--text-secondary)' }}>USD</span>
            </>
          )}
        </h3>

        {/* HORIZONTAL BALANCES LIST */}
        <div style={{ display: 'flex', gap: '12px', overflowX: 'auto', paddingBottom: '8px', margin: '0 -8px', padding: '0 8px', position: 'relative', zIndex: 1 }} className="no-scrollbar">
          {/* Add Button */}
          <button 
            onClick={() => setIsActionModalOpen(true)}
            className="clickable"
            style={{ 
              minWidth: '60px', height: '84px', borderRadius: '18px', background: 'var(--primary)', 
              border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff',
              flexShrink: 0, cursor: 'pointer', fontSize: '28px', boxShadow: '0 4px 16px rgba(10, 132, 255, 0.3)'
            }}
            title="Balans yaratish"
          >
            <Plus size={28} />
          </button>
          
          {/* User Balances */}
          {(data?.balances || []).map((b, i) => {
            const colors = [
              { emoji: '🟢', bg: 'linear-gradient(135deg, #34C759, #248A3D)', text: '#fff' },
              { emoji: '🟣', bg: 'linear-gradient(135deg, #8B5CF6, #6D28D9)', text: '#fff' },
              { emoji: '🟡', bg: 'linear-gradient(135deg, #F59E0B, #D97706)', text: '#fff' },
              { emoji: '🔵', bg: 'linear-gradient(135deg, #0A84FF, #0052CC)', text: '#fff' }
            ];
            const color = colors[i % colors.length];
            return (
              <div 
                key={i} 
                className={`balance-chip ${activeCurrency === b.currency ? 'balance-chip-active' : ''}`}
                onClick={() => setActiveCurrency(b.currency)} 
                style={{ background: color.bg, color: color.text }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontWeight: '600', opacity: 0.9 }}>
                  <span>{color.emoji}</span> {b.title || "So'm"}
                </div>
                <div style={{ fontSize: '16px', fontWeight: '700' }}>
                  {balanceHidden ? '••••' : `${b.amount.toLocaleString()} ${b.currency}`}
                </div>
              </div>
            );
          })}
          
          {/* View All Button */}
          <button 
            onClick={() => navigate('/balances')}
            className="clickable"
            style={{ 
              minWidth: '60px', height: '84px', borderRadius: '18px', background: 'var(--card)', 
              border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', 
              color: 'var(--text-secondary)', flexShrink: 0, cursor: 'pointer'
            }}
            title="Barchasini ko'rish"
          >
            <ChevronRight size={20} />
          </button>
        </div>
      </div>

      <QuickActions balances={data?.balances || []} onSuccess={() => loadData(false)} />
      <SmartWidgets data={data} />

      {/* QARZLAR WIDGET */}
      <div className="card" style={{ padding: '20px', marginBottom: '24px' }}>
        <div className="flex-between" style={{ marginBottom: '24px' }}>
          <h2 style={{ fontSize: '20px', fontWeight: '600', margin: 0 }}>Qarzlar</h2>
          <span onClick={() => navigate('/debts')} style={{ color: 'var(--primary)', fontSize: '14px', fontWeight: '600', cursor: 'pointer' }}>Barchasini →</span>
        </div>
        <div className="flex-between" style={{ marginBottom: '16px' }}>
          <div>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px', fontWeight: '500' }}>Berishim kerak</p>
            <p style={{ fontSize: '18px', fontWeight: '700', color: 'var(--danger)' }}>{balanceHidden ? '••••' : `${debts.berishimKerak.toLocaleString()} UZS`}</p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px', fontWeight: '500' }}>Olishim kerak</p>
            <p style={{ fontSize: '18px', fontWeight: '700', color: 'var(--success)' }}>{balanceHidden ? '••••' : `${debts.olishimKerak.toLocaleString()} UZS`}</p>
          </div>
        </div>
      </div>

      {/* STATISTIKA WIDGET */}
      <div className="card" style={{ padding: '20px', marginBottom: '24px' }}>
        <div className="flex-between" style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '20px', fontWeight: '600', margin: 0 }}>Statistika</h2>
          <Calendar size={20} color="var(--text-secondary)" />
        </div>
        
        {/* Date Selector */}
        <div className="flex-between" style={{ marginBottom: '20px' }}>
          <ChevronRight size={20} style={{ transform: 'rotate(180deg)', color: 'var(--text-primary)', cursor: 'pointer' }} />
          <span style={{ fontSize: '15px', fontWeight: '600', color: 'var(--text-primary)' }}>Apr 1 – Apr 20</span>
          <ChevronRight size={20} color="var(--text-primary)" style={{ cursor: 'pointer' }} />
        </div>

        {/* Currency Filters */}
        <div style={{ display: 'flex', gap: '8px', overflowX: 'auto', marginBottom: '24px' }} className="no-scrollbar">
          {['UZS', 'USD'].map((c) => (
            <div key={c} onClick={() => setActiveStatCurrency(c)} className="clickable" style={{ 
              padding: '8px 16px', borderRadius: '20px', fontSize: '14px', fontWeight: '600', flexShrink: 0,
              background: activeStatCurrency === c ? 'var(--primary)' : 'transparent',
              color: activeStatCurrency === c ? '#fff' : 'var(--text-secondary)',
              border: activeStatCurrency === c ? 'none' : '1px solid var(--border)',
              cursor: 'pointer'
            }}>
              {c}
            </div>
          ))}
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', background: 'var(--bg)', borderRadius: '12px', padding: '4px', marginBottom: '32px', gap: '4px' }}>
          {['Hammasi', 'Kirim', 'Chiqim', 'Qarz'].map(t => (
            <div key={t} className="clickable" onClick={() => setActiveStatTab(t)} style={{ 
              flex: 1, textAlign: 'center', padding: '10px 0', fontSize: '13px', fontWeight: '600', borderRadius: '10px',
              background: activeStatTab === t ? 'var(--card)' : 'transparent',
              color: activeStatTab === t ? 'var(--text-primary)' : 'var(--text-secondary)',
              cursor: 'pointer', transition: 'all 0.2s',
              boxShadow: activeStatTab === t ? '0 2px 8px rgba(0,0,0,0.05)' : 'none'
            }}>
              {t}
            </div>
          ))}
        </div>

        {/* Pie Chart */}
        <div style={{ height: '240px', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie 
                data={chartData} 
                innerRadius={65} 
                outerRadius={100} 
                paddingAngle={4} 
                cornerRadius={10} 
                dataKey="value" 
                stroke="none"
              >
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color || '#6366F1'} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', textAlign: 'center', background: 'var(--nav-bg)', padding: '12px 16px', borderRadius: '16px', backdropFilter: 'var(--glass-blur)', border: '1px solid var(--border)', boxShadow: '0 8px 32px rgba(0,0,0,0.1)' }}>
            <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '4px' }}>Jami chiqim:</p>
            <p style={{ fontSize: '16px', fontWeight: 'bold', color: 'var(--danger)' }}>-{currentBal.chiqim.toLocaleString()} {activeStatCurrency}</p>
          </div>
        </div>
      </div>

      {/* BUGUNGI HISOBOTLAR */}
      <div className="card" style={{ padding: '20px' }}>
        <div className="flex-between" style={{ marginBottom: '20px' }}>
          <h2 style={{ fontSize: '20px', fontWeight: '600', margin: 0 }}>Bugun</h2>
          <span onClick={() => navigate('/transactions')} style={{ color: 'var(--primary)', fontSize: '14px', fontWeight: '600', cursor: 'pointer' }}>Barchasini →</span>
        </div>

        {transactions.length === 0 ? (
          <EmptyState 
            icon="📝" 
            title="Hali hech narsa kiritilmagan" 
            subtitle="Xarajatingizni yozing yoki ovoz yuboring"
            example={<span>💬 <strong>"Taksiga 15 ming so'm"</strong></span>}
          />
        ) : (
          transactions.slice(0, 5).map(t => (
            <div 
              key={t.id} 
              className={`tx-item flex-between ${newTxIds.has(t.id) ? 'slide-down-enter' : ''}`}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                <div className={`tx-icon ${t.type === 'chiqim' ? 'tx-icon-expense' : 'tx-icon-income'}`}>
                  {t.category.split(' ')[0]}
                </div>
                <div>
                  <p style={{ fontWeight: '600', fontSize: '15px', color: 'var(--text-primary)', margin: 0 }}>{t.category.split(' ').slice(1).join(' ')}</p>
                  <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '4px 0 0 0' }}>
                    {t.type === 'chiqim' ? 'Chiqim' : 'Kirim'} • {t.currency || 'UZS'}
                  </p>
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <p style={{ fontWeight: '700', fontSize: '15px', color: t.type === 'chiqim' ? 'var(--danger)' : 'var(--success)', margin: 0 }}>
                  {t.type === 'chiqim' ? '-' : '+'} {t.amount.toLocaleString()}
                </p>
                <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '4px 0 0 0' }}>
                  {t.date ? t.date.substring(11, 16) : '00:00'}
                </p>
              </div>
            </div>
          ))
        )}
      </div>

      <TransactionModal 
        isOpen={isActionModalOpen} 
        onClose={() => {
          setIsActionModalOpen(false);
          loadData(); // Reload data after modal closes
        }} 
      />

      {/* End of Dashboard */}
    </div>
  );
};

export default DashboardPage;
