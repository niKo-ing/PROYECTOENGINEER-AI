"use client";

import Link from "next/link";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

type MdNode = Record<string, unknown> & {
  type?: string;
  value?: string;
  children?: MdNode[];
};

const PRODUCT_URL_RE = /\/product\/(\d+)/g;

function transformChildren(parent: MdNode): void {
  if (!Array.isArray(parent.children)) return;
  if (parent.type === "code" || parent.type === "link" || parent.type === "inlineCode") return;

  const next: MdNode[] = [];
  for (const child of parent.children) {
    if (child?.type === "text" && typeof child.value === "string") {
      PRODUCT_URL_RE.lastIndex = 0;
      let cursor = 0;
      let changed = false;
      let match: RegExpExecArray | null;
      while ((match = PRODUCT_URL_RE.exec(child.value)) !== null) {
        changed = true;
        if (match.index > cursor) {
          next.push({ type: "text", value: child.value.slice(cursor, match.index) });
        }
        next.push({
          type: "link",
          url: match[0],
          title: null,
          children: [{ type: "text", value: match[0] }],
        });
        cursor = match.index + match[0].length;
      }
      if (changed) {
        if (cursor < child.value.length) next.push({ type: "text", value: child.value.slice(cursor) });
      } else {
        next.push(child);
      }
    } else {
      next.push(child);
    }
  }
  parent.children = next;
}

function walk(node: MdNode | unknown): void {
  if (!node || typeof node !== "object") return;
  const current = node as MdNode;
  if (Array.isArray(current.children)) {
    transformChildren(current);
    for (const child of current.children) walk(child);
  }
}

function remarkProductLinks() {
  return (tree: MdNode) => {
    walk(tree);
  };
}

const linkClassName = "font-medium text-primary underline underline-offset-2 decoration-primary/40 transition-colors hover:decoration-primary";
const headingClass = "mb-1.5 mt-3 font-semibold leading-snug text-foreground first:mt-0";

const components = {
  a: ({ href, children, node: _node, ...props }) => {
    void _node;
    if (href && href.startsWith("/") && !href.startsWith("//")) {
      return (
        <Link href={href} className={linkClassName}>
          {children}
        </Link>
      );
    }
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className={linkClassName}
        {...props}
      >
        {children}
      </a>
    );
  },
  p: ({ children }) => <p className="my-1.5 leading-6 first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => (
    <ul className="my-1.5 list-disc space-y-1 pl-5 marker:text-primary/60 first:mt-0 last:mb-0">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="my-1.5 list-decimal space-y-1 pl-5 marker:text-primary/60 first:mt-0 last:mb-0">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="leading-6">{children}</li>,
  h1: ({ children }) => <h1 className={headingClass}>{children}</h1>,
  h2: ({ children }) => <h2 className={cn(headingClass, "text-base")}>{children}</h2>,
  h3: ({ children }) => <h3 className={cn(headingClass, "text-sm")}>{children}</h3>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-primary/50 pl-3 text-sm text-muted-foreground last:mb-0">
      {children}
    </blockquote>
  ),
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  hr: () => <hr className="my-3 border-border" />,
  code: ({ children, className, ...props }) => (
    <code
      className={cn(
        "rounded-md bg-muted px-1.5 py-0.5 font-mono text-[0.85em] leading-snug",
        className
      )}
      {...props}
    >
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-xl bg-muted p-3.5 font-mono text-[13px] leading-relaxed first:mt-0 last:mb-0">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-b border-border px-2 py-1.5 text-left font-semibold">{children}</th>
  ),
  td: ({ children }) => <td className="border-b border-border px-2 py-1.5 align-top">{children}</td>,
} satisfies Components;

export function MarkdownContent({ markdown }: { markdown: string }) {
  return (
    <div className="chat-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkProductLinks]} components={components}>
        {markdown}
      </ReactMarkdown>
    </div>
  );
}