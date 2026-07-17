export const WHOLE_PROFILE_HARVEST_FEATURES = {
  connection: true,
  calibration: true,
  testCurrentVideo: true,
  verifyProfile: true,
  dryRunFirst: true,
  dryRunLast: true,
  dryRunRandom: true,
  runHarvest: true,
  stopResumeReset: true,
  diagnostics: true,

  legacyCaptureCurrentPage: false,
  legacySmartCapture: false,
  legacyFullModalHarvest: false,
  legacySafeRunner: false,
  legacyCDP: false,
  legacyProbeModal: false
} as const;

export type WholeProfileHarvestFeatureName = keyof typeof WHOLE_PROFILE_HARVEST_FEATURES;
