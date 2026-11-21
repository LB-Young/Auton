import { useState, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';

function CodeBlock({ children }: { children?: ReactNode }) {
  const [message, setMessage] = useState('复制代码');
  return (
    <div className="code-block">
      <button
        className="code-copy"
        onClick={(event) => {
          const text = event.currentTarget.parentElement?.querySelector('pre')?.textContent ?? '';
          void navigator.clipboard
            .writeText(text)
            .then(() => setMessage('已复制'))
            .catch(() => setMessage('复制失败，请选择文本复制'));
        }}
      >
        {message}
      </button>
      <pre>{children}</pre>
    </div>
  );
}

export function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        skipHtml
        components={{
          pre: CodeBlock,
          a: ({ children: label, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {label}
            </a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
