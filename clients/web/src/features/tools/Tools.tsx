import { useEffect, useState } from 'react';
import type { ToolDescriptor, ToolPlan, ToolReceipt, WorkspaceView } from '../../shared/contracts';
import type { ToolsFeature } from './factory';

export function Tools({ feature }: { feature: ToolsFeature }) {
  const [catalog, setCatalog] = useState<ToolDescriptor[] | null>(null);
  const [workspaces, setWorkspaces] = useState<WorkspaceView[]>([]);
  const [workspaceId, setWorkspaceId] = useState('');
  const [editable, setEditable] = useState(false);
  const [tool, setTool] = useState<ToolDescriptor['id']>('file.write');
  const [path, setPath] = useState('notes.md');
  const [content, setContent] = useState('# 本机工具验证\n');
  const [expected, setExpected] = useState('');
  const [program, setProgram] = useState('python.syntax_check');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [plan, setPlan] = useState<ToolPlan | null>(null);
  const [approval, setApproval] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<ToolReceipt | null>(null);
  const workspace = workspaces.find((item) => item.id === workspaceId);
  useEffect(() => {
    let live = true;
    Promise.all([feature.catalog(), feature.workspaces()])
      .then(([tools, scopes]) => {
        if (live) {
          setCatalog(tools);
          setWorkspaces(scopes);
          setWorkspaceId(scopes[0]?.id ?? '');
        }
      })
      .catch((error: Error) => {
        if (live) setError(error.message);
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
      setError(error instanceof Error ? error.message : '工具请求失败');
    } finally {
      setBusy(false);
    }
  }
  const locked = busy || plan !== null;
  return (
    <section className="module-page tool-page">
      <p className="eyebrow">工具宿主 · M06</p>
      <h1>工具</h1>
      <p className="module-description">先查看操作，批准后执行；结果不明时核对实际状态。</p>
      <p className="module-note">
        工具仅访问独立的本机工作目录。进程只开放 Python
        版本查询和语法检查，不执行输入代码。工具输出视为不可信内容。当前工作区归属跟随本次后端的浏览器会话。
      </p>
      {error && (
        <p role="alert" className="notice-banner">
          {error}
        </p>
      )}
      {!catalog && !error && <p role="status">正在连接工具宿主…</p>}
      <article className="settings-card">
        <h2>工作目录与权限</h2>
        {workspaces.length === 0 && <p>尚无工具工作区，请先建立一个明确权限的独立目录。</p>}
        <label className="judgment-label">
          当前工作区
          <select
            aria-label="工具工作区"
            value={workspaceId}
            disabled={locked}
            onChange={(event) => {
              setWorkspaceId(event.target.value);
              setReceipt(null);
            }}
          >
            <option value="">选择工作区</option>
            {workspaces.map((scope) => (
              <option key={scope.id} value={scope.id}>
                {scope.title} · {scope.read_only ? '只读' : '写入需审批'}
              </option>
            ))}
          </select>
        </label>
        <label className="judgment-check">
          <input
            type="checkbox"
            checked={editable}
            disabled={locked}
            onChange={(event) => setEditable(event.target.checked)}
          />
          允许新工作区申请写入与固定进程操作
        </label>
        <button
          className="secondary-button"
          disabled={locked}
          onClick={() =>
            void run(async () => {
              const value = await feature.createWorkspace(!editable);
              setWorkspaces((items) => [...items, value]);
              setWorkspaceId(value.id);
              setReceipt(null);
            })
          }
        >
          创建工具工作区
        </button>
        {workspace && (
          <p className="module-note">
            {workspace.read_only
              ? '只读任务不能写文件或启动进程。'
              : '操作限于这个独立目录，写入/进程仍须逐次审批。'}
          </p>
        )}
      </article>
      <article className="settings-card">
        <h2>准备操作</h2>
        <label className="judgment-label">
          工具
          <select
            aria-label="选择工具"
            value={tool}
            disabled={locked}
            onChange={(event) => {
              setTool(event.target.value as ToolDescriptor['id']);
              setReceipt(null);
            }}
          >
            {catalog?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
        {(tool === 'file.read' || tool === 'file.write') && (
          <label className="judgment-label">
            相对路径
            <input
              aria-label="工具文件路径"
              value={path}
              disabled={locked}
              onChange={(event) => setPath(event.target.value)}
            />
          </label>
        )}
        {tool === 'file.write' && (
          <label className="judgment-label">
            预期原文件 SHA256（新建留空）
            <input
              aria-label="预期文件摘要"
              value={expected}
              disabled={locked}
              onChange={(event) => setExpected(event.target.value)}
            />
          </label>
        )}
        {tool === 'process.run' && (
          <label className="judgment-label">
            固定程序
            <select
              aria-label="固定程序"
              disabled={locked}
              value={program}
              onChange={(event) => setProgram(event.target.value)}
            >
              <option value="python.syntax_check">Python 语法检查</option>
              <option value="python.version">Python 版本</option>
            </select>
          </label>
        )}
        {tool !== 'file.read' && (
          <label className="judgment-label">
            {tool === 'file.write'
              ? '文件内容'
              : tool === 'mcp.sha256'
                ? '待计算文本'
                : '待检查代码'}
            <textarea
              aria-label="工具输入内容"
              className="judgment-input"
              rows={5}
              value={content}
              disabled={locked}
              onChange={(event) => setContent(event.target.value)}
            />
          </label>
        )}
        <button
          className="secondary-button"
          disabled={locked || !workspaceId}
          onClick={() =>
            void run(async () => {
              const args =
                tool === 'file.write'
                  ? { path, content, expected_sha256: expected || null }
                  : tool === 'file.read'
                    ? { path }
                    : tool === 'process.run'
                      ? { program, source: content }
                      : { text: content };
              setReceipt(null);
              setApproval(null);
              setPlan(
                await feature.prepare({
                  operation_id: crypto.randomUUID(),
                  workspace_id: workspaceId,
                  tool,
                  arguments: args,
                }),
              );
            })
          }
        >
          准备并预览
        </button>
      </article>
      {plan && (
        <article className="settings-card">
          <h2>操作预览</h2>
          <p>
            {plan.title} · {plan.requires_approval ? '需要本次批准' : '允许只读执行'}
          </p>
          <pre className="tool-output">{plan.preview || '内容没有变化'}</pre>
          {plan.requires_approval && !approval && (
            <button
              className="secondary-button"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  setApproval((await feature.approve(plan.operation_id)).id);
                })
              }
            >
              批准本次操作
            </button>
          )}
          <button
            className="secondary-button"
            disabled={busy || (plan.requires_approval && !approval)}
            onClick={() =>
              void run(async () => {
                setReceipt(await feature.execute(plan.operation_id, approval));
                setPlan(null);
                setApproval(null);
              })
            }
          >
            {plan.requires_approval ? '执行已批准操作' : '执行只读操作'}
          </button>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => {
              setPlan(null);
              setApproval(null);
            }}
          >
            返回修改
          </button>
        </article>
      )}
      {receipt && (
        <article className="settings-card" role="status">
          <h2>执行凭据</h2>
          <p>
            {receipt.outcome === 'succeeded'
              ? '操作成功'
              : receipt.outcome === 'failed'
                ? '操作失败'
                : '结果未知 · 待对账'}{' '}
            · 尝试 {receipt.attempt}
            {receipt.reconciled && ' · 已核对实际文件状态'}
          </p>
          <p className="module-note">
            操作 ID {receipt.operation_id} · {receipt.code}
          </p>
          <pre className="tool-output">{receipt.output || receipt.evidence}</pre>
          {receipt.outcome === 'unknown' && (
            <button
              className="secondary-button"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  setReceipt(await feature.reconcile(receipt.operation_id));
                })
              }
            >
              核对实际结果
            </button>
          )}
          {receipt.artifact && (
            <>
              <p className="module-note">
                {receipt.artifact.path} · {receipt.artifact.size_bytes} bytes · SHA256{' '}
                {receipt.artifact.sha256}
              </p>
              <a
                className="secondary-button"
                href={feature.artifactUrl(receipt.operation_id)}
                download
              >
                下载已验证文件
              </a>
              <button
                className="secondary-button"
                onClick={() => setExpected(receipt.artifact?.sha256 ?? '')}
              >
                将摘要用于下次修改
              </button>
            </>
          )}
        </article>
      )}
    </section>
  );
}
