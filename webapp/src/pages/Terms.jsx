import React from 'react';
import { FileText, ArrowLeft, CheckCircle, AlertTriangle, Users, Ban } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../components/PageHeader';

const TermsPage = () => {
  const navigate = useNavigate();

  return (
    <div className="animate-fade-in" style={{ padding: '0 16px 100px', paddingTop: '16px', maxWidth: '800px', margin: '0 auto' }}>
      
      {/* Header */}
      <PageHeader title="Foydalanish shartlari" showLogo={true} showBack={true} />

      {/* Icon */}
      <div style={{ textAlign: 'center', marginBottom: '32px' }}>
        <div style={{ 
          width: '80px', height: '80px', borderRadius: '40px', 
          background: 'linear-gradient(135deg, rgba(10,132,255,0.2) 0%, rgba(191,90,242,0.2) 100%)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', 
          margin: '0 auto 16px', border: '1px solid rgba(10,132,255,0.3)'
        }}>
          <FileText size={40} color="#0A84FF" />
        </div>
        <h2 style={{ fontSize: '18px', fontWeight: '700', color: 'var(--text-primary)', margin: '0 0 8px' }}>Somly AI Foydalanish Shartlari</h2>
        <p style={{ fontSize: '14px', color: 'var(--text-secondary)', margin: 0 }}>Oxirgi yangilanish: 2026-yil, may</p>
      </div>

      {/* Main Content */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>

        {/* Section 1 */}
        <div style={{ background: 'var(--card)', borderRadius: '20px', padding: '20px', border: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{ background: 'rgba(10,132,255,0.15)', padding: '10px', borderRadius: '12px' }}>
              <CheckCircle size={20} color="#0A84FF" />
            </div>
            <h3 style={{ fontSize: '16px', fontWeight: '700', color: 'var(--text-primary)', margin: 0 }}>Umumiy qoidalar</h3>
          </div>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', lineHeight: '1.7', margin: 0 }}>
            Somly AI — shaxsiy moliyaviy boshqaruv uchun mo'ljallangan Telegram bot va Mini App xizmati. 
            Xizmatdan foydalanish orqali siz ushbu shartlarga rozilik bildirasiz. Somly AI <strong style={{ color: 'var(--text-primary)' }}>bepul xizmat</strong> bo'lib, 
            barcha asosiy funksiyalar tekin taqdim etiladi.
          </p>
        </div>

        {/* Section 2 */}
        <div style={{ background: 'var(--card)', borderRadius: '20px', padding: '20px', border: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{ background: 'rgba(48,209,88,0.15)', padding: '10px', borderRadius: '12px' }}>
              <Users size={20} color="#30D158" />
            </div>
            <h3 style={{ fontSize: '16px', fontWeight: '700', color: 'var(--text-primary)', margin: 0 }}>Foydalanuvchi majburiyatlari</h3>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {[
              'Botga haqiqiy va to\'g\'ri ma\'lumotlar kiritish',
              'Xizmatdan noqonuniy maqsadlarda foydalanmaslik',
              'Boshqa foydalanuvchilarning huquqlarini hurmat qilish',
              'Spam yoki zararli xabarlar yubormaslik'
            ].map((item, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 14px', background: 'var(--bg)', borderRadius: '12px' }}>
                <div style={{ width: '6px', height: '6px', borderRadius: '3px', background: '#30D158', flexShrink: 0 }} />
                <span style={{ fontSize: '14px', color: 'var(--text-primary)' }}>{item}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Section 3 */}
        <div style={{ background: 'var(--card)', borderRadius: '20px', padding: '20px', border: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{ background: 'rgba(255,159,10,0.15)', padding: '10px', borderRadius: '12px' }}>
              <AlertTriangle size={20} color="#FF9F0A" />
            </div>
            <h3 style={{ fontSize: '16px', fontWeight: '700', color: 'var(--text-primary)', margin: 0 }}>Javobgarlik chegarasi</h3>
          </div>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', lineHeight: '1.7', margin: 0 }}>
            Somly AI sun'iy intellekt yordamida moliyaviy ma'lumotlarni qayta ishlaydi. 
            Biz <strong style={{ color: 'var(--text-primary)' }}>professional moliyaviy maslahat bermaymiz</strong>. 
            Bot tomonidan taqdim etilgan barcha tahlillar faqat informatsion maqsadlarda. 
            Moliyaviy qarorlar uchun javobgarlik foydalanuvchining o'zida.
          </p>
        </div>

        {/* Section 4 */}
        <div style={{ background: 'var(--card)', borderRadius: '20px', padding: '20px', border: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{ background: 'rgba(255,69,58,0.15)', padding: '10px', borderRadius: '12px' }}>
              <Ban size={20} color="#FF453A" />
            </div>
            <h3 style={{ fontSize: '16px', fontWeight: '700', color: 'var(--text-primary)', margin: 0 }}>Xizmatni to'xtatish</h3>
          </div>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', lineHeight: '1.7', margin: 0 }}>
            Biz ushbu shartlarni buzgan foydalanuvchilarning hisobini <strong style={{ color: 'var(--text-primary)' }}>ogohlantirishsiz to'xtatish</strong> huquqini 
            saqlab qolamiz. Shuningdek, xizmat texnik sabablarga ko'ra vaqtincha to'xtatilishi mumkin.
          </p>
        </div>

        {/* Contact */}
        <div style={{ 
          background: 'linear-gradient(135deg, var(--primary-glow) 0%, rgba(90,200,250,0.1) 100%)', 
          borderRadius: '20px', padding: '20px', 
          border: '1px solid rgba(10,132,255,0.2)',
          textAlign: 'center'
        }}>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary)', lineHeight: '1.6', margin: '0 0 16px' }}>
            Savollar yoki takliflar uchun biz bilan bog'laning:
          </p>
          <button 
            onClick={() => window.Telegram?.WebApp?.openTelegramLink('https://t.me/XusniddinWR') || window.open('https://t.me/XusniddinWR', '_blank')}
            style={{ 
              background: 'var(--primary)', color: '#fff', border: 'none', 
              padding: '12px 24px', borderRadius: '14px', 
              fontSize: '15px', fontWeight: '600', cursor: 'pointer',
              boxShadow: '0 8px 24px var(--primary-glow)'
            }}
          >
            @XusniddinWR ga yozish
          </button>
        </div>
      </div>
    </div>
  );
};

export default TermsPage;
