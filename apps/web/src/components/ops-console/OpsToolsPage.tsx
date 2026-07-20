"use client";

import { useT } from "../../lib/i18n";
import { OpsConsoleShell } from "../app-shell/OpsConsoleShell";
import { OpsPanel } from "./OpsShared";

const commands = [
  { labelKey: "opsTools.doctor", command: "npm run doctor", detailKey: "opsTools.doctorDetail" },
  { labelKey: "opsTools.migrate", command: "npm run db:migrate", detailKey: "opsTools.migrateDetail" },
  { labelKey: "opsTools.seedDemo", command: "npm run dev:seed", detailKey: "opsTools.seedDemoDetail" },
  { labelKey: "opsTools.startAll", command: "npm run dev", detailKey: "opsTools.startAllDetail" },
  { labelKey: "opsTools.stopAll", command: "npm run dev:stop", detailKey: "opsTools.stopAllDetail" },
  { labelKey: "opsTools.smoke", command: "npm run smoke", detailKey: "opsTools.smokeDetail" }
];

export function OpsToolsPage() {
  const t = useT();

  return (
    <OpsConsoleShell description={t("opsTools.description")} title={t("opsTools.title")}>
      <main className="ops-page">
        <section className="ops-grid">
          <OpsPanel title={t("opsTools.localCommands")}>
            <table className="health-table">
              <thead>
                <tr><th>{t("opsTools.task")}</th><th>{t("opsTools.command")}</th><th>{t("opsTools.useWhen")}</th></tr>
              </thead>
              <tbody>
                {commands.map((item) => (
                  <tr key={item.labelKey}>
                    <td>{t(item.labelKey)}</td>
                    <td><code>{item.command}</code></td>
                    <td>{t(item.detailKey)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </OpsPanel>

          <OpsPanel title={t("opsTools.runbooksAndDocs")}>
            <div className="studio-card-list">
              <div className="studio-card">
                <span>
                  <strong>{t("opsTools.docsDirectory")}</strong>
                  <small>{t("opsTools.docsDirectoryDetail")}</small>
                </span>
                <span>Local</span>
              </div>
            </div>
          </OpsPanel>

          <OpsPanel title={t("opsTools.browserActionPolicy")}>
            <ul className="compact-list">
              <li>{t("opsTools.policyLine1")}</li>
              <li>{t("opsTools.policyLine2")}</li>
              <li>{t("opsTools.policyLine3")}</li>
            </ul>
          </OpsPanel>
        </section>
      </main>
    </OpsConsoleShell>
  );
}
