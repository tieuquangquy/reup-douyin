"use client";

import { useRef, useState } from "react";
import { useT } from "../../lib/i18n";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import {
  TranscriptEditorPage,
  type TranscriptEditorPageHandle
} from "../transcript-editor/TranscriptEditorPage";

export function OperatorTranscriptEditorPage({ sourceVideoId }: { sourceVideoId: string }) {
  const t = useT();
  const editorRef = useRef<TranscriptEditorPageHandle>(null);
  const [refreshing, setRefreshing] = useState(false);

  return (
    <OperatorStudioShell
      actions={
        <TopbarRefreshButton
          busy={refreshing}
          onClick={() => {
            void (async () => {
              setRefreshing(true);
              try {
                await editorRef.current?.refresh();
              } finally {
                setRefreshing(false);
              }
            })();
          }}
        />
      }
      description={t("operatorRoutes.transcriptEditorDesc")}
      title={t("operatorRoutes.transcriptEditorTitle")}
    >
      <TranscriptEditorPage ref={editorRef} sourceVideoId={sourceVideoId} />
    </OperatorStudioShell>
  );
}
