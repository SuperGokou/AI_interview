import { useEffect, useId, useState } from 'react';
import { AdminShell, Card, Button, Field, Pill } from '../../ui';
import { api } from '../../lib/api';
import type { Job, Question, Difficulty } from '../../types';

const DIFFICULTY_COLOR: Record<Difficulty, string> = {
  '初级': '#2BE5A4',
  '中级': '#FACC15',
  '高级': '#FB5070',
};

interface QFormState {
  prompt: string;
  key_points: string;
  reference_answer: string;
  difficulty: Difficulty;
  is_probe: boolean;
}

const EMPTY_QFORM: QFormState = {
  prompt: '',
  key_points: '',
  reference_answer: '',
  difficulty: '初级',
  is_probe: false,
};

function questionToForm(q: Question): QFormState {
  return {
    prompt: q.prompt,
    key_points: q.key_points,
    reference_answer: q.reference_answer,
    difficulty: q.difficulty,
    is_probe: q.is_probe,
  };
}

interface QFormProps {
  initial: QFormState;
  onSave: (f: QFormState) => Promise<void>;
  onCancel: () => void;
  saving: boolean;
}

function QuestionForm({ initial, onSave, onCancel, saving }: QFormProps) {
  const [form, setForm] = useState<QFormState>(initial);
  const diffId = useId();
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
      <div className="flex flex-col gap-1.5 md:col-span-2">
        <label className="text-sm font-medium text-muted">题目描述</label>
        <textarea
          value={form.prompt}
          onChange={(e) => setForm({ ...form, prompt: e.target.value })}
          placeholder="请输入题目内容…"
          rows={3}
          style={{ ...inputStyle, resize: 'vertical' }}
        />
      </div>

      <Field
        label="考察要点"
        value={form.key_points}
        onChange={(e) => setForm({ ...form, key_points: e.target.value })}
        placeholder="考察的核心知识点"
      />

      <div className="flex flex-col gap-1.5">
        <label htmlFor={diffId} className="text-sm font-medium text-muted">难度</label>
        <select
          id={diffId}
          value={form.difficulty}
          onChange={(e) => setForm({ ...form, difficulty: e.target.value as Difficulty })}
          style={inputStyle}
        >
          <option value="初级">初级</option>
          <option value="中级">中级</option>
          <option value="高级">高级</option>
        </select>
      </div>

      <div className="flex flex-col gap-1.5 md:col-span-2">
        <label className="text-sm font-medium text-muted">参考答案</label>
        <textarea
          value={form.reference_answer}
          onChange={(e) => setForm({ ...form, reference_answer: e.target.value })}
          placeholder="参考答案…"
          rows={3}
          style={{ ...inputStyle, resize: 'vertical' }}
        />
      </div>

      <div className="flex items-center gap-3 md:col-span-2">
        <input
          type="checkbox"
          id="is_probe"
          checked={form.is_probe}
          onChange={(e) => setForm({ ...form, is_probe: e.target.checked })}
          className="w-4 h-4 accent-cyan"
        />
        <label htmlFor="is_probe" className="text-sm text-muted cursor-pointer">探针题（挑战性追问）</label>
      </div>

      <div className="flex gap-3 md:col-span-2">
        <Button type="submit" disabled={saving}>{saving ? '保存中…' : '保存'}</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>取消</Button>
      </div>
    </form>
  );
}

