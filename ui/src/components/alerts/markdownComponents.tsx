import type { Components } from 'react-markdown';

export const reportMarkdownComponents: Components = {
  h1: ({ children }) => (
    <h1 className="text-2xl font-bold mb-4 text-cyan-400 wrap-break-word border-b border-cyan-400/20 pb-2">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-xl font-semibold mb-3 text-emerald-400 wrap-break-word">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-lg font-medium mb-2 text-violet-400 wrap-break-word">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-base font-medium mb-2 text-amber-400 wrap-break-word">{children}</h4>
  ),
  p: ({ children }) => (
    <p className="mb-3 text-gray-300 leading-relaxed wrap-break-word">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="list-disc list-inside mb-3 text-gray-300 space-y-1 ml-2">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal list-inside mb-3 text-gray-300 space-y-1 ml-2">{children}</ol>
  ),
  li: ({ children }) => (
    <li className="text-gray-300 wrap-break-word marker:text-primary">{children}</li>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-primary pl-4 italic text-gray-400 mb-3 bg-gray-800/50 py-2 rounded-r">
      {children}
    </blockquote>
  ),
  code: ({ children, className }) => {
    const isInline = !className;
    return isInline ? (
      <code className="bg-gray-800 px-2 py-0.5 rounded-sm text-sm font-mono text-emerald-400 break-all">
        {children}
      </code>
    ) : (
      <pre className="bg-gray-950 p-4 rounded-md overflow-x-auto mb-3 border border-gray-700">
        <code className="text-gray-300 text-sm font-mono">{children}</code>
      </pre>
    );
  },
  pre: ({ children }) => (
    <div className="bg-gray-950 p-4 rounded-md overflow-x-auto mb-3 border border-gray-700">
      {children}
    </div>
  ),
  strong: ({ children }) => <strong className="font-bold text-white">{children}</strong>,
  em: ({ children }) => <em className="italic text-gray-200">{children}</em>,
  a: ({ children, href }) => (
    <a
      href={href}
      className="text-primary hover:text-primary-dark underline decoration-primary/50 underline-offset-2 transition-colors"
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto mb-4">
      <table className="min-w-full border border-gray-700 rounded-lg overflow-hidden">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-gray-800 text-gray-100">{children}</thead>,
  tbody: ({ children }) => <tbody className="bg-gray-900/50">{children}</tbody>,
  tr: ({ children }) => (
    <tr className="border-b border-gray-700 hover:bg-gray-800/50 transition-colors">{children}</tr>
  ),
  th: ({ children }) => (
    <th className="px-4 py-2 text-left text-sm font-semibold text-gray-100">{children}</th>
  ),
  td: ({ children }) => (
    <td className="px-4 py-2 text-sm text-gray-300 wrap-break-word">{children}</td>
  ),
  hr: () => <hr className="my-6 border-gray-700" />,
};
