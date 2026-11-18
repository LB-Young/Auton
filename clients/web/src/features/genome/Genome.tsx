import { useEffect, useState } from 'react';
import type { Asset, AssetRevision, Project, Snapshot, VersionInfo } from '../../shared/contracts';
import type { GenomeFeature } from './factory';

export function Genome({ feature }: { feature: GenomeFeature }) {
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [state, setState] = useState<AssetRevision | null>(null);
  const [projectId, setProjectId] = useState('');
  const [title, setTitle] = useState('项目资料');
  const [instructions, setInstructions] = useState('');
  const [id, setId] = useState('notes');
  const [name, setName] = useState('项目笔记');
  const [kind, setKind] = useState<Asset['kind']>('memory');
  const [origin, setOrigin] = useState<Asset['origin']>('user_explicit');
  const [source, setSource] = useState('用户显式录入');
  const [content, setContent] = useState('');
  const [expiry, setExpiry] = useState('');
  const [parents, setParents] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [versions, setVersions] = useState<VersionInfo[]>([]);
  const [historyAsset, setHistoryAsset] = useState('');
  const [diff, setDiff] = useState('');
  function update(value: AssetRevision) {
    setState(value);
    setProjectId(value.project.id);
    setSnapshot(null);
    setDiff('');
    setVersions([]);
  }
  useEffect(() => {
    let live = true;
    feature
      .projects()
      .then((items) => {
        if (live) setProjects(items);
        if (live) setLoading(false);
      })
      .catch((error: Error) => {
        if (live) {
          setError(error.message);
          setLoading(false);
        }
      });
    return () => {
      live = false;
    };
  }, [feature]);
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (error) {
      setError(error instanceof Error ? error.message : '资产操作失败');
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="module-page tool-page">
      <p className="eyebrow">项目资产 · M07</p>
      <h1>资产</h1>
      <p className="module-description">候选先审阅再晋升，按项目保存版本与来源。</p>
      <p className="module-note">
        资产文本不授予工具权限。撤回会阻止派生引用及旧快照被再次读取；Git
        历史用于审计，逻辑撤回不等于磁盘物理擦除。
      </p>
      {loading && <p role="status">正在读取项目资产…</p>}
      {error && (
        <p role="alert" className="notice-banner">
          {error}
        </p>
      )}
      <article className="settings-card">
        <h2>项目边界与说明</h2>
        <label className="judgment-label">
          已有项目
          <select
            aria-label="选择资产项目"
            disabled={busy}
            value={state?.project.id ?? ''}
            onChange={(event) => {
              if (event.target.value)
                void run(async () => update(await feature.view(event.target.value)));
            }}
          >
            <option value="">选择项目</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </label>
        <label className="judgment-label">
          新项目 ID
          <input
            aria-label="资产项目 ID"
            value={projectId}
            disabled={busy}
            onChange={(event) => setProjectId(event.target.value)}
          />
        </label>
        <label className="judgment-label">
          项目名称
          <input
            aria-label="资产项目名称"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <label className="judgment-label">
          项目说明
          <textarea
            aria-label="资产项目说明"
            className="judgment-input"
            value={instructions}
            onChange={(event) => setInstructions(event.target.value)}
          />
        </label>
        <button
          className="secondary-button"
          disabled={busy || !projectId}
          onClick={() =>
            void run(async () => {
              const value = await feature.create({ id: projectId, title, instructions });
              update(value);
              setProjects(await feature.projects());
            })
          }
        >
          创建资产项目
        </button>
        {state && (
          <p className="module-note">
            当前：{state.project.title} · {state.project.instructions || '未填写说明'}
            <br />
            正式版本 {state.revision}
          </p>
        )}
      </article>
      {state && (
        <>
          <article className="settings-card">
            <h2>学习候选</h2>
            <label className="judgment-label">
              上传 UTF-8 文本至候选区（最多 128 KiB，仍需审阅晋升）
              <input
                aria-label="上传项目文本"
                type="file"
                accept=".txt,.md,.json,.csv"
                disabled={busy}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = '';
                  if (file)
                    void run(async () => {
                      await feature.upload(state.project.id, file);
                      update(await feature.view(state.project.id));
                    });
                }}
              />
            </label>
            <label className="judgment-label">
              资产 ID
              <input
                aria-label="资产 ID"
                value={id}
                onChange={(event) => setId(event.target.value)}
              />
            </label>
            <label className="judgment-label">
              资产名称
              <input
                aria-label="资产名称"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="judgment-label">
              类别
              <select
                aria-label="资产类别"
                value={kind}
                onChange={(event) => setKind(event.target.value as Asset['kind'])}
              >
                {['memory', 'knowledge', 'document', 'skill', 'prompt', 'role'].map((kind) => (
                  <option key={kind}>{kind}</option>
                ))}
              </select>
            </label>
            <label className="judgment-label">
              来源类型
              <select
                aria-label="资产来源类型"
                value={origin}
                onChange={(event) => setOrigin(event.target.value as Asset['origin'])}
              >
                <option value="user_explicit">用户显式记忆</option>
                <option value="inferred">推断记忆</option>
                <option value="external">外部导入</option>
              </select>
            </label>
            <label className="judgment-label">
              来源引用
              <input
                aria-label="资产来源引用"
                value={source}
                onChange={(event) => setSource(event.target.value)}
              />
            </label>
            <label className="judgment-label">
              父资产 ID（逗号分隔）
              <input
                aria-label="父资产 ID"
                value={parents}
                onChange={(event) => setParents(event.target.value)}
              />
            </label>
            <label className="judgment-label">
              到期时间（可选）
              <input
                aria-label="资产到期时间"
                type="datetime-local"
                value={expiry}
                onChange={(event) => setExpiry(event.target.value)}
              />
            </label>
            <label className="judgment-label">
              候选内容
              <textarea
                aria-label="资产候选内容"
                className="judgment-input"
                rows={4}
                value={content}
                onChange={(event) => setContent(event.target.value)}
              />
            </label>
            <button
              className="secondary-button"
              disabled={busy || !content || !id}
              onClick={() =>
                void run(async () =>
                  update(
                    await feature.propose(
                      state.project.id,
                      {
                        id,
                        name,
                        kind,
                        content,
                        origin,
                        source,
                        parents: parents
                          .split(',')
                          .map((p) => p.trim())
                          .filter(Boolean),
                        expires_at: expiry ? new Date(expiry).toISOString() : null,
                        untrusted: true,
                      },
                      state.candidates_revision,
                    ),
                  ),
                )
              }
            >
              保存到学习候选
            </button>
            {state.candidates.length === 0 && <p>没有待晋升候选</p>}
            {state.candidates.map((record) => (
              <div key={record.asset.id} className="asset-record">
                <h3>{record.asset.name}</h3>
                <p className="module-note">
                  {record.asset.origin} · {record.asset.source} · 不可信文本
                </p>
                {state.assets.find((current) => current.asset.id === record.asset.id) && (
                  <>
                    <p>当前正式内容</p>
                    <pre className="tool-output">
                      {
                        state.assets.find((current) => current.asset.id === record.asset.id)?.asset
                          .content
                      }
                    </pre>
                  </>
                )}
                <p>候选内容</p>
                <pre className="tool-output">{record.asset.content}</pre>
                <button
                  className="secondary-button"
                  disabled={busy || !state.revision || !state.candidates_revision}
                  onClick={() =>
                    void run(async () =>
                      update(
                        await feature.change(
                          state.project.id,
                          record.asset.id,
                          'promote',
                          state.revision!,
                          state.candidates_revision,
                        ),
                      ),
                    )
                  }
                >
                  晋升 {record.asset.name}
                </button>
              </div>
            ))}
          </article>
          <article className="settings-card">
            <h2>正式资产</h2>
            {Object.entries(state.excluded).map(([identity, reason]) => (
              <p className="module-note" key={identity}>
                {identity} ·{' '}
                {reason === 'expired' ? '已过期' : reason === 'revoked' ? '已撤回' : '来源不可用'}
              </p>
            ))}
            {state.assets.length === 0 && <p>当前没有可用的正式资产</p>}
            {state.assets.map((record) => (
              <div key={record.asset.id} className="asset-record">
                <h3>{record.asset.name}</h3>
                <p className="module-note">
                  {record.asset.id} · {record.asset.kind} · {record.asset.origin} ·{' '}
                  {record.asset.source}
                </p>
                <pre className="tool-output">{record.asset.content}</pre>
                <button
                  className="secondary-button"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      setHistoryAsset(record.asset.id);
                      setVersions(await feature.history(state.project.id, record.asset.id));
                    })
                  }
                >
                  历史 {record.asset.name}
                </button>
                <button
                  className="secondary-button"
                  disabled={busy || !state.revision}
                  onClick={() =>
                    void run(async () =>
                      update(
                        await feature.change(
                          state.project.id,
                          record.asset.id,
                          'revoke',
                          state.revision!,
                          null,
                        ),
                      ),
                    )
                  }
                >
                  撤回 {record.asset.name} 及派生引用
                </button>
              </div>
            ))}
            <button
              className="secondary-button"
              disabled={busy}
              onClick={() =>
                void run(async () => setSnapshot(await feature.resolve(state.project.id)))
              }
            >
              生成使用快照
            </button>
            {snapshot && (
              <p role="status" className="module-note">
                快照 {snapshot.id} · {snapshot.assets.length} 个项目资产 · 不授予额外权限
              </p>
            )}
          </article>
        </>
      )}
      {state && versions.length > 0 && (
        <article className="settings-card">
          <h2>资产历史</h2>
          {versions.map((version) => (
            <div className="asset-record" key={version.revision}>
              <p className="module-note">
                {version.revision} · {version.origin} · {version.status}
              </p>
              <button
                className="secondary-button"
                disabled={busy}
                onClick={() =>
                  void run(async () =>
                    setDiff(await feature.diff(state.project.id, historyAsset, version.revision)),
                  )
                }
              >
                查看版本差异
              </button>
              <button
                className="secondary-button"
                disabled={busy || !state.revision}
                onClick={() =>
                  void run(async () =>
                    update(
                      await feature.change(
                        state.project.id,
                        historyAsset,
                        'rollback',
                        state.revision!,
                        version.revision,
                      ),
                    ),
                  )
                }
              >
                回退此版本
              </button>
            </div>
          ))}
          {diff && <pre className="tool-output">{diff}</pre>}
        </article>
      )}
    </section>
  );
}
