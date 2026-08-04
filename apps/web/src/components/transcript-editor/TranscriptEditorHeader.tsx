"use client";

import Link from "next/link";
import { useT } from "../../lib/i18n";
import {
  isTranscriptPipelineActionUnlocked,
  resolveTranscriptPipelineGuide,
  transcriptPipelineActionLabelKey,
  transcriptPipelineStepLabelKey,
  type TranscriptPipelinePrimaryAction
} from "../../lib/transcriptEditorPipeline";
import type { TranscriptEditorState, TranslationPreset } from "../../types/transcript-editor";
import { AsyncButton } from "../shared/AsyncButton";

type Props = {
  state: TranscriptEditorState;
  dirtyCount: number;
  blockingCount: number;
  saving: boolean;
  reanalyzing: boolean;
  translating: boolean;
  synthesizingTts: boolean;
  hasJoinedTts: boolean;
  ttsSourceFingerprint?: string | null;
  onSave: () => void;
  onDiscard: () => void;
  onTranslateLiteral: (preset: TranslationPreset) => void;
  onReanalyze: (preset: TranslationPreset) => void;
  onGenerateTts: () => void;
};

type CommandIconKind = "save" | "translate" | "tts" | "final" | "reasr" | "discard";

function CommandIcon({ kind }: { kind: CommandIconKind }) {
  if (kind === "save") {
    return (
      <svg className="editor-command__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4.5 4.5h9.2L15.5 6.3V15.5H4.5V4.5z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinejoin="round"
        />
        <path
          d="M7 4.5v3.8h5.2V4.5M7 15.5v-4.2h6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "translate") {
    return (
      <svg className="editor-command__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4.5 5.5h7.5M8.2 5.5 6 14.5M10.2 14.5 8.2 5.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M12.2 9.2h3.6M14 9.2c0 2.4-1.4 4.6-3.2 5.8"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (kind === "tts") {
    return (
      <svg className="editor-command__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M4.5 8.2v3.6M7.2 6.2v7.6M9.9 4.8v10.4M12.6 6.8v6.4M15.3 8.2v3.6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (kind === "final") {
    return (
      <svg className="editor-command__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M5 10.2 8.2 13.4 15 6.6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (kind === "reasr") {
    return (
      <svg className="editor-command__icon" viewBox="0 0 20 20" aria-hidden="true">
        <path
          d="M15.5 10a5.5 5.5 0 1 1-1.6-3.9"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
        <path
          d="M15.5 4.8v3.6h-3.6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  return (
    <svg className="editor-command__icon" viewBox="0 0 20 20" aria-hidden="true">
      <path
        d="M5 6.2h10M7.2 6.2V5.2A1.2 1.2 0 0 1 8.4 4h3.2A1.2 1.2 0 0 1 12.8 5.2v1M6.4 6.2l.6 8.4A1.2 1.2 0 0 0 8.2 16h3.6a1.2 1.2 0 0 0 1.2-1.4l.6-8.4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function PipelineLockIcon() {
  return (
    <svg className="editor-command__pipeline-lock" viewBox="0 0 20 20" aria-hidden="true">
      <path
        d="M6.5 9.2V7.4a3.5 3.5 0 0 1 7 0v1.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <rect
        x="5.2"
        y="9.2"
        width="9.6"
        height="6.6"
        rx="1.4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      />
    </svg>
  );
}

export function TranscriptEditorHeader({
  state,
  dirtyCount,
  blockingCount,
  saving,
  reanalyzing,
  translating,
  synthesizingTts,
  hasJoinedTts,
  ttsSourceFingerprint = null,
  onSave,
  onDiscard,
  onTranslateLiteral,
  onReanalyze,
  onGenerateTts
}: Props) {
  const t = useT();
  const busy = saving || reanalyzing || translating || synthesizingTts;
  const guide = resolveTranscriptPipelineGuide(state, { hasJoinedTts, ttsSourceFingerprint });
  const ttsBlocked = !guide.hasVietnamese;
  const primary = guide.primaryAction;
  const translateUnlocked = isTranscriptPipelineActionUnlocked("translate", guide.currentStep);
  const ttsUnlocked = isTranscriptPipelineActionUnlocked("tts", guide.currentStep);
  const finalUnlocked = isTranscriptPipelineActionUnlocked("final", guide.currentStep);

  function runTranslate(isPrimary: boolean) {
    const confirmKey = isPrimary
      ? "transcriptEditorHeader.translateLiteralConfirm"
      : "transcriptEditorHeader.translateAgainCascadeConfirm";
    if (window.confirm(t(confirmKey))) {
      onTranslateLiteral("literal_safe");
    }
  }

  function runTts(isPrimary: boolean) {
    if (!ttsUnlocked || ttsBlocked) return;
    const regenerating = !isPrimary || guide.hasJoinedTts || guide.ttsOutdated;
    const confirmKey = regenerating
      ? "transcriptEditorHeader.regenerateTtsConfirm"
      : "transcriptEditorHeader.generateTtsConfirm";
    if (window.confirm(t(confirmKey))) {
      onGenerateTts();
    }
  }

  function actionClass(action: TranscriptPipelinePrimaryAction, base: string): string {
    const role = primary === action ? `${base} editor-command__primary` : `${base} editor-command__quiet`;
    if (action === "tts" && guide.ttsOutdated) return `${role} editor-command__tts--stale`;
    return role;
  }

  return (
    <header className="transcript-header transcript-header--command">
      <div className="transcript-header__bar">
        <div className="transcript-header__lead">
          <Link className="transcript-header__back" href="/selection/review-board">
            <svg className="transcript-header__back-icon" viewBox="0 0 20 20" aria-hidden="true">
              <path
                d="M11.8 4.8 6.6 10l5.2 5.2M6.8 10h7.6"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span>{t("transcriptEditorHeader.backToReviewBoard")}</span>
          </Link>
          <ol className="editor-command__pipeline" aria-label={t("transcriptEditorHeader.pipelineLabel")}>
            {guide.steps.map((step, index) => {
              const locked = step.state === "pending";
              const showConnector = index < guide.steps.length - 1;
              const connectorReached = step.state === "done" || step.state === "active";
              return (
                <li
                  className={`editor-command__pipeline-step is-${step.state}`}
                  key={step.key}
                  title={locked ? t("transcriptEditorHeader.pipelineLocked") : undefined}
                  aria-current={step.state === "active" ? "step" : undefined}
                >
                  <span className="editor-command__pipeline-badge">
                    <span className="editor-command__pipeline-index" aria-hidden="true">
                      {step.state === "done" ? "✓" : locked ? <PipelineLockIcon /> : index + 1}
                    </span>
                    <span className="editor-command__pipeline-label">{t(transcriptPipelineStepLabelKey(step.key))}</span>
                  </span>
                  {showConnector ? (
                    <span
                      className={`editor-command__pipeline-connector${connectorReached ? " is-reached" : ""}`}
                      aria-hidden="true"
                    >
                      <svg className="editor-command__pipeline-connector-icon" viewBox="0 0 20 20">
                        <path
                          d="M7.2 4.8 12.4 10 7.2 15.2"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.8"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ol>
          {guide.ttsFreshness === "outdated" ? (
            <span
              className="editor-command__freshness is-outdated"
              title={t("transcriptEditorHeader.freshnessTtsOutdated")}
            >
              {t("transcriptEditorHeader.freshnessTtsOutdated")}
            </span>
          ) : null}
        </div>

        <div className="editor-command" role="toolbar" aria-label={t("transcriptEditorHeader.toolbarLabel")}>
          <AsyncButton
            className="editor-command__save"
            pending={saving}
            pendingLabel={t("transcriptEditorHeader.saving")}
            leadingIcon={<CommandIcon kind="save" />}
            onClick={onSave}
            disabled={dirtyCount === 0 || busy || blockingCount > 0}
          >
            <span>{t("transcriptEditorHeader.saveDraft")}</span>
            {dirtyCount > 0 ? <span className="editor-command__dot" aria-hidden /> : null}
          </AsyncButton>

          <div className="editor-command__focus">
            {primary === "translate" ? (
              <AsyncButton
                className={actionClass("translate", "editor-command__translate")}
                pending={translating}
                pendingLabel={t("transcriptEditorHeader.translating")}
                leadingIcon={<CommandIcon kind="translate" />}
                disabled={busy}
                title={t("transcriptEditorHeader.pipelineNowTranslate")}
                onClick={() => runTranslate(true)}
              >
                <span>{t(transcriptPipelineActionLabelKey("translate", { isPrimary: true }))}</span>
              </AsyncButton>
            ) : null}

            {primary === "tts" ? (
              <AsyncButton
                className={actionClass("tts", "editor-command__tts")}
                pending={synthesizingTts}
                pendingLabel={t("transcriptEditorHeader.generatingTtsShort")}
                leadingIcon={<CommandIcon kind="tts" />}
                disabled={busy || ttsBlocked}
                title={ttsBlocked ? t("transcriptEditorHeader.ttsRequiresVi") : t("transcriptEditorHeader.pipelineNowTts")}
                onClick={() => runTts(true)}
              >
                <span>{t(transcriptPipelineActionLabelKey("tts", { isPrimary: true, ttsOutdated: guide.ttsOutdated }))}</span>
              </AsyncButton>
            ) : null}

            {primary === "final" ? (
              <Link
                className={actionClass("final", "editor-command__final")}
                href={`/production/final-review/${state.sourceVideoId}`}
                title={t("transcriptEditorHeader.pipelineNowFinal")}
              >
                <CommandIcon kind="final" />
                <span>{t(transcriptPipelineActionLabelKey("final", { isPrimary: true }))}</span>
              </Link>
            ) : null}
          </div>

          {translateUnlocked && primary !== "translate" ? (
            <AsyncButton
              className="editor-command__translate editor-command__quiet"
              pending={translating}
              pendingLabel={t("transcriptEditorHeader.translating")}
              leadingIcon={<CommandIcon kind="translate" />}
              disabled={busy}
              onClick={() => runTranslate(false)}
            >
              <span>{t(transcriptPipelineActionLabelKey("translate", { isPrimary: false }))}</span>
            </AsyncButton>
          ) : null}
          {ttsUnlocked && primary !== "tts" ? (
            <AsyncButton
              className={actionClass("tts", "editor-command__tts")}
              pending={synthesizingTts}
              pendingLabel={t("transcriptEditorHeader.generatingTtsShort")}
              leadingIcon={<CommandIcon kind="tts" />}
              disabled={busy || ttsBlocked}
              title={
                ttsBlocked
                  ? t("transcriptEditorHeader.ttsRequiresVi")
                  : guide.ttsOutdated
                    ? t("transcriptEditorHeader.freshnessTtsOutdated")
                    : undefined
              }
              onClick={() => runTts(false)}
            >
              <span>
                {t(transcriptPipelineActionLabelKey("tts", { isPrimary: false, ttsOutdated: guide.ttsOutdated }))}
              </span>
            </AsyncButton>
          ) : null}
          {finalUnlocked && primary !== "final" ? (
            <Link
              className="editor-command__final editor-command__quiet"
              href={`/production/final-review/${state.sourceVideoId}`}
            >
              <CommandIcon kind="final" />
              <span>{t(transcriptPipelineActionLabelKey("final", { isPrimary: false }))}</span>
            </Link>
          ) : null}

          <AsyncButton
            className="editor-command__reasr editor-command__quiet"
            pending={reanalyzing}
            pendingLabel={t("transcriptEditorHeader.reanalyzingShort")}
            leadingIcon={<CommandIcon kind="reasr" />}
            disabled={busy}
            title={t("transcriptEditorHeader.reanalyzeAudio")}
            onClick={() => {
              if (window.confirm(t("transcriptEditorHeader.reanalyzeCascadeConfirm"))) {
                onReanalyze("literal_safe");
              }
            }}
          >
            <span>{t("transcriptEditorHeader.reanalyzeShort")}</span>
          </AsyncButton>

          <button
            type="button"
            className="editor-command__discard"
            onClick={onDiscard}
            disabled={dirtyCount === 0 || busy}
          >
            <CommandIcon kind="discard" />
            <span>{t("transcriptEditorHeader.discard")}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
