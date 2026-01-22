import { useState, useCallback, memo, useMemo, Children, isValidElement } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Check, Copy } from 'lucide-react';

interface CodeBlockProps {
  language: string;
  children: string;
}

const CodeBlock = memo(function CodeBlock({ language, children }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [children]);

  return (
    <div className="code-block group">
      <div className="code-header">
        <span className="code-lang">{language || 'text'}</span>
        <button
          onClick={handleCopy}
          className="code-copy"
          aria-label={copied ? 'Copied' : 'Copy code'}
        >
          {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>
      <SyntaxHighlighter
        style={oneDark}
        language={language || 'text'}
        PreTag="div"
        customStyle={{
          margin: 0,
          borderRadius: '0 0 8px 8px',
          fontSize: '13px',
          lineHeight: '1.6',
        }}
      >
        {children}
      </SyntaxHighlighter>
    </div>
  );
});

interface MarkdownRendererProps {
  content: string;
}

function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const components: Components = useMemo(
    () => ({
      pre({ children }) {
        const childArray = Children.toArray(children);
        const firstChild = childArray[0];

        if (isValidElement(firstChild) && firstChild.type === 'code') {
          const codeProps = firstChild.props as {
            className?: string;
            children?: React.ReactNode;
          };
          const className = codeProps.className || '';
          const match = /language-(\w+)/.exec(className);
          const language = match ? match[1] : '';
          const codeContent = String(codeProps.children || '').replace(/\n$/, '');

          return <CodeBlock language={language} children={codeContent} />;
        }

        return <pre className="code-block-fallback">{children}</pre>;
      },
    }),
    []
  );

  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default memo(MarkdownRenderer);
