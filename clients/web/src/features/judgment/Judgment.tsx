import { useEffect, useState } from 'react';
import type { JudgmentInfo, JudgmentResult } from '../../shared/contracts';
import type { JudgmentFeature } from './factory';

const labels: Record<JudgmentInfo['health'], string> = {
  not_loaded: '已配置 · 按需加载',
  available: '最近推理成功',
  weights_missing: '尚未下载本地权重',
  unavailable: '最近推理失败',
  test_fixture: '测试替身',
};

const names: Record<string, string> = {
  sufficient: '信息充分性',
  executor: '执行模型档位',
  tool: '工具领域',
  skill: '工作模式',
  yes: '是',
  no: '否',
  small_2b: '约 2B 小模型',
  small_7b: '约 7B 小模型',
  strong: '强模型',
  none: '不需要工具',
  read: '读取资料',
  write: '文件与代码操作',
  general: '通用',
  research: '调研',
  engineering: '软件工程',
  proposed: '已有建议',
  blocked: '已阻塞',
  stale: '状态已过期',
  not_requested: '未请求选择模型',
  insufficient_information: '模型认为信息不足',
  no_eligible_executor: '没有符合权限与能力要求的执行模型',
  local_executor_not_registered: '尚未注册本地执行模型',
  eligible_stronger_executor: '建议使用允许的更强模型',
  eligible_requested_tier: '执行模型符合所需档位',
  state_truncated: '输入超过上下文限额',
  invalid_provider_answer: '模型返回的答案不符合契约',
};
const label = (value: string) => names[value] ?? value;

export function Judgment({ feature }: { feature: JudgmentFeature }) {
  const [info, setInfo] = useState<JudgmentInfo | null>(null);
  const [state, setState] = useState('请计算 1 加 1，只返回结果。');
  const [isPublic, setPublic] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<JudgmentResult | null>(null);
  useEffect(() => {
    let live = true;
    feature
      .info()
      .then((value) => {
        if (live) setInfo(value);
      })
      .catch(() => {
        if (live) setError('判断状态读取失败');
      });
    return () => {
      live = false;
    };
  }, [feature]);
  async function preview() {
    setBusy(true);
    setError('');
    setResult(null);
    try {
      setResult(await feature.preview(state, isPublic, crypto.randomUUID()));
      setInfo(await feature.info());
    } catch (error) {
      setError(error instanceof Error ? error.message : '本地判断失败');
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="settings-card">
      <h2>本地判断 · Laya</h2>
      <p className="module-note">
        当前只走配置的本地判断来源。以下操作生成建议，不执行任务；决策分数不代表任务成功率。自动采用需先通过本领域质量评估。
      </p>
      <dl>
        <div>
          <dt>状态</dt>
          <dd>{info ? labels[info.health] : '正在读取…'}</dd>
        </div>
        <div>
          <dt>Checkpoint</dt>
          <dd>{info?.checkpoint ?? '未知'}</dd>
        </div>
        <div>
          <dt>版本</dt>
          <dd>{info?.revision ?? '未知'}</dd>
        </div>
        <div>
          <dt>采用权限</dt>
          <dd>
            {info?.application_enabled ? '固定策略授权后可采用' : '建议模式 · 未开放自动采用'}
          </dd>
        </div>
      </dl>
      <label className="judgment-label" htmlFor="judgment-state">
        待判断任务
      </label>
      <textarea
        id="judgment-state"
        className="judgment-input"
        value={state}
        onChange={(event) => setState(event.target.value)}
        maxLength={12000}
        rows={3}
        disabled={busy}
      />
      <label className="judgment-check">
        <input
          type="checkbox"
          checked={isPublic}
          onChange={(event) => setPublic(event.target.checked)}
          disabled={busy}
        />
        该输入是公开数据，可考虑已授权的云端执行模型
      </label>
      <button
        className="secondary-button"
        disabled={busy || !state.trim() || info?.health === 'weights_missing'}
        onClick={() => void preview()}
      >
        {busy ? '本地判断中…' : '预览本地判断'}
      </button>
      {error && (
        <p className="notice-banner" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div role="status" className="judgment-result">
          <p>
            {result.source.source === 'test' ? '测试判断' : '真实本地判断'} ·{' '}
            {result.source.provider} · {result.source.runtime_version} · {result.latency_ms} ms
          </p>
          <p>
            建议状态：{label(result.route.status)} · {result.route.model_id ?? '没有执行候选'} ·{' '}
            {result.adopted ? '已采用' : '未采用'}
          </p>
          {result.route.reason_codes.length > 0 && (
            <p>{result.route.reason_codes.map(label).join(' · ')}</p>
          )}
          <dl>
            {result.answers.map((answer) => (
              <div key={label(answer.question_id)}>
                <dt>{label(answer.question_id)}</dt>
                <dd>
                  {label(answer.selected_id ?? answer.reason ?? answer.status)}
                  {answer.confidence !== null && ` · 分数 ${answer.confidence.toFixed(4)}`}
                </dd>
              </div>
            ))}
          </dl>
          <p className="module-note">
            输入截止点 {result.state_cutoff} · 目标修订 {result.goal_revision}
            。原始响应已留在本机事件日志，不能作为已验证的训练标签。
          </p>
        </div>
      )}
    </section>
  );
}
