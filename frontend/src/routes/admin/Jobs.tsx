import { useEffect, useId, useState } from 'react';
import { AdminShell, Card, Button, Field, Pill } from '../../ui';
import { api } from '../../lib/api';
import type { Job, JobStatus, InterviewerVoice } from '../../types';

const VOICE_OPTIONS: InterviewerVoice[] = [
  'Serena', 'Sunny', 'Kiki', 'Tina', 'Ethan', 'Dylan', 'Peter', 'Aiden',
];

const STATUS_COLOR: Record<JobStatus, string> = {
  active: '#2BE5A4',
  draft: '#FACC15',
  closed: '#8593AD',
};

const STATUS_LABEL: Record<JobStatus, string> = {
  active: '进行中',
  draft: '草稿',
  closed: '已关闭',
};

interface FormState {
  title: string;
  jd: string;
  interviewer_voice: InterviewerVoice;
  language: string;
  duration_minutes: string;
  status: JobStatus;
}

const EMPTY_FORM: FormState = {
  title: '',
  jd: '',
  interviewer_voice: 'Serena',
  language: 'zh',
  duration_minutes: '30',
  status: 'draft',
};

function jobToForm(job: Job): FormState {
  return {
    title: job.title,
    jd: job.jd,
    interviewer_voice: job.interviewer_voice,
    language: job.language,
    duration_minutes: String(job.duration_minutes),
    status: job.status,
  };
}

interface JobFormProps {
  initial: FormState;
  onSave: (f: FormState) => Promise<void>;
  onCancel: () => void;
  saving: boolean;
}

function JobForm({ initial, onSave, onCancel, saving }: JobFormProps) {
  const [form, setForm] = useState<FormState>(initial);
  const selectId = useId();
  const langId = useId();
  const statusId = useId();
  const voiceId = useId();
  const inputStyle: React.CSSProperties = {
    background: '#0E1525',
    border: '1px solid #243049',
    borderRadius: 14,
    padding: '12px 16px',
    color: '#E8EEF9',
    fontSize: 14,
    width: '100%',
    boxSizing: 'border-box',
    outline: 'none',
  };

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); void onSave(form); }}
      className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4"
    >
      <Field
        label="职位名称"
        value={form.title}
        onChange={(e) => setForm({ ...form, title: e.target.value })}
        placeholder="例：前端工程师"
      />

      <div className="flex flex-col gap-1.5">
        <label htmlFor={voiceId} className="text-sm font-medium text-muted">面试官音色</label>
        <select
          id={voiceId}
          value={form.interviewer_voice}
          onChange={(e) => setForm({ ...form, interviewer_voice: e.target.value as InterviewerVoice })}
          style={inputStyle}
        >
          {VOICE_OPTIONS.map((v) => <option key={v} value={v}>{v}</option>)}
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={langId} className="text-sm font-medium text-muted">语言</label>
        <select
          id={langId}
          value={form.language}
          onChange={(e) => setForm({ ...form, language: e.target.value })}
          style={inputStyle}
        >
          <option value="zh">中文</option>
          <option value="en">English</option>
        </select>
      </div>

      <Field
        label="时长（分钟）"
        value={form.duration_minutes}
        onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })}
        type="number"
        placeholder="30"
      />

      <div className="flex flex-col gap-1.5">
        <label htmlFor={statusId} className="text-sm font-medium text-muted">状态</label>
        <select
          id={statusId}
          value={form.status}
          onChange={(e) => setForm({ ...form, status: e.target.value as JobStatus })}
          style={inputStyle}
        >
          <option value="draft">草稿</option>
          <option value="active">进行中</option>
          <option value="closed">已关闭</option>
        </select>
      </div>

      <div className="flex flex-col gap-1.5 md:col-span-2">
        <label htmlFor={selectId} className="text-sm font-medium text-muted">职位描述 (JD)</label>
        <textarea
          id={selectId}
          value={form.jd}
          onChange={(e) => setForm({ ...form, jd: e.target.value })}
          placeholder="请输入职位描述…"
          rows={4}
          style={{ ...inputStyle, resize: 'vertical' }}
        />
      </div>

      <div className="flex gap-3 md:col-span-2">
        <Button type="submit" disabled={saving}>{saving ? '保存中…' : '保存'}</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>取消</Button>
      </div>
    </form>
  );
}

