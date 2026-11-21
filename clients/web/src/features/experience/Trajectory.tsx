import { useEffect, useState } from 'react';
import type { AgentRun, Trajectory as TrajectoryView } from '../../shared/contracts';
import type { ExperienceFeature } from './factory';

const reasonLabels: Record<string, string> = {
  run_not_at_recovery_boundary: '任务未处于可恢复的安全边界',
  checkpoint_schema_incompatible: '检查点版本不兼容',
  checkpoint_reference_invalid: '检查点来源校验失败',
  source_evidence_missing_or_unavailable: '原始证据缺失或已不可用',
  projection_behind: '投影尚未追平当前任务',
  tool_reconciliation_required: '请先对账未知工具结果',
  trace_limit: '轨迹超过本次查询上限',
};

export function Trajectory({
  feature,
  run,
  onRecovered,
}: {
  feature: ExperienceFeature;
  run: AgentRun;
  onRecovered: (run: AgentRun) => void;
}) {
  const [view, setView] = useState<TrajectoryView | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let live = true;
    setView(null);
    setLoading(true);
    setError('');
    feature
      .trajectory(run.command.project_id, run.id)
      .then((value) => {
        if (live) {
          setView(value);
          setLoading(false);
        }
      })
      .catch((e: Error) => {
        if (live) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      live = false;
    };
  }, [feature, run.id, run.version, run.command.project_id, refresh]);
  async function recover() {
    if (!view?.checkpoint) return;
    setBusy(true);
    setError('');
    try {
      onRecovered(
        await feature.recover(run.command.project_id, run.id, {
          request_id: crypto.randomUUID(),
          expected_version: view.checkpoint.version,
          expected_goal_revision: run.goal_revision,
          checkpoint_event_id: view.checkpoint.event_id,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : '恢复被拒绝');
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="trajectory-view" aria-label="任务轨迹与恢复">
      <h3>轨迹与恢复</h3>
      {loading && <p>正在核对原始事件与检查点…</p>}
      {error && <p role="alert">{error}</p>}
      {view && (
        <>
          <p>
            投影{view.caught_up ? '已追平' : '正在追赶'} · 事件游标 {view.processing_cursor} ·{' '}
            {view.nodes.length} 条任务事件
          </p>
          <p className="module-note">
            确认用量：{view.tokens_used ?? '未知'} tokens /{' '}
            {view.cost_microusd === null ? '未知' : `$${(view.cost_microusd / 1000000).toFixed(6)}`}
            。{view.usage_complete ? '没有已知未决用量。' : '存在未知或未确认用量。'}{' '}
            独立语义质量尚未评估。
          </p>
          <p>
            检查点版本 {view.checkpoint?.version ?? '未知'} · 恢复
            {view.recovery_available ? '可用' : '暂不可用'}
          </p>
          {view.recovery_reasons.length > 0 && (
            <p className="module-note">
              {view.recovery_reasons.map((reason) => reasonLabels[reason] ?? reason).join('、')}
            </p>
          )}
          {view.missing_references.length > 0 && (
            <details>
              <summary>缺失或不可用的证据</summary>
              <pre className="tool-output">{view.missing_references.join('\n')}</pre>
            </details>
          )}
          <button
            className="secondary-button"
            disabled={busy || loading}
            onClick={() => setRefresh((v) => v + 1)}
          >
            刷新轨迹
          </button>
          <button
            className="secondary-button"
            disabled={busy || !view.recovery_available || view.checkpoint?.version !== run.version}
            onClick={() => void recover()}
          >
            从已核对检查点恢复
          </button>
          <details>
            <summary>展开事件时间线</summary>
            <ol className="trajectory-events">
              {view.nodes.map((n) => (
                <li key={n.id}>
                  <details>
                    <summary>
                      #{n.cursor} · {n.kind}
                      {n.late_revision_result ? ' · 旧修订晚到结果' : ''}
                    </summary>
                    <p>
                      事件时间：{n.event_time}
                      <br />
                      处理时间：{n.processed_at || '旧版本未记录'}
                      <br />
                      来源：{n.source} · 事件目标修订 {n.goal_revision}
                    </p>
                    <pre className="tool-output">{JSON.stringify(n.details, null, 2)}</pre>
                  </details>
                </li>
              ))}
            </ol>
          </details>
          <details>
            <summary>来源关联与检查点摘要</summary>
            <pre className="tool-output">
              {JSON.stringify(
                {
                  checkpoint: view.checkpoint,
                  state: view.checkpoint_state,
                  episodes: view.episodes,
                  edges: view.edges,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </>
      )}
    </div>
  );
}
