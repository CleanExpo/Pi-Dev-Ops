// @ts-nocheck
"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeftMark, PlusMark, CloseMark, ExternalMark } from "@/components/ui/marks";
import { supabaseClient } from "@/lib/supabase/client";
import { EmptyState } from "@/components/ui/EmptyState";

interface Client {
  id: string;
  name: string;
  email: string;
  company: string | null;
  country: string | null;
  total_arr_aud: number;
  product_count: number;
  uses_synthex: boolean;
  uses_restore_assist: boolean;
  uses_ccw_crm: boolean;
  uses_carsi: boolean;
  created_at: string;
}

const EMPTY_FORM = { name: '', email: '', company: '', country: 'AU', phone: '' };

export default function ClientsDirectory() {
  const router = useRouter();
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    supabaseClient.auth.getSession().then(({ data: { session } }) => {
      if (!session) router.push('/en/login');
    });
  }, [router]);

  const fetchClients = async () => {
    setLoading(true);
    const { data, error } = await supabaseClient
      .from('unified_customers')
      .select('*')
      .order('created_at', { ascending: false });
    if (!error && data) setClients(data as Client[]);
    setLoading(false);
  };

  useEffect(() => { if (mounted) fetchClients(); }, [mounted]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const { error: insertErr } = await supabaseClient
      .from('unified_customers')
      .insert([{ name: form.name, email: form.email, company: form.company || null, country: form.country, phone: form.phone || null }]);
    if (insertErr) {
      setError(insertErr.message);
    } else {
      setShowAdd(false);
      setForm(EMPTY_FORM);
      fetchClients();
    }
    setSaving(false);
  };

  if (!mounted) return null;

  const inputStyle = {
    width: '100%', padding: '8px 12px', fontSize: 13, borderRadius: 8,
    border: '1px solid #27272a', background: 'var(--surface-1)', color: 'var(--ink-primary)',
    outline: 'none', fontFamily: 'var(--font-display)',
    transition: 'border-color 0.1s ease',
  } as React.CSSProperties;

  return (
    <div style={{ minHeight: '100vh', background: 'var(--canvas)', color: 'var(--ink-primary)' }}>
      {/* Header */}
      <header style={{ height: 60, display: 'flex', alignItems: 'center', padding: '0 24px', borderBottom: '1px solid #27272a', position: 'sticky', top: 0, background: 'rgba(9,9,11,0.9)', backdropFilter: 'blur(20px)', zIndex: 40 }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', width: '100%', display: 'flex', alignItems: 'center', gap: 16 }}>
          <Link href="/ceo" style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#52525b', textDecoration: 'none', fontSize: 12 }}
            onMouseEnter={e => (e.currentTarget.style.color = 'var(--ink-secondary)')}
            onMouseLeave={e => (e.currentTarget.style.color = '#52525b')}
          >
            <ArrowLeftMark size={12} /> Command Center
          </Link>
          <span style={{ color: 'var(--border-default)' }}>·</span>
          <h1 style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink-primary)', letterSpacing: '-0.02em', margin: 0, fontFamily: 'var(--font-display)' }}>Clients</h1>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: '#52525b' }}>{clients.length} total</span>
          <div style={{ flex: 1 }} />
          <button
            onClick={() => setShowAdd(true)}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', fontSize: 12, fontWeight: 500, borderRadius: 8, border: '1px solid #1d4ed8', color: '#fff', background: 'var(--red-500)', cursor: 'pointer', transition: 'background 0.1s' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--red-400)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'var(--red-500)')}
          >
            <PlusMark size={13} /> Add Client
          </button>
        </div>
      </header>

      <main style={{ maxWidth: 1200, margin: '0 auto', padding: '24px' }}>

        {/* Active Portals — split from `clients` by uses_ccw_crm flag.
            UNI-1947 Pillar 2: the previous hardcoded CCW JSX is gone; the
            row now comes from unified_customers like every other client. */}
        {(() => {
          const activePortals = clients.filter(c => c.uses_ccw_crm);
          if (activePortals.length === 0) {
            return null; // nothing to render — skip the section entirely
          }
          return (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#52525b', marginBottom: 10 }}>Active Portals</div>
              {activePortals.map(client => (
                <Link key={client.id} href="/clients/ccw" style={{ textDecoration: 'none' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '14px 20px', background: 'var(--surface-1)', backgroundImage: 'linear-gradient(180deg,rgba(255,255,255,0.025) 0%,transparent 50%)', border: '1px solid #27272a', borderRadius: 10, transition: 'border-color 0.1s' }}
                    onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--ink-tertiary)')}
                    onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border-default)')}
                  >
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#dc2626', display: 'inline-block' }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink-primary)', letterSpacing: '-0.02em' }}>{client.company ?? client.name}</div>
                      <div style={{ fontSize: 11, color: '#52525b', marginTop: 2 }}>
                        {client.total_arr_aud > 0 ? `$${client.total_arr_aud.toLocaleString()}/yr ARR` : 'CRM portal active'}
                      </div>
                    </div>
                    <span style={{ fontSize: 10, fontWeight: 600, color: '#16a34a', letterSpacing: '0.04em', textTransform: 'uppercase', padding: '2px 8px', borderRadius: 4, background: 'rgba(22,163,74,0.1)', border: '1px solid rgba(22,163,74,0.2)' }}>Active</span>
                    <ExternalMark size={12} color="#52525b" />
                  </div>
                </Link>
              ))}
            </div>
          );
        })()}

        {/* Unified customers from DB */}
        <div style={{ marginTop: 24 }}>
          <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#52525b', marginBottom: 10 }}>All Clients</div>

          {loading ? (
            <div style={{ background: 'var(--surface-1)', border: '1px solid #27272a', borderRadius: 10, overflow: 'hidden' }}>
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="skeleton" style={{ height: 54, borderBottom: i < 2 ? '1px solid #27272a' : 'none' }} />
              ))}
            </div>
          ) : clients.length === 0 ? (
            <EmptyState
              title="No clients yet"
              description="Add your first client to start tracking ARR, portals, and engagements."
            />
          ) : (
            <div style={{ background: 'var(--surface-1)', border: '1px solid #27272a', borderRadius: 10, overflow: 'hidden' }}>
              {clients.map((client, i) => (
                <motion.div
                  key={client.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.04 }}
                  style={{
                    display: 'grid', gridTemplateColumns: '1fr 160px 100px 80px',
                    alignItems: 'center', gap: 16, padding: '13px 20px',
                    borderBottom: i < clients.length - 1 ? '1px solid #27272a' : 'none',
                  }}
                >
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#d4d4d8', letterSpacing: '-0.01em' }}>{client.name}</div>
                    <div style={{ fontSize: 11, color: '#52525b', marginTop: 2 }}>{client.company ?? client.email}</div>
                  </div>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--ink-secondary)' }}>{client.email}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: client.total_arr_aud > 0 ? '#16a34a' : '#52525b' }}>
                    {client.total_arr_aud > 0 ? `$${client.total_arr_aud.toLocaleString()}` : '—'}
                  </span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: '#52525b', letterSpacing: '0.04em', textTransform: 'uppercase' }}>{client.country ?? 'AU'}</span>
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </main>

      {/* Add Client slide-in panel */}
      <AnimatePresence>
        {showAdd && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              onClick={() => setShowAdd(false)}
              style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 49 }}
            />
            {/* Panel */}
            <motion.div
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
              transition={{ ease: [0.23, 1, 0.32, 1], duration: 0.3 }}
              style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 400, background: 'var(--surface-1)', borderLeft: '1px solid #27272a', zIndex: 50, display: 'flex', flexDirection: 'column' }}
            >
              {/* Panel header */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '20px 24px', borderBottom: '1px solid #27272a' }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink-primary)', letterSpacing: '-0.02em', fontFamily: 'var(--font-display)' }}>Add Client</span>
                <button onClick={() => setShowAdd(false)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', padding: 4 }}>
                  <CloseMark size={16} color="#52525b" />
                </button>
              </div>

              {/* Form */}
              <form onSubmit={handleAdd} style={{ flex: 1, padding: 24, display: 'flex', flexDirection: 'column', gap: 16, overflowY: 'auto' }}>
                {error && (
                  <div style={{ padding: '10px 14px', borderRadius: 8, background: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.2)', fontSize: 12, color: '#dc2626' }}>
                    {error}
                  </div>
                )}

                {[
                  { key: 'name',    label: 'Full Name',     type: 'text',  required: true,  placeholder: 'Jane Smith' },
                  { key: 'email',   label: 'Email Address', type: 'email', required: true,  placeholder: 'jane@company.com.au' },
                  { key: 'company', label: 'Company',       type: 'text',  required: false, placeholder: 'Company Pty Ltd' },
                  { key: 'phone',   label: 'Phone',         type: 'tel',   required: false, placeholder: '+61 4xx xxx xxx' },
                ].map(field => (
                  <div key={field.key} style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    <label style={{ fontSize: 11, fontWeight: 500, color: 'var(--ink-secondary)' }}>
                      {field.label}{field.required && <span style={{ color: '#dc2626' }}> *</span>}
                    </label>
                    <input
                      type={field.type}
                      required={field.required}
                      placeholder={field.placeholder}
                      value={form[field.key as keyof typeof form]}
                      onChange={e => setForm(f => ({ ...f, [field.key]: e.target.value }))}
                      style={inputStyle}
                      onFocus={e => (e.target.style.borderColor = 'var(--red-500)')}
                      onBlur={e => (e.target.style.borderColor = 'var(--border-default)')}
                    />
                  </div>
                ))}

                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  <label style={{ fontSize: 11, fontWeight: 500, color: 'var(--ink-secondary)' }}>Country</label>
                  <select
                    value={form.country}
                    onChange={e => setForm(f => ({ ...f, country: e.target.value }))}
                    style={{ ...inputStyle, cursor: 'pointer' }}
                  >
                    <option value="AU">Australia (AU)</option>
                    <option value="NZ">New Zealand (NZ)</option>
                    <option value="US">United States (US)</option>
                    <option value="GB">United Kingdom (GB)</option>
                    <option value="CA">Canada (CA)</option>
                  </select>
                </div>

                <div style={{ marginTop: 'auto', display: 'flex', gap: 10 }}>
                  <button
                    type="button" onClick={() => setShowAdd(false)}
                    style={{ flex: 1, padding: '9px 0', fontSize: 13, fontWeight: 500, borderRadius: 8, border: '1px solid #27272a', color: 'var(--ink-secondary)', background: 'transparent', cursor: 'pointer' }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit" disabled={saving}
                    style={{ flex: 2, padding: '9px 0', fontSize: 13, fontWeight: 500, borderRadius: 8, border: 'none', color: '#fff', background: saving ? 'var(--ink-tertiary)' : 'var(--red-500)', cursor: saving ? 'not-allowed' : 'pointer', transition: 'background 0.1s' }}
                    onMouseEnter={e => { if (!saving) (e.currentTarget as HTMLButtonElement).style.background = 'var(--red-400)'; }}
                    onMouseLeave={e => { if (!saving) (e.currentTarget as HTMLButtonElement).style.background = 'var(--red-500)'; }}
                  >
                    {saving ? 'Adding…' : 'Add Client'}
                  </button>
                </div>
              </form>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
