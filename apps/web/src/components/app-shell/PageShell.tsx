import type { ReactNode } from "react";

export function PageShell({
  title,
  description,
  children,
  actions
}: {
  title: string;
  description?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="page-shell">
      <div className="page-shell-header">
        <div>
          <h2>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        {actions ? <div className="page-shell-actions">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}
