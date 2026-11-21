import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Folder, X } from 'lucide-react';
import type { LocalDirectories } from '../../shared/contracts';
import type { ConversationFeature } from './factory';

export function ProjectPicker({
  feature,
  initial,
  hasConversation,
  onSelect,
  onClose,
}: {
  feature: ConversationFeature;
  initial: string | null;
  hasConversation: boolean;
  onSelect(path: string): void;
  onClose(): void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const scope = useRef(0);
  const [value, setValue] = useState(initial ?? '');
  const [listing, setListing] = useState<LocalDirectories | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  async function browse(path?: string) {
    const revision = ++scope.current;
    setLoading(true);
    setError('');
    try {
      const result = await feature.directories(path);
      if (revision !== scope.current) return;
      setListing(result);
      setValue(result.path);
    } catch (error) {
      if (revision === scope.current)
        setError(error instanceof Error ? error.message : '无法浏览目录');
    } finally {
      if (revision === scope.current) setLoading(false);
    }
  }
  useEffect(() => {
    dialog.current?.showModal();
    void browse(initial ?? undefined);
    return () => {
      scope.current++;
      dialog.current?.close();
    };
    // Initial binding is fixed for the lifetime of this picker.
  }, []);
  return (
    <dialog
      ref={dialog}
      className="cw-project-picker"
      aria-labelledby="project-picker-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <header>
        <h2 id="project-picker-title">选择本地项目目录</h2>
        <button className="cw-icon" aria-label="关闭目录选择" onClick={onClose}>
          <X size={19} />
        </button>
      </header>
      <p className="cw-picker-note">
        选择运行 Auton 后端的这台机器上的目录，直接处理原项目文件。修改仍需逐项批准。
        {hasConversation && '选择目录会开启一个新对话。'}
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void browse(value || undefined);
        }}
      >
        <input
          disabled={loading}
          aria-label="项目目录路径"
          placeholder="输入或粘贴绝对路径"
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <button type="submit" disabled={loading}>
          打开路径
        </button>
      </form>
      {error && (
        <p role="alert" className="cw-error">
          {error}
        </p>
      )}
      <div className="cw-directory-list" aria-label="可选项目文件夹">
        {loading ? (
          <p role="status">正在读取目录…</p>
        ) : (
          <>
            <button
              className="cw-directory-parent"
              disabled={!listing?.parent}
              onClick={() => void browse(listing?.parent ?? undefined)}
            >
              <ArrowUp size={16} />
              上一级目录
            </button>
            {listing?.directories.map((name) => (
              <button
                className="cw-directory"
                key={name}
                onClick={() => void browse(`${listing.path.replace(/\/$/, '')}/${name}`)}
              >
                <Folder size={17} />
                <span>{name}</span>
              </button>
            ))}
            {listing && !listing.directories.length && (
              <p>此目录没有可浏览的子文件夹，可以直接选择当前目录。</p>
            )}
            {listing?.truncated && <p>子目录较多，仅显示部分结果；可直接输入完整路径。</p>}
          </>
        )}
      </div>
      <footer>
        <button className="cw-secondary" onClick={onClose}>
          取消
        </button>
        <button
          className="cw-primary"
          disabled={loading || Boolean(error) || !listing?.parent || listing.path !== value}
          onClick={() => listing && onSelect(listing.path)}
        >
          使用此目录
        </button>
      </footer>
    </dialog>
  );
}
