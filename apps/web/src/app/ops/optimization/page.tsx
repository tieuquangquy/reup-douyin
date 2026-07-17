import { pageMetadata } from "../../../lib/pageMetadata";
import { OpsConsoleShell } from "../../../components/app-shell/OpsConsoleShell";
import { OptimizationPage } from "../../../components/optimization/OptimizationPage";

export const metadata = pageMetadata.opsOptimization;

export default function Page() {
  return (
    <OpsConsoleShell
      description="Use outcome quality and feedback-driven hints without turning the app into autopilot."
      title="Optimization"
    >
      <OptimizationPage />
    </OpsConsoleShell>
  );
}
