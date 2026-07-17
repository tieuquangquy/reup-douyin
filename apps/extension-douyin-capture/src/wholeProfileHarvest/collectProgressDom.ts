import type { CollectLiveProgressPhase } from "./collectLiveProgress.js";
import { formatIntegerCollectLabel } from "./collectDisplaySmoothing.js";
import type { ScannerControlPanelViewModel } from "./viewModel.js";

export type CollectProgressDomRefs = {
  shell: HTMLElement;
  statusRow: HTMLElement;
  statusText: HTMLElement;
  batchRow: HTMLElement;
  batchLabel: HTMLElement;
  batchValue: HTMLElement;
  track: HTMLElement;
  bar: HTMLElement;
  phaseLabel: HTMLElement;
};

const SHELL_CLASS = "scp-collect-live-shell";
const HOST_FLAG = "data-scp-collect-live-mounted";

function phaseLabelText(phase: CollectLiveProgressPhase): string {
  if (phase === "preparing") return "Preparing";
  if (phase === "collecting") return "Collecting";
  if (phase === "saving") return "Saving";
  return "Checking";
}

export function ensureCollectProgressDom(host: HTMLElement): CollectProgressDomRefs {
  const existing = host.querySelector<HTMLElement>(`.${SHELL_CLASS}`);
  if (existing && host.getAttribute(HOST_FLAG) === "yes") {
    return {
      shell: existing,
      statusRow: existing.querySelector<HTMLElement>("[data-scp-collect-status-row]")!,
      statusText: existing.querySelector<HTMLElement>("[data-scp-collect-status-text]")!,
      batchRow: existing.querySelector<HTMLElement>("[data-scp-collect-batch-row]")!,
      batchLabel: existing.querySelector<HTMLElement>("[data-scp-collect-batch-label]")!,
      batchValue: existing.querySelector<HTMLElement>("[data-scp-collect-batch-value]")!,
      track: existing.querySelector<HTMLElement>("[data-scp-collect-track]")!,
      bar: existing.querySelector<HTMLElement>("[data-scp-collect-bar]")!,
      phaseLabel: existing.querySelector<HTMLElement>("[data-scp-collect-phase-label]")!
    };
  }

  const shell = document.createElement("div");
  shell.className = SHELL_CLASS;
  shell.style.gridColumn = "1 / -1";

  const phaseLabel = document.createElement("span");
  phaseLabel.className = "scp-collect-phase-label";
  phaseLabel.dataset.scpCollectPhaseLabel = "yes";

  const statusRow = document.createElement("div");
  statusRow.className = "scanner-stat scp-counter scp-stats-compact scp-collect-status-row";
  statusRow.dataset.scpCollectStatusRow = "yes";
  const statusText = document.createElement("strong");
  statusText.dataset.scpCollectStatusText = "yes";
  statusRow.append(phaseLabel, statusText);

  const batchRow = document.createElement("div");
  batchRow.className = "scanner-stat scp-counter scp-scan-progress-counter";
  batchRow.dataset.scpCollectBatchRow = "yes";
  batchRow.hidden = true;
  const batchLabel = document.createElement("span");
  batchLabel.dataset.scpCollectBatchLabel = "yes";
  const batchValue = document.createElement("strong");
  batchValue.dataset.scpCollectBatchValue = "yes";
  batchRow.append(batchLabel, batchValue);

  const track = document.createElement("div");
  track.className = "scp-scan-progress-track scp-collect-progress-track";
  track.dataset.scpCollectTrack = "yes";
  track.setAttribute("role", "progressbar");
  track.setAttribute("aria-valuemin", "0");
  track.setAttribute("aria-valuemax", "100");
  const bar = document.createElement("div");
  bar.className = "scp-scan-progress-bar";
  bar.dataset.scpCollectBar = "yes";
  track.appendChild(bar);

  shell.append(statusRow, batchRow, track);
  host.appendChild(shell);
  host.setAttribute(HOST_FLAG, "yes");

  return { shell, statusRow, statusText, batchRow, batchLabel, batchValue, track, bar, phaseLabel };
}

export function removeCollectProgressDom(host: HTMLElement): void {
  host.querySelector(`.${SHELL_CLASS}`)?.remove();
  host.removeAttribute(HOST_FLAG);
}

export function updateCollectProgressDom(refs: CollectProgressDomRefs, vm: ScannerControlPanelViewModel): void {
  const progress = vm.collectProgress;
  if (!progress?.active) {
    refs.shell.hidden = true;
    return;
  }
  refs.shell.hidden = false;

  const phase = progress.phase;
  const phaseText = phaseLabelText(phase);
  if (refs.phaseLabel.textContent !== phaseText) {
    refs.phaseLabel.textContent = phaseText;
    refs.phaseLabel.dataset.phase = phase;
  }

  const statusLine = progress.profileIndeterminate
    ? (phase === "preparing" ? "Starting collection…" : "Collecting profile videos…")
    : formatIntegerCollectLabel(vm.headerStatus);
  if (refs.statusText.textContent !== statusLine) {
    refs.statusText.textContent = statusLine;
  }

  const showBatch = progress.showBatchCard === true;
  refs.batchRow.hidden = !showBatch;
  if (showBatch) {
    const batchLabel = phase === "saving" ? "This batch (saving)" : "This batch (checking)";
    const batchValue = `${progress.batchAttempted} / ${progress.batchTotal} · ${progress.batchReady} ready · ${progress.batchNeedData} need data`;
    if (refs.batchLabel.textContent !== batchLabel) refs.batchLabel.textContent = batchLabel;
    if (refs.batchValue.textContent !== batchValue) refs.batchValue.textContent = batchValue;
  }

  const indeterminate = Boolean(progress.profileIndeterminate);
  refs.track.dataset.indeterminate = indeterminate ? "yes" : "no";
  refs.track.setAttribute("aria-busy", indeterminate ? "true" : "false");

  if (indeterminate) {
    refs.bar.className = "scp-scan-progress-bar scp-collect-progress-bar-indeterminate";
    refs.bar.style.width = "";
    refs.track.removeAttribute("aria-valuenow");
    refs.track.setAttribute(
      "aria-label",
      phase === "preparing" ? "Preparing collection" : "Checking profile videos"
    );
  } else {
    refs.bar.className = "scp-scan-progress-bar";
    refs.bar.classList.remove("scp-collect-progress-bar-indeterminate");
    const percent = progress.profilePercent ?? 0;
    const width = `${percent}%`;
    if (refs.bar.style.width !== width) {
      refs.bar.style.width = width;
    }
    refs.track.setAttribute("aria-valuenow", String(percent));
    refs.track.setAttribute(
      "aria-label",
      `Profile collect progress ${progress.profileAlready} of ${progress.profileTotal}`
    );
  }
}
