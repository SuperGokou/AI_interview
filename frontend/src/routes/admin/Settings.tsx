import { useEffect, useState } from 'react';
import { AdminShell, Card } from '../../ui';
import { api } from '../../lib/api';
import type { HealthResponse } from '../../types';

const VOICES = ['Serena', 'Sunny', 'Kiki', 'Tina', 'Ethan', 'Dylan', 'Peter', 'Aiden'];

interface StatusRowProps {
  label: string;
  ok: boolean;
  okText?: string;
  badText?: string;
}

function StatusRow({ label, ok, okText = '正常', badText = '未配置' }: StatusRowProps) {
  const color = ok ? '#2BE5A4' : '#FB5070';
  return (
    <div className="flex items-center justify-between py-3 border-b border-border last:border-0">
      <span className="text-muted text-sm">{label}</span>
      <span className="flex items-center gap-2 text-sm font-medium" style={{ color }}>
        <span className="w-2 h-2 rounded-full" style={{ background: color }} />
        {ok ? okText : badText}
      </span>
    </div>
  );
}

export default function Settings() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .health()
      .then((h) => alive && setHealth(h))
      .catch(() => alive && setErr(true));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <AdminShell active="设置">
      <div className="max-w-3xl">
        <h1 className="text-2xl font-bold text-text mb-1">设置</h1>
        <p className="text-muted text-sm mb-6">系统状态与面试默认配置</p>

        <Card className="p-6 mb-5">
          <h2 className="text-base font-semibold text-text mb-2">系统状态</h2>
          {err && (
            <p className="text-[#FB5070] text-sm py-2">无法获取系统状态(后端未连接)</p>
          )}
          <StatusRow
            label="数据库 (Supabase Postgres)"
            ok={health?.database === 'up'}
            okText="已连接"
            badText="未连接"
          />
          <StatusRow label="Qwen-Omni 实时模型" ok={!!health?.models?.qwen} okText="已配置" />
          <StatusRow label="DeepSeek 评分模型" ok={!!health?.models?.deepseek} okText="已配置" />
        </Card>

        <Card className="p-6 mb-5">
          <h2 className="text-base font-semibold text-text mb-3">面试默认配置</h2>
          <div className="mb-4">
            <div className="text-muted text-sm mb-2">面试官音色(可在各职位单独设置)</div>
            <div className="flex flex-wrap gap-2">
              {VOICES.map((v) => (
                <span key={v} className="px-3 py-1 rounded-lg bg-surface2 text-text text-sm">
                  {v}
                </span>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
            <div>
              <span className="text-muted">默认语言:</span>{' '}
              <span className="text-text">中文 / English</span>
            </div>
            <div>
              <span className="text-muted">默认时长:</span>{' '}
              <span className="text-text">30 分钟</span>
            </div>
          </div>
        </Card>

        <Card className="p-6 mb-5">
          <h2 className="text-base font-semibold text-text mb-3">诚信检测说明</h2>
          <div className="flex flex-col gap-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#2BE5A4' }} />
              <span className="text-text">绿色 · 正常</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#FACC15' }} />
              <span className="text-text">黄色 · 警告(检出轻微异常)</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#FB5070' }} />
              <span className="text-text">红色 · 风险(疑似 AI 作弊,需人工复核)</span>
            </div>
          </div>
        </Card>

        <Card className="p-6">
          <h2 className="text-base font-semibold text-text mb-2">账号</h2>
          <div className="flex items-center justify-between">
            <span className="text-text text-sm">HR · 菜鸟庆</span>
            <span className="text-muted text-xs">HR 登录鉴权即将上线</span>
          </div>
        </Card>
      </div>
    </AdminShell>
  );
}
