import { pageMetadata } from "../../lib/pageMetadata";
import { OperatorStudioShell } from "../../components/app-shell/OperatorStudioShell";
import { OptimizationPage } from "../../components/optimization/OptimizationPage";

export const metadata = pageMetadata.optimization;

export default function Page() {
  return (
    <OperatorStudioShell
      actions={
        <>
          <a href="/publishing/drafts">Publish drafts</a>
          <a href="/selection/reup-queue">Reup queue</a>
        </>
      }
      description="Operator-facing optimization hints for source, account, and scheduling choices."
      title="Optimization"
    >
      <OptimizationPage />
    </OperatorStudioShell>
  );
}
