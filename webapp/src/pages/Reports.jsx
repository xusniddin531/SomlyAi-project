import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ChevronDown, X, Edit2, Trash2, Check, RefreshCw, Info } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip, Legend, Cell } from 'recharts';
import { useTranslation } from 'react-i18next';
import { fetchApi, showToast } from '../utils/api';
import { EmptyState, ErrorState, SkeletonPage } from '../components/StateViews';
import PageHeader from '../components/PageHeader';

const ReportsPage = ({ initData }) => {
  const { t } = useTranslation();
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Modals
  const [activeModal, setActiveModal] = useState(null);
  const [selectedTx, setSelectedTx] = useState(null);
  const [editForm, setEditForm] = useState({ amount: '', category: '', desc: '' });

  // Filters
  const [filters, setFilters] = useState({
    type: 'all',
    balances: [],
    dateStart: null,
    dateEnd: null,
    category: 'all'
  });

  const [filterDisplay, setFilterDisplay] = useState({
    type: 'Hammasi',
    balances: 'Barchasi',
    dateRange: 'Bugun',
    category: 'Barchasi'
  });

  const [chartData, setChartData] = useState([]);
  const scrollContainerRef = useRef(null);
  const swipeStartRef = useRef(0);

  const loadTransactions = async (isBackground = false) => {
    if (!isBackground) setLoading(true);
    try {
      let url = '/dashboard?all_txs=true';
      if (filters.dateStart && filters.dateEnd) {
        const sd = new Date(filters.dateStart).toISOString().split('T')[0];
        const ed = new Date(filters.dateEnd).toISOString().split('T')[0];
        url += `&start=${sd}&end=${ed}`;
      }
      const response = await fetchApi(url);
      if (response && response.transactions) {
        let filteredTxs = response.transactions;
        if (filters.type !== 'all') {
          filteredTxs = filteredTxs.filter(t => t.type === filters.type);
        }
        if (filters.category !== 'all') {
          filteredTxs = filteredTxs.filter(t => t.category === filters.category);
        }
        // Balance filter
        if (filters.balances && filters.balances.length > 0) {
          filteredTxs = filteredTxs.filter(t => {
            const cur = (t.balance_name || '').toLowerCase();
            return filters.balances.includes(cur);
          });
        }
        
        setTransactions(filteredTxs);
        buildChartData(filteredTxs);
        setError(false);
      }
    } catch (err) {
      if (err.message !== 'OFFLINE') setError(true);
    } finally {
      if (!isBackground) setLoading(false);
      setRefreshing(false);
    }
  };

  const buildChartData = (txs) => {
    const dayMap = {};
    txs.forEach(tx => {
      const date = new Date(tx.created_at);
      const day = date.getDate();
      const month = date.toLocaleString('uz-UZ', { month: 'short' });
      const key = `${day} ${month}`;
      
      if (!dayMap[key]) dayMap[key] = { name: key, dateObj: date, kirim: 0, chiqim: 0 };
      
      let amountInMln = tx.amount / 1000000;
      // Protect chart from breaking due to absurdly large numbers
      if (amountInMln > 999999) amountInMln = 999999;
      
      if (tx.type === 'kirim') dayMap[key].kirim += amountInMln;
      else if (tx.type === 'chiqim') dayMap[key].chiqim += amountInMln;
    });

    const sorted = Object.values(dayMap)
      .sort((a, b) => a.dateObj - b.dateObj)
      .map(item => ({
        name: item.name,
        Kirim: Number(item.kirim.toFixed(1)),
        Chiqim: Number(item.chiqim.toFixed(1))
      }));

    // If there is only one data point, adding a dummy point helps the chart render it centered
    if (sorted.length === 1) {
      setChartData([
        { name: '', Kirim: 0, Chiqim: 0 },
        sorted[0],
        { name: ' ', Kirim: 0, Chiqim: 0 }
      ]);
    } else {
      setChartData(sorted);
    }
  };

  const groupTransactionsByDate = (txs) => {
    const groups = {};
    txs.forEach(tx => {
      const date = new Date(tx.created_at).toLocaleDateString('uz-UZ', {
        weekday: 'short',
        month: 'long',
        day: 'numeric'
      });
      if (!groups[date]) {
        groups[date] = {
          transactions: [],
          total: 0
        };
      }
      groups[date].transactions.push(tx);
      groups[date].total += tx.type === 'kirim' ? tx.amount : -tx.amount;
    });

    return Object.entries(groups).sort((a, b) => new Date(b[0]) - new Date(a[0]));
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadTransactions(true);
  };

  const handleEditSubmit = async () => {
    if (!selectedTx) return;
    try {
      const updates = {};
      if (editForm.amount) updates.amount = parseInt(editForm.amount.toString().replace(/\s+/g, ''));
      if (editForm.category) updates.category = editForm.category;
      if (editForm.desc) updates.desc = editForm.desc;

      const payload = {
        user_id: window.Telegram?.WebApp?.initDataUnsafe?.user?.id,
        updates
      };

      const response = await fetchApi(`/transactions/${selectedTx.id}`, {
        method: 'PUT',
        body: JSON.stringify(payload)
      });

      if (response && response.success) {
        showToast('✅ Tranzaksiya yangilandi', 'success');
        setActiveModal(null);
        loadTransactions(true);
      }
    } catch (err) {
      showToast('❌ Yangilashda xato', 'error');
    }
  };

  const handleDelete = async (txId) => {
    try {
      const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
      const response = await fetchApi(`/transactions/${txId}?user_id=${userId}`, {
        method: 'DELETE'
      });

      if (response && response.success) {
        showToast('✅ Tranzaksiya o\'chirildi', 'success');
        setActiveModal(null);
        loadTransactions(true);
      }
    } catch (err) {
      showToast('❌ O\'chirishda xato', 'error');
    }
  };

  const handleSwipe = (txId, direction) => {
    if (direction === 'left') {
      setSelectedTx(transactions.find(t => t.id === txId));
      setActiveModal('delete');
    }
  };

  useEffect(() => {
    loadTransactions();
  }, [filters]); // reload on filter change

  useEffect(() => {
    const events = ['ws_transaction.updated', 'ws_transaction.deleted', 'ws_transaction.created'];
    const handler = () => loadTransactions(true);
    events.forEach(e => window.addEventListener(e, handler));
    return () => {
      events.forEach(e => window.removeEventListener(e, handler));
    };
  }, [filters]);

  // Group transactions
  const groupedTxs = groupTransactionsByDate(transactions);

  const hasActiveFilters = filters.type !== 'all' || filters.balances.length > 0 || filters.dateStart !== null || filters.category !== 'all';

  if (loading) return <SkeletonPage cards={4} />;
  
  if (error && transactions.length === 0) {
    return <ErrorState onRetry={() => loadTransactions()} />;
  }

  return (
    <div style={{ padding: '0 0 100px' }}>
      {/* Header */}
      <div style={{
        padding: '16px',
        background: 'var(--card)',
        borderBottom: '1px solid var(--border)',
        position: 'sticky',
        top: 0,
        zIndex: 10
      }}>
        <PageHeader 
          title="Hisobotlar" 
          showLogo={true} 
          rightElement={
            <button
              onClick={handleRefresh}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--primary)',
                padding: '8px'
              }}
              className={refreshing ? 'spin-animation' : ''}
            >
              <RefreshCw size={20} />
            </button>
          }
        />
      </div>

      {/* Filters */}
      <div style={{
        padding: '12px 16px',
        overflowX: 'auto',
        background: 'var(--bg)',
        display: 'flex',
        gap: '8px',
        borderBottom: '1px solid var(--border)'
      }}
      ref={scrollContainerRef}
      className="horizontal-scroll"
      >
        <FilterChip
          label={filterDisplay.type}
          onClick={() => setActiveModal('type')}
        />
        <FilterChip
          label={filterDisplay.balances}
          onClick={() => setActiveModal('balances')}
        />
        <FilterChip
          label={filterDisplay.dateRange}
          onClick={() => setActiveModal('date')}
        />
        <FilterChip
          label={filterDisplay.category}
          onClick={() => setActiveModal('category')}
        />
      </div>

      {/* Chart */}
      {chartData.length > 0 && (
        <div style={{ padding: '24px 16px', background: 'var(--bg)' }}>
          <h3 style={{
            fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)',
            marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px'
          }}>
            📊 Xarajat va Daromad statistikasi
          </h3>
          <div style={{ height: '240px', marginLeft: '-15px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }} barGap={4} barSize={14}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="name" stroke="var(--text-secondary)" fontSize={11} tickLine={false} axisLine={false} />
                <YAxis 
                  stroke="var(--text-secondary)" 
                  fontSize={11} 
                  tickLine={false} 
                  axisLine={false} 
                  tickFormatter={(v) => {
                    if (v >= 1000) return `${(v/1000).toFixed(1)}B`;
                    return v;
                  }} 
                />
                <Tooltip
                  contentStyle={{
                    background: 'rgba(28, 28, 30, 0.85)',
                    backdropFilter: 'blur(20px)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '12px',
                    color: '#fff',
                    boxShadow: '0 8px 32px rgba(0,0,0,0.4)'
                  }}
                  itemStyle={{ fontWeight: '600' }}
                  cursor={{ fill: 'rgba(255,255,255,0.05)' }}
                  formatter={(value) => [`${value} mln`, undefined]}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: '12px', paddingTop: '15px' }} />
                <Bar dataKey="Kirim" fill="var(--success)" radius={[4, 4, 4, 4]} />
                <Bar dataKey="Chiqim" fill="var(--danger)" radius={[4, 4, 4, 4]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Transactions List */}
      <div style={{ padding: '16px' }}>
        {groupedTxs.length === 0 ? (
          <EmptyState 
            icon="📊" 
            title={hasActiveFilters ? "Hisobotlar topilmadi" : "Hali hisobotlar yo'q"}
            subtitle={hasActiveFilters ? "Tanlangan filtrlar bo'yicha hisobotlar topilmadi" : "Sizda hali hech qanday tranzaksiya mavjud emas."}
            example={hasActiveFilters ? (
              <button 
                onClick={() => {
                  setFilters({ type: 'all', balances: [], dateStart: null, dateEnd: null, category: 'all' });
                  setFilterDisplay({ type: 'Hammasi', balances: 'Barchasi', dateRange: 'Bugun', category: 'Barchasi' });
                }}
                style={{ 
                  background: 'var(--primary)', color: '#fff', border: 'none', 
                  padding: '8px 16px', borderRadius: '8px', fontWeight: '600', cursor: 'pointer' 
                }}
              >
                Filtrlarni tozalash
              </button>
            ) : null}
          />
        ) : (
          groupedTxs.map(([date, group]) => (
            <div key={date}>
              {/* Date Header */}
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '12px 0',
                marginBottom: '8px',
                borderBottom: '1px solid var(--border)'
              }}>
                <h3 style={{
                  margin: 0,
                  fontSize: '14px',
                  fontWeight: 600,
                  color: 'var(--text-secondary)',
                  textTransform: 'capitalize'
                }}>
                  {date}
                </h3>
                <span style={{
                  fontSize: '12px',
                  fontWeight: 600,
                  color: group.total >= 0 ? 'var(--success)' : 'var(--danger)'
                }}>
                  {group.total >= 0 ? '+' : ''}{(group.total / 1000000).toFixed(1)}M
                </span>
              </div>

              {/* Transaction Cards */}
              {group.transactions.map((tx) => (
                <TransactionCard
                  key={tx.id}
                  tx={tx}
                  onTap={() => {
                    setSelectedTx(tx);
                    setEditForm({ 
                      amount: tx.amount ? tx.amount.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") : '', 
                      category: '', 
                      desc: '' 
                    });
                    setActiveModal('edit');
                  }}
                  onSwipe={(dir) => handleSwipe(tx.id, dir)}
                />
              ))}
            </div>
          ))
        )}
      </div>

      {/* Modals */}
      {activeModal === 'type' && (
        <FilterModal
          title="Turi"
          onClose={() => setActiveModal(null)}
          onApply={(value) => {
            setFilters({ ...filters, type: value });
            setFilterDisplay({ ...filterDisplay, type: value });
            setActiveModal(null);
          }}
          options={[
            { label: 'Hammasi', value: 'all' },
            { label: 'Kirim', value: 'kirim' },
            { label: 'Chiqim', value: 'chiqim' },
            { label: 'Qarz', value: 'debt' }
          ]}
          selected={filters.type}
          type="radio"
        />
      )}

      {activeModal === 'balances' && (
        <FilterModal
          title="Balanslar"
          onClose={() => setActiveModal(null)}
          onApply={(values) => {
            setFilters({ ...filters, balances: values });
            const names = values.length ? values.map(v => {
              const nameMap = { 'usd': 'USD' };
              return nameMap[v] || v;
            }).join(', ') : 'Barchasi';
            setFilterDisplay({ ...filterDisplay, balances: names });
            setActiveModal(null);
          }}
          options={[
            { label: 'UZS', value: 'uzs' },
            { label: 'USD', value: 'usd' }
          ]}
          selected={filters.balances}
          type="checkbox"
          showClear={true}
          onClear={() => {
            setFilters({ ...filters, balances: [] });
            setFilterDisplay({ ...filterDisplay, balances: 'Barchasi' });
            setActiveModal(null);
          }}
        />
      )}

      {activeModal === 'date' && (
        <FilterModal
          title="Sana"
          onClose={() => setActiveModal(null)}
          onApply={(range) => {
            setFilters({ ...filters, dateStart: range.start, dateEnd: range.end });
            setFilterDisplay({ ...filterDisplay, dateRange: range.display });
            setActiveModal(null);
          }}
          options={[
            { label: 'Bugungi kun', value: 'today' },
            { label: 'Hafta', value: 'week' },
            { label: 'O\'tgan oy', value: 'month' }
          ]}
          type="date"
          showClear={true}
          onClear={() => {
            setFilters({ ...filters, dateStart: null, dateEnd: null });
            setFilterDisplay({ ...filterDisplay, dateRange: 'Bugun' });
            setActiveModal(null);
          }}
        />
      )}

      {activeModal === 'category' && (
        <FilterModal
          title="Kategoriya"
          onClose={() => setActiveModal(null)}
          onApply={(value) => {
            setFilters({ ...filters, category: value });
            setFilterDisplay({ ...filterDisplay, category: value });
            setActiveModal(null);
          }}
          options={[
            { label: 'Barchasi', value: 'all' },
            { label: 'Ovqat', value: 'food' },
            { label: 'Transport', value: 'transport' },
            { label: 'Uy xizmatlar', value: 'utilities' }
          ]}
          selected={filters.category}
          type="radio"
        />
      )}

      {activeModal === 'edit' && selectedTx && (
        <EditModal
          tx={selectedTx}
          form={editForm}
          setForm={setEditForm}
          onClose={() => setActiveModal(null)}
          onSave={handleEditSubmit}
        />
      )}

      {activeModal === 'delete' && selectedTx && (
        <ConfirmModal
          message={`"${selectedTx.desc}" o'chirilsinmi?`}
          onConfirm={() => handleDelete(selectedTx.id)}
          onCancel={() => setActiveModal(null)}
        />
      )}

      <style>{`
        .horizontal-scroll {
          -webkit-overflow-scrolling: touch;
          scroll-behavior: smooth;
        }
        .horizontal-scroll::-webkit-scrollbar {
          height: 4px;
        }
        .horizontal-scroll::-webkit-scrollbar-thumb {
          background: var(--primary);
          border-radius: 2px;
        }
        .spin-animation {
          animation: spin 0.8s linear infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

const FilterChip = ({ label, onClick }) => (
  <button
    onClick={onClick}
    style={{
      background: 'var(--card)',
      border: '1px solid var(--border)',
      padding: '8px 16px',
      borderRadius: '20px',
      color: 'var(--text-primary)',
      cursor: 'pointer',
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
      fontSize: '13px',
      fontWeight: 500,
      whiteSpace: 'nowrap',
      transition: 'all 0.2s'
    }}
    onMouseOver={(e) => e.target.style.background = 'var(--primary)'}
    onMouseOut={(e) => e.target.style.background = 'var(--card)'}
  >
    {label}
    <ChevronDown size={14} />
  </button>
);

const TransactionCard = ({ tx, onTap, onSwipe }) => {
  const startXRef = useRef(0);
  const startYRef = useRef(0);

  const handleTouchStart = (e) => {
    startXRef.current = e.touches[0].clientX;
    startYRef.current = e.touches[0].clientY;
  };

  const handleTouchEnd = (e) => {
    const endX = e.changedTouches[0].clientX;
    const endY = e.changedTouches[0].clientY;
    const diffX = startXRef.current - endX;
    const diffY = startYRef.current - endY;

    if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 50) {
      if (diffX > 0) {
        onSwipe('left');
      }
    }
  };

  const emojiMap = {
    food: '🍽️',
    transport: '🚗',
    utilities: '💡',
    salary: '💰',
    shopping: '🛍️',
    default: '💳'
  };

  return (
    <div
      onClick={onTap}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      className="clickable"
      style={{
        background: 'var(--card)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '12px',
        marginBottom: '8px',
        display: 'grid',
        gridTemplateColumns: '1fr auto',
        gap: '12px',
        cursor: 'pointer',
        transition: 'all 0.2s'
      }}
      onMouseOver={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}
      onMouseOut={(e) => e.currentTarget.style.background = 'var(--card)'}
    >
      <div>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: '6px'
        }}>
          <span style={{ fontSize: '18px' }}>
            {emojiMap[tx.category] || emojiMap.default}
          </span>
          <span style={{
            fontSize: '14px',
            fontWeight: 500,
            flex: 1,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis'
          }}>
            {tx.desc}
          </span>
          <span style={{
            fontSize: '14px',
            fontWeight: 600,
            color: tx.type === 'kirim' ? 'var(--success)' : 'var(--danger)'
          }}>
            {tx.type === 'kirim' ? '+' : '-'}{(tx.amount / 1000000).toFixed(1)}M
          </span>
        </div>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          fontSize: '12px',
          color: 'var(--text-secondary)'
        }}>
          <span>{tx.category}</span>
          <span>•</span>
          <span>{tx.balance_name}</span>
          <span>•</span>
          <span>{new Date(tx.created_at).toLocaleTimeString('uz-UZ', {
            hour: '2-digit',
            minute: '2-digit'
          })}</span>
        </div>
      </div>
    </div>
  );
};

const FilterModal = ({
  title,
  onClose,
  onApply,
  onClear,
  options,
  selected,
  type,
  showClear
}) => {
  const [localSelected, setLocalSelected] = useState(
    type === 'checkbox' ? selected : (selected || 'all')
  );

  return (
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
    onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--card)',
          width: '100%',
          borderRadius: '20px 20px 0 0',
          padding: '20px'
        }}
      >
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '16px'
        }}>
          <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 700 }}>{title}</h2>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--text-primary)',
              padding: '8px'
            }}
          >
            <X size={20} />
          </button>
        </div>

        <div style={{ maxHeight: '300px', overflowY: 'auto', marginBottom: '16px' }}>
          {type === 'radio' && (
            <div>
              {options.map((opt) => (
                <label
                  key={opt.value}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    padding: '12px',
                    cursor: 'pointer',
                    borderRadius: '8px',
                    marginBottom: '8px',
                    background: localSelected === opt.value ? 'rgba(0,0,0,0.1)' : 'transparent'
                  }}
                >
                  <input
                    type="radio"
                    name="filter"
                    value={opt.value}
                    checked={localSelected === opt.value}
                    onChange={() => setLocalSelected(opt.value)}
                    style={{ marginRight: '12px', cursor: 'pointer' }}
                  />
                  <span style={{ fontSize: '14px', fontWeight: 500 }}>{opt.label}</span>
                </label>
              ))}
            </div>
          )}

          {type === 'checkbox' && (
            <div>
              {options.map((opt) => (
                <label
                  key={opt.value}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    padding: '12px',
                    cursor: 'pointer',
                    borderRadius: '8px',
                    marginBottom: '8px',
                    background: localSelected.includes(opt.value) ? 'rgba(0,0,0,0.1)' : 'transparent'
                  }}
                >
                  <input
                    type="checkbox"
                    checked={localSelected.includes(opt.value)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setLocalSelected([...localSelected, opt.value]);
                      } else {
                        setLocalSelected(localSelected.filter(v => v !== opt.value));
                      }
                    }}
                    style={{ marginRight: '12px', cursor: 'pointer' }}
                  />
                  <span style={{ fontSize: '14px', fontWeight: 500 }}>{opt.label}</span>
                </label>
              ))}
            </div>
          )}

          {type === 'date' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {options.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => {
                    const ranges = {
                      today: { start: new Date(), end: new Date(), display: 'Bugun' },
                      week: {
                        start: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000),
                        end: new Date(),
                        display: 'Oxirgi 7 kun'
                      },
                      month: {
                        start: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000),
                        end: new Date(),
                        display: 'Oxirgi 30 kun'
                      }
                    };
                    onApply(ranges[opt.value]);
                  }}
                  style={{
                    background: 'var(--bg)',
                    border: 'none',
                    padding: '12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontSize: '14px',
                    fontWeight: 500,
                    color: 'var(--text-primary)'
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>

        <div style={{
          display: 'flex',
          gap: '8px'
        }}>
          {showClear && (
            <button
              onClick={onClear}
              style={{
                flex: 1,
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                padding: '12px',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: 600,
                color: 'var(--text-primary)'
              }}
            >
              O'chirish
            </button>
          )}
          <button
            onClick={() => onApply(localSelected)}
            style={{
              flex: 1,
              background: 'var(--primary)',
              border: 'none',
              padding: '12px',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: 600,
              color: '#fff'
            }}
          >
            Qo'llash
          </button>
        </div>
      </div>
    </div>
  );
};

const EditModal = ({ tx, form, setForm, onClose, onSave }) => {
  const [txType, setTxType] = useState(tx.type || 'kirim');
  const [isPlaying, setIsPlaying] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showCopyConfirm, setShowCopyConfirm] = useState(false);
  const audioRef = useRef(null);

  const handlePlayAudio = () => {
    if (tx.voice_file_url) {
      if (isPlaying) {
        audioRef.current?.pause();
        setIsPlaying(false);
      } else {
        audioRef.current?.play();
        setIsPlaying(true);
      }
    }
  };

  const handleCopyTransaction = async () => {
    try {
      const payload = {
        user_id: window.Telegram?.WebApp?.initDataUnsafe?.user?.id,
        original_id: tx.id,
        copy_data: {
          type: txType,
          amount: form.amount || tx.amount,
          category: form.category || tx.category,
          desc: form.desc || tx.desc,
          balance: form.balance || tx.balance_name,
          debt_person: form.debt_person || tx.debt_person
        }
      };

      const response = await fetchApi('/transactions', {
        method: 'POST',
        body: JSON.stringify(payload)
      });

      if (response && response.success) {
        showToast('✅ Nusxa yaratildi', 'success');
        setShowCopyConfirm(false);
      }
    } catch (err) {
      showToast('❌ Nusxa xatosi', 'error');
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return '';
      return date.toLocaleString('uz-UZ', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch (e) {
      return '';
    }
  };

  const getSafeDatetimeLocal = (dateStr) => {
    try {
      if (!dateStr) return '';
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return '';
      const local = new Date(d.getTime() - (d.getTimezoneOffset() * 60000));
      return local.toISOString().slice(0, 16);
    } catch (e) {
      return '';
    }
  };

  return (
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
    onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--card)',
          width: '100%',
          borderRadius: '20px 20px 0 0',
          padding: '16px',
          maxHeight: '90vh',
          overflowY: 'auto'
        }}
      >
        {/* Top Action Bar */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '16px',
          paddingBottom: '12px',
          borderBottom: '1px solid var(--border)'
        }}>
          <button
            onClick={() => setShowDeleteConfirm(true)}
            title="O'chirish"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--danger)',
              fontSize: '18px',
              padding: '8px',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontWeight: 600
            }}
          >
            🗑 O'chirish
          </button>

          <button
            onClick={() => setShowCopyConfirm(true)}
            title="Nusxa olish"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--primary)',
              fontSize: '16px',
              padding: '8px',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontWeight: 600
            }}
          >
            ⧉ Nusxa
          </button>

          <button
            onClick={onClose}
            title="Yopish"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--text-secondary)',
              fontSize: '18px',
              padding: '8px'
            }}
          >
            ✕
          </button>
        </div>

        {/* Type Tabs */}
        <div style={{
          display: 'flex',
          gap: '12px',
          marginBottom: '16px',
          borderBottom: '1px solid var(--border)',
          paddingBottom: '12px'
        }}>
          {[
            { value: 'kirim', label: 'Kirim', emoji: '📥' },
            { value: 'chiqim', label: 'Chiqim', emoji: '📤' },
            { value: 'debt', label: 'Qarz', emoji: '🤝' }
          ].map((tab) => (
            <button
              key={tab.value}
              onClick={() => setTxType(tab.value)}
              style={{
                background: 'none',
                border: 'none',
                padding: '8px 12px',
                fontSize: '14px',
                fontWeight: txType === tab.value ? 700 : 500,
                color: txType === tab.value ? 'var(--primary)' : 'var(--text-secondary)',
                cursor: 'pointer',
                borderBottom: txType === tab.value ? '2px solid var(--primary)' : '2px solid transparent',
                transition: 'all 0.2s',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}
            >
              {txType === tab.value ? '●' : '○'} {tab.label}
            </button>
          ))}
        </div>

        {/* Audio Playback (if voice input) */}
        {tx.voice_file_url && (
          <div style={{
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            borderRadius: '12px',
            padding: '12px 16px',
            marginBottom: '16px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px'
          }}>
            <button
              onClick={handlePlayAudio}
              style={{
                background: 'var(--primary)',
                border: 'none',
                color: '#fff',
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 700,
                fontSize: '16px'
              }}
            >
              {isPlaying ? '⏸' : '▶'}
            </button>
            <div style={{
              flex: 1,
              height: '4px',
              background: 'var(--border)',
              borderRadius: '2px',
              position: 'relative'
            }}>
              <div style={{
                height: '100%',
                background: 'var(--primary)',
                borderRadius: '2px',
                animation: isPlaying ? 'wave 0.6s ease-in-out infinite' : 'none',
                width: isPlaying ? '30%' : '0%'
              }} />
            </div>
            <span style={{
              fontSize: '12px',
              color: 'var(--text-secondary)',
              fontWeight: 600
            }}>
              Ovoz
            </span>
            <audio
              ref={audioRef}
              src={tx.voice_file_url}
              onEnded={() => setIsPlaying(false)}
            />
          </div>
        )}

        {/* Form Fields */}
        <div style={{ display: 'grid', gap: '14px', marginBottom: '16px' }}>
          {/* Amount & Currency */}
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '8px' }}>
            <div>
              <label style={{
                fontSize: '12px',
                color: 'var(--text-secondary)',
                fontWeight: 600,
                display: 'block',
                marginBottom: '6px'
              }}>
                Summa
              </label>
              <input
                type="tel"
                value={form.amount}
                onChange={(e) => {
                  let rawVal = e.target.value.replace(/\s+/g, '');
                  if (rawVal === '') {
                    setForm({ ...form, amount: '' });
                    return;
                  }
                  if (!/^\d*$/.test(rawVal)) return;
                  if (rawVal.length > 1 && rawVal.startsWith('0')) {
                    rawVal = rawVal.replace(/^0+/, '');
                  }
                  const formattedVal = rawVal.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
                  setForm({ ...form, amount: formattedVal });
                }}
                style={{
                  width: '100%',
                  background: 'var(--bg)',
                  border: '1px solid var(--border)',
                  padding: '10px',
                  borderRadius: '8px',
                  color: 'var(--text-primary)',
                  fontSize: '14px',
                  boxSizing: 'border-box'
                }}
              />
            </div>
            <div>
              <label style={{
                fontSize: '12px',
                color: 'var(--text-secondary)',
                fontWeight: 600,
                display: 'block',
                marginBottom: '6px'
              }}>
                Valyuta
              </label>
              <select
                value={form.currency || tx.currency || 'UZS'}
                onChange={(e) => setForm({ ...form, currency: e.target.value })}
                style={{
                  width: '100%',
                  background: 'var(--bg)',
                  border: '1px solid var(--border)',
                  padding: '10px',
                  borderRadius: '8px',
                  color: 'var(--text-primary)',
                  fontSize: '14px',
                  boxSizing: 'border-box'
                }}
              >
                <option value="UZS">UZS</option>
                <option value="USD">USD</option>
                <option value="RUB">RUB</option>
              </select>
            </div>
          </div>

          {/* Details */}
          <div>
            <label style={{
              fontSize: '12px',
              color: 'var(--text-secondary)',
              fontWeight: 600,
              display: 'block',
              marginBottom: '6px'
            }}>
              Tafsilot
            </label>
            <input
              type="text"
              value={form.desc || tx.desc}
              onChange={(e) => setForm({ ...form, desc: e.target.value })}
              placeholder="Izoh yozing..."
              style={{
                width: '100%',
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                padding: '10px',
                borderRadius: '8px',
                color: 'var(--text-primary)',
                fontSize: '14px',
                boxSizing: 'border-box'
              }}
            />
          </div>

          {/* Balance Dropdown */}
          <div>
            <label style={{
              fontSize: '12px',
              color: 'var(--text-secondary)',
              fontWeight: 600,
              display: 'block',
              marginBottom: '6px'
            }}>
              Balans
            </label>
            <select
              value={form.balance || tx.balance_name || ''}
              onChange={(e) => setForm({ ...form, balance: e.target.value })}
              style={{
                width: '100%',
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                padding: '10px',
                borderRadius: '8px',
                color: 'var(--text-primary)',
                fontSize: '14px',
                boxSizing: 'border-box'
              }}
            >
              <option value="">Tanlang...</option>
              <option value="UZS">UZS</option>
              <option value="USD">USD</option>
            </select>
          </div>

          {/* Category Dropdown */}
          <div>
            <label style={{
              fontSize: '12px',
              color: 'var(--text-secondary)',
              fontWeight: 600,
              display: 'block',
              marginBottom: '6px'
            }}>
              Kategoriya
            </label>
            <select
              value={form.category || tx.category || ''}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              style={{
                width: '100%',
                background: 'var(--bg)',
                border: '1px solid var(--border)',
                padding: '10px',
                borderRadius: '8px',
                color: 'var(--text-primary)',
                fontSize: '14px',
                boxSizing: 'border-box'
              }}
            >
              <option value="">Tanlang...</option>
              <option value="food">🍽️ Ovqat</option>
              <option value="transport">🚗 Transport</option>
              <option value="utilities">💡 Uy xizmatlar</option>
              <option value="entertainment">🎬 Xushlik</option>
              <option value="shopping">🛍️ Savdo</option>
              <option value="other">💳 Boshqa</option>
            </select>
          </div>

          {/* Date & Time */}
          <div>
            <label style={{
              fontSize: '12px',
              color: 'var(--text-secondary)',
              fontWeight: 600,
              display: 'block',
              marginBottom: '6px'
            }}>
              Sana va vaqt
            </label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="datetime-local"
                value={form.datetime || getSafeDatetimeLocal(tx.created_at)}
                onChange={(e) => setForm({ ...form, datetime: e.target.value })}
                style={{
                  flex: 1,
                  background: 'var(--bg)',
                  border: '1px solid var(--border)',
                  padding: '10px',
                  borderRadius: '8px',
                  color: 'var(--text-primary)',
                  fontSize: '14px',
                  boxSizing: 'border-box'
                }}
              />
              <button
                style={{
                  background: 'var(--bg)',
                  border: '1px solid var(--border)',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  color: 'var(--text-primary)',
                  fontSize: '16px'
                }}
              >
                📅
              </button>
            </div>
          </div>

          {/* Additional Fields for Debt */}
          {txType === 'debt' && (
            <>
              <div>
                <label style={{
                  fontSize: '12px',
                  color: 'var(--text-secondary)',
                  fontWeight: 600,
                  display: 'block',
                  marginBottom: '6px'
                }}>
                  Qarz olgan/bergan shaxs
                </label>
                <input
                  type="text"
                  value={form.debt_person || tx.debt_person || ''}
                  onChange={(e) => setForm({ ...form, debt_person: e.target.value })}
                  placeholder="Ism..."
                  style={{
                    width: '100%',
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    padding: '10px',
                    borderRadius: '8px',
                    color: 'var(--text-primary)',
                    fontSize: '14px',
                    boxSizing: 'border-box'
                  }}
                />
              </div>

              <div>
                <label style={{
                  fontSize: '12px',
                  color: 'var(--text-secondary)',
                  fontWeight: 600,
                  display: 'block',
                  marginBottom: '6px'
                }}>
                  Qarz muddati
                </label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input
                    type="date"
                    value={form.debt_deadline || tx.debt_deadline?.split('T')[0] || ''}
                    onChange={(e) => setForm({ ...form, debt_deadline: e.target.value })}
                    style={{
                      flex: 1,
                      background: 'var(--bg)',
                      border: '1px solid var(--border)',
                      padding: '10px',
                      borderRadius: '8px',
                      color: 'var(--text-primary)',
                      fontSize: '14px',
                      boxSizing: 'border-box'
                    }}
                  />
                  <button
                    style={{
                      background: 'var(--bg)',
                      border: '1px solid var(--border)',
                      padding: '10px 12px',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      color: 'var(--text-primary)',
                      fontSize: '16px'
                    }}
                  >
                    📅
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Close Button */}
        <button
          onClick={onSave}
          style={{
            width: '100%',
            background: '#1E3A8A',
            border: 'none',
            padding: '14px',
            borderRadius: '12px',
            cursor: 'pointer',
            fontWeight: 700,
            color: '#fff',
            fontSize: '16px',
            marginBottom: '8px'
          }}
        >
          Saqlash
        </button>

        {/* Delete Confirmation Modal */}
        {showDeleteConfirm && (
          <div style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1001
          }}
          onClick={() => setShowDeleteConfirm(false)}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: 'var(--card)',
                borderRadius: '16px',
                padding: '20px',
                maxWidth: '340px',
                textAlign: 'center'
              }}
            >
              <p style={{
                margin: '0 0 20px 0',
                fontSize: '14px',
                color: 'var(--text-primary)'
              }}>
                <strong>Tranzaksiya o'chiriladimi?</strong><br/>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                  Balans qayta hisoblanadi.
                </span>
              </p>
              <div style={{
                display: 'flex',
                gap: '8px'
              }}>
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  style={{
                    flex: 1,
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    padding: '12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontWeight: 600,
                    color: 'var(--text-primary)'
                  }}
                >
                  Bekor
                </button>
                <button
                  onClick={async () => {
                    setShowDeleteConfirm(false);
                    const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;
                    await (window.confirm = () => true);
                    // Call parent delete handler
                    const response = await fetchApi(`/transactions/${tx.id}?user_id=${userId}`, {
                      method: 'DELETE'
                    });
                    if (response && response.success) {
                      showToast('✅ Tranzaksiya o\'chirildi', 'success');
                      onClose();
                    }
                  }}
                  style={{
                    flex: 1,
                    background: 'var(--danger)',
                    border: 'none',
                    padding: '12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontWeight: 600,
                    color: '#fff'
                  }}
                >
                  O'chirish 🗑
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Copy Confirmation Modal */}
        {showCopyConfirm && (
          <div style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1001
          }}
          onClick={() => setShowCopyConfirm(false)}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: 'var(--card)',
                borderRadius: '16px',
                padding: '20px',
                maxWidth: '340px',
                textAlign: 'center'
              }}
            >
              <p style={{
                margin: '0 0 20px 0',
                fontSize: '14px',
                color: 'var(--text-primary)'
              }}>
                <strong>Tranzaksiyaning nusxasini yaratishchi?</strong>
              </p>
              <div style={{
                display: 'flex',
                gap: '8px'
              }}>
                <button
                  onClick={() => setShowCopyConfirm(false)}
                  style={{
                    flex: 1,
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    padding: '12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontWeight: 600,
                    color: 'var(--text-primary)'
                  }}
                >
                  Bekor
                </button>
                <button
                  onClick={handleCopyTransaction}
                  style={{
                    flex: 1,
                    background: 'var(--primary)',
                    border: 'none',
                    padding: '12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontWeight: 600,
                    color: '#fff'
                  }}
                >
                  Nusxa olish ⧉
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      <style>{`
        @keyframes wave {
          0%, 100% { width: 0%; }
          50% { width: 30%; }
        }
      `}</style>
    </div>
  );
};

const ConfirmModal = ({ message, onConfirm, onCancel }) => (
  <div style={{
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'rgba(0,0,0,0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000
  }}
  onClick={onCancel}
  >
    <div
      onClick={(e) => e.stopPropagation()}
      style={{
        background: 'var(--card)',
        borderRadius: '16px',
        padding: '20px',
        maxWidth: '320px',
        textAlign: 'center'
      }}
    >
      <p style={{ margin: '0 0 20px 0', fontSize: '14px', color: 'var(--text-primary)' }}>
        {message}
      </p>
      <div style={{
        display: 'flex',
        gap: '8px'
      }}>
        <button
          onClick={onCancel}
          style={{
            flex: 1,
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            padding: '12px',
            borderRadius: '8px',
            cursor: 'pointer',
            fontWeight: 600,
            color: 'var(--text-primary)'
          }}
        >
          Bekor
        </button>
        <button
          onClick={onConfirm}
          style={{
            flex: 1,
            background: 'var(--danger)',
            border: 'none',
            padding: '12px',
            borderRadius: '8px',
            cursor: 'pointer',
            fontWeight: 600,
            color: '#fff'
          }}
        >
          O'chirish
        </button>
      </div>
    </div>
  </div>
);

export default ReportsPage;
