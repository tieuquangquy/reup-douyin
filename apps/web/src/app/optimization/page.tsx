import { pageMetadata } from "../../lib/pageMetadata";
import { OperatorStudioShell } from "../../components/app-shell/OperatorStudioShell";
import { OptimizationPage } from "../../components/optimization/OptimizationPage";

export const metadata = pageMetadata.optimization;

export default function Page() {
  return (
    <OperatorStudioShell
      actions={
        <>
          <a href="/ops/publish-health">Publish health</a>
          <a href="/ops/publish-control">Publish control</a>
          <a href="/ops/optimization">Ops optimization</a>
        </>
      }
      description="Operator-facing optimization hints for source, account, and scheduling choices."
      title="Optimization"
    >
      <OptimizationPage />
    </OperatorStudioShell>
  );
}