export default function Questions() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [loadingQ, setLoadingQ] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingQ, setEditingQ] = useState<Question | null>(null);
  const [saving, setSaving] = useState(false);
  const jobSelectId = useId();

  useEffect(() => {
    api.listJobs()
      .then((data) => { setJobs(data); setLoadingJobs(false); })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '加载职位失败');
        setLoadingJobs(false);
      });
  }, []);

  function loadQuestions(jobId: number) {
    setLoadingQ(true);
    api.listQuestions(jobId)
      .then((data) => { setQuestions(data); setLoadingQ(false); })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '加载题目失败');
        setLoadingQ(false);
      });
  }

  function handleSelectJob(id: number) {
    setSelectedJobId(id);
    setShowForm(false);
    setEditingQ(null);
    loadQuestions(id);
  }

  async function handleSave(form: QFormState) {
    if (!selectedJobId) return;
    setSaving(true);
    const body = {
      prompt: form.prompt,
      key_points: form.key_points,
      reference_answer: form.reference_answer,
      difficulty: form.difficulty,
      is_probe: form.is_probe,
    };
    try {
      if (editingQ) {
        await api.updateQuestion(editingQ.id, body);
      } else {
        await api.createQuestion(selectedJobId, body);
      }
      setShowForm(false);
      setEditingQ(null);
      loadQuestions(selectedJobId);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '操作失败');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: number) {
    if (!selectedJobId) return;
    if (!window.confirm('确认删除此题目？')) return;
    try {
      await api.deleteQuestion(id);
      loadQuestions(selectedJobId);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  }

  const inputStyle: React.CSSProperties = {
    background: '#0E1525',
    border: '1px solid #243049',
    borderRadius: 14,
    padding: '10px 16px',
    color: '#E8EEF9',
    fontSize: 14,
    minWidth: 220,
    outline: 'none',
  };

  return (
    <AdminShell active="题库管理">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-text">题库管理</h1>
          <p className="text-sm text-muted mt-1">管理各职位的面试题目</p>
        </div>
        {selectedJobId && (
          <Button onClick={() => { setEditingQ(null); setShowForm((v) => !v); }}>
            + 新建题目
          </Button>
        )}
      </div>

      {error && <p className="text-red text-sm mb-4">错误：{error}</p>}

      <Card className="mb-6">
        <div className="flex items-center gap-3 flex-wrap">
          <label htmlFor={jobSelectId} className="text-sm font-medium text-muted shrink-0">选择职位：</label>
          {loadingJobs ? (
            <span className="text-muted text-sm">加载职位中…</span>
          ) : (
            <select
              id={jobSelectId}
              value={selectedJobId ?? ''}
              onChange={(e) => {
                const val = Number(e.target.value);
                if (val) handleSelectJob(val);
              }}
              style={inputStyle}
            >
              <option value="">— 请选择职位 —</option>
              {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
            </select>
          )}
        </div>
      </Card>

      {selectedJobId && showForm && !editingQ && (
        <Card className="mb-6">
          <h2 className="text-sm font-semibold text-text">新建题目</h2>
          <QuestionForm
            initial={EMPTY_QFORM}
            onSave={handleSave}
            onCancel={() => setShowForm(false)}
            saving={saving}
          />
        </Card>
      )}

      {selectedJobId && loadingQ && <p className="text-muted text-sm">加载题目中…</p>}

      {selectedJobId && !loadingQ && questions.length === 0 && (
        <Card>
          <p className="text-muted text-sm text-center py-8">该职位暂无题目，点击"新建题目"添加。</p>
        </Card>
      )}

      <div className="flex flex-col gap-4">
        {questions.map((q) => (
          <Card key={q.id}>
            {editingQ?.id === q.id ? (
              <>
                <h2 className="text-sm font-semibold text-text mb-2">编辑题目</h2>
                <QuestionForm
                  initial={questionToForm(q)}
                  onSave={handleSave}
                  onCancel={() => setEditingQ(null)}
                  saving={saving}
                />
              </>
            ) : (
              <div className="flex items-start gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <Pill color={DIFFICULTY_COLOR[q.difficulty]}>{q.difficulty}</Pill>
                    {q.is_probe && (
                      <Pill color="#A78BFA" dot={false}>探针</Pill>
                    )}
                  </div>
                  <p className="text-sm text-text leading-relaxed">{q.prompt}</p>
                  {q.key_points && (
                    <p className="text-xs text-muted mt-1">考点：{q.key_points}</p>
                  )}
                </div>
                <div className="flex gap-2 shrink-0">
                  <Button
                    variant="ghost"
                    onClick={() => { setEditingQ(q); setShowForm(false); }}
                  >
                    编辑
                  </Button>
                  <Button
                    variant="danger"
                    onClick={() => void handleDelete(q.id)}
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