export default function Jobs() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingJob, setEditingJob] = useState<Job | null>(null);
  const [saving, setSaving] = useState(false);

  function loadJobs() {
    setLoading(true);
    api.listJobs()
      .then((data) => { setJobs(data); setLoading(false); })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '加载失败');
        setLoading(false);
      });
  }

  useEffect(() => { loadJobs(); }, []);

  async function handleSave(form: FormState) {
    setSaving(true);
    const body = {
      title: form.title,
      jd: form.jd,
      interviewer_voice: form.interviewer_voice,
      language: form.language,
      duration_minutes: Number(form.duration_minutes),
      status: form.status,
    };
    try {
      if (editingJob) {
        await api.updateJob(editingJob.id, body);
      } else {
        await api.createJob(body);
      }
      setShowForm(false);
      setEditingJob(null);
      loadJobs();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '操作失败');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    if (!window.confirm('确认删除此职位？')) return;
    try {
      await api.deleteJob(id);
      loadJobs();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  }

  return (
    <AdminShell active="职位管理">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-text">职位管理</h1>
          <p className="text-sm text-muted mt-1">管理面试职位与配置</p>
        </div>
        <Button
          onClick={() => { setEditingJob(null); setShowForm((v) => !v); }}
        >
          + 新建职位
        </Button>
      </div>

      {error && <p className="text-red text-sm mb-4">错误：{error}</p>}

      {(showForm && !editingJob) && (
        <Card className="mb-6">
          <h2 className="text-sm font-semibold text-text">新建职位</h2>
          <JobForm
            initial={EMPTY_FORM}
            onSave={handleSave}
            onCancel={() => setShowForm(false)}
            saving={saving}
          />
        </Card>
      )}

      {loading && <p className="text-muted text-sm">加载中…</p>}

      {!loading && jobs.length === 0 && (
        <Card>
          <p className="text-muted text-sm text-center py-8">暂无职位，点击"新建职位"创建第一个职位。</p>
        </Card>
      )}

      <div className="flex flex-col gap-4">
        {jobs.map((job) => (
          <Card key={job.id}>
            {editingJob?.id === job.id ? (
              <>
                <h2 className="text-sm font-semibold text-text mb-2">编辑职位</h2>
                <JobForm
                  initial={jobToForm(job)}
                  onSave={handleSave}
                  onCancel={() => setEditingJob(null)}
                  saving={saving}
                />
              </>
            ) : (
              <div className="flex items-start gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="text-base font-semibold text-text">{job.title}</span>
                    <Pill color={STATUS_COLOR[job.status as JobStatus] ?? '#8593AD'}>
                      {STATUS_LABEL[job.status as JobStatus] ?? job.status}
                    </Pill>
                  </div>
                  <div className="flex flex-wrap gap-4 mt-2 text-xs text-muted">
                    <span>音色：{job.interviewer_voice}</span>
                    <span>语言：{job.language === 'zh' ? '中文' : 'English'}</span>
                    <span>时长：{job.duration_minutes} 分钟</span>
                    <span>题目：{job.question_count}</span>
                    <span>候选人：{job.candidate_count}</span>
                  </div>
                </div>
                <div className="flex gap-2 shrink-0">
                  <Button
                    variant="ghost"
                    onClick={() => { setEditingJob(job); setShowForm(false); }}
                  >
                    编辑
                  </Button>
                  <Button
                    variant="danger"
                    onClick={() => void handleDelete(job.id)}
                  >
                    删除
                  </Button>
                </div>
              </div>
            )}
          </Card>
        ))}
      </div>
    </AdminShell>
  );
}
