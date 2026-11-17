import { useEffect, useState } from 'react';
import type { ModelInfo, ModelResult } from '../../shared/contracts';
import type { ModelFeature } from './factory';

const healthLabels: Record<ModelInfo['health'], string> = {
  not_checked: '尚未检测',
  available: '最近请求成功',
  unavailable: '最近请求失败',
  credential_missing: '未配置凭据',
  test_fixture: '测试替身',
};

export function Models({ feature }: { feature: ModelFeature }) {
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, ModelResult>>({});
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let live = true;
    feature
      .catalog()
      .then((value) => {
        if (live) setModels(value);
      })
      .catch((error: Error) => {
        if (live) setError(error.message);
      });
    return () => {
      live = false;
    };
  }, [feature, reload]);
  async function probe(modelId: string) {
    setBusy(modelId);
    setError('');
    try {
      const result = await feature.probe(modelId, crypto.randomUUID());
      setResults((previous) => ({ ...previous, [modelId]: result }));
      setReload((value) => value + 1);
    } catch (error) {
      setError(error instanceof Error ? error.message : '检测失败');
    } finally {
      setBusy(null);
    }
  }
  return (
    <section className="module-page">
      <p className="eyebrow">执行模型 · M04</p>
      <h1>模型</h1>
      <p className="module-description">连接执行模型，查看能力、实际返回版本与调用用量。</p>
      <p className="module-note">
        连接检测只发送固定的公开短句，会产生少量费用并计入预算。主对话仍为框架演示。本地 Laya
        判断见页面下方。
      </p>
      {error && (
        <div role="alert" className="notice-banner">
          {error}
          <button
            className="secondary-button"
            onClick={() => {
              setError('');
              setReload((value) => value + 1);
            }}
          >
            刷新连接
          </button>
        </div>
      )}
      {!models && !error && <p role="status">正在加载模型…</p>}
      {models?.length === 0 && <p>尚未注册模型</p>}
      {models?.map((model) => (
        <article className="settings-card" key={model.id}>
          <h2>{model.id}</h2>
          <dl>
            <div>
              <dt>状态</dt>
              <dd>{healthLabels[model.health]}</dd>
            </div>
            <div>
              <dt>来源</dt>
              <dd>
                {model.capability_source === 'test-fixture'
                  ? '测试替身 · 无真实推理'
                  : 'DeepSeek 云端 · 能力由供应商声明'}
              </dd>
            </div>
            <div>
              <dt>声明版本</dt>
              <dd>
                {model.declared_revision}
                {!model.revision_is_pinned && ' · 服务别名可能更新'}
              </dd>
            </div>
            <div>
              <dt>上下文 / 输出上限</dt>
              <dd>
                {model.context_tokens.toLocaleString()} / {model.max_output_tokens.toLocaleString()}{' '}
                tokens
              </dd>
            </div>
            <div>
              <dt>声明上下文</dt>
              <dd>{model.declared_context_tokens.toLocaleString()} tokens · 当前保守限额另计</dd>
            </div>
            <div>
              <dt>协议能力</dt>
              <dd>{model.capabilities.join(' · ')}</dd>
            </div>
            <div>
              <dt>费用基线</dt>
              <dd>{model.price_revision} · 按峰值公开价格估算，实际账单以供应商为准</dd>
            </div>
          </dl>
          <button
            className="secondary-button"
            disabled={busy !== null || model.health === 'credential_missing'}
            onClick={() => void probe(model.id)}
          >
            {busy === model.id ? '检测中…' : `检测 ${model.id}`}
          </button>
          {results[model.id] && (
            <div role="status" className="model-result">
              <p>
                {results[model.id].source === 'test' ? '测试响应' : '真实模型响应'}：
                {results[model.id].content}
              </p>
              <p>
                返回版本 {results[model.id].reported_model} · {results[model.id].finish_reason} ·{' '}
                {results[model.id].latency_ms} ms
              </p>
              <p>
                输入 {results[model.id].usage.input_tokens} / 输出{' '}
                {results[model.id].usage.output_tokens} tokens · 估算 $
                {(results[model.id].usage.estimated_cost_microusd / 1000000).toFixed(6)}
              </p>
            </div>
          )}
        </article>
      ))}
    </section>
  );
}
